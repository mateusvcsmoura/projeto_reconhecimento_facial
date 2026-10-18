"""Contratos HTTP e de persistencia da autenticacao web, com dados sinteticos."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scripts.criar_admin_web import main as bootstrap_main
from src.application.use_cases.autenticar_professor import normalizar_usuario
from src.config.web_settings import WebSettings
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_conta_repository import (
    COOKIE_SESSAO,
    PostgresContaRepository,
)
from src.presentation.web.app import WebServices, create_app

DATABASE_URL_TESTE = (
    "postgresql+psycopg://usuario:senha-nao-real@test-db:5432/face_test_task010"
)
SEGREDO_TESTE = "segredo-sintetico-para-testes-com-mais-de-32-caracteres"
ORIGEM_TESTE = "https://testserver"
AGORA_INICIAL = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def banco_sqlite() -> Any:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def registrar_btrim(connection: Any, _record: Any) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip())

    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def relogio() -> dict[str, datetime]:
    return {"agora": AGORA_INICIAL}


@pytest.fixture
def repositorio(banco_sqlite: Any, relogio: dict[str, datetime]) -> Any:
    return PostgresContaRepository(
        banco_sqlite,
        segredo=SEGREDO_TESTE,
        clock=lambda: relogio["agora"],
        parametros_hash=(1, 8192, 1),
    )


def _settings() -> WebSettings:
    return WebSettings(
        environment="test",
        database_url=DATABASE_URL_TESTE,
        secret_key=SEGREDO_TESTE,
        retention_days=14,
        database_disposable=True,
        public_origin=ORIGEM_TESTE,
    )


def _client(repositorio: Any) -> TestClient:
    app = create_app(_settings(), WebServices(auth_repository=repositorio))
    return TestClient(app, base_url=ORIGEM_TESTE)


def _criar_admin(repositorio: Any, usuario: str = "admin") -> int:
    return repositorio.criar_admin_bootstrap(usuario, "SenhaInicial!123")


def _login(client: TestClient, usuario: str, senha: str) -> tuple[dict[str, Any], str]:
    resposta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario, "senha": senha},
        headers={"Origin": ORIGEM_TESTE},
    )
    return resposta.json(), resposta.cookies.get(COOKIE_SESSAO, "")


def test_usuario_normalizado_com_unicode_e_espacos() -> None:
    assert normalizar_usuario("  Jo\u00e3o.Silva  ") == "jo\u00e3o.silva"
    assert normalizar_usuario(" ＡDMIN ") == "admin"


def test_login_sessao_csrf_e_me_sem_expor_segredos(
    repositorio: Any,
) -> None:
    conta_id = _criar_admin(repositorio)
    with _client(repositorio) as client:
        _, token_anterior = _login(client, " ADMIN ", "SenhaInicial!123")
        payload, token = _login(client, " ADMIN ", "SenhaInicial!123")
        me = client.get("/api/v1/me")

    assert token
    assert token != token_anterior
    assert payload["csrf_token"]
    assert payload["conta"]["id"] == conta_id
    assert payload["conta"]["papel"] == "admin"
    assert "SenhaInicial" not in str(payload)
    assert me.status_code == 200
    csrf_refresh = client.get("/api/v1/auth/csrf")
    assert me.json() == {
        "id": conta_id,
        "papel": "admin",
        "ativo": True,
        "troca_senha_obrigatoria": False,
    }
    assert csrf_refresh.status_code == 200
    assert csrf_refresh.json()["csrf_token"] == payload["csrf_token"]

    with repositorio.session_factory() as session:
        auth_session = session.query(models.SessaoAutenticacaoWeb).one()
        assert token not in auth_session.token_hash
        assert len(auth_session.token_hash) == 64
    assert repositorio.autenticar_sessao(token_anterior) is None


def test_login_nao_enumera_usuario_e_aplica_limite_por_conta_e_ip(
    repositorio: Any,
) -> None:
    _criar_admin(repositorio)
    with _client(repositorio) as client:
        usuario_inexistente = client.post(
            "/api/v1/auth/login",
            json={"usuario": "desconhecido", "senha": "senha-errada"},
            headers={"Origin": ORIGEM_TESTE},
        )
        senha_errada = client.post(
            "/api/v1/auth/login",
            json={"usuario": "admin", "senha": "senha-errada"},
            headers={"Origin": ORIGEM_TESTE},
        )
        for _ in range(4):
            bloqueio = client.post(
                "/api/v1/auth/login",
                json={"usuario": "admin", "senha": "senha-errada"},
                headers={"Origin": ORIGEM_TESTE},
            )

    assert usuario_inexistente.status_code == senha_errada.status_code == 401
    assert usuario_inexistente.json()["codigo"] == senha_errada.json()["codigo"]
    assert usuario_inexistente.json()["mensagem"] == senha_errada.json()["mensagem"]
    assert bloqueio.status_code == 429
    assert "admin" not in bloqueio.text


def test_cookie_seguro_origin_e_csrf_sao_obrigatorios(
    repositorio: Any,
) -> None:
    _criar_admin(repositorio)
    with _client(repositorio) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"usuario": "admin", "senha": "SenhaInicial!123"},
            headers={"Origin": ORIGEM_TESTE},
        )
        cookie = login.cookies.get(COOKIE_SESSAO)
        sem_csrf = client.post("/api/v1/auth/logout", headers={"Origin": ORIGEM_TESTE})
        origem_invalida = client.post(
            "/api/v1/auth/logout",
            headers={
                "Origin": "https://evil.example",
                "X-CSRF-Token": login.json()["csrf_token"],
            },
        )
        logout = client.post(
            "/api/v1/auth/logout",
            headers={
                "Origin": ORIGEM_TESTE,
                "X-CSRF-Token": login.json()["csrf_token"],
            },
        )
        client.cookies.set(
            COOKIE_SESSAO, "token-invalido", domain="testserver", path="/api/v1"
        )
        cookie_invalido = client.get("/api/v1/me")

    assert login.status_code == 200
    assert cookie
    assert "secure" in login.headers["set-cookie"].lower()
    assert "httponly" in login.headers["set-cookie"].lower()
    assert "samesite=lax" in login.headers["set-cookie"].lower()
    assert sem_csrf.status_code == 403
    assert origem_invalida.status_code == 403
    assert logout.status_code == 204
    assert cookie_invalido.status_code == 401


def test_expiracao_por_inatividade_e_limite_absoluto(
    repositorio: Any, relogio: dict[str, datetime]
) -> None:
    _criar_admin(repositorio)
    with _client(repositorio) as client:
        _, _ = _login(client, "admin", "SenhaInicial!123")
        relogio["agora"] += timedelta(minutes=31)
        expirou_idle = client.get("/api/v1/me")
        _, _ = _login(client, "admin", "SenhaInicial!123")
        relogio["agora"] += timedelta(hours=8, minutes=1)
        expirou_absoluta = client.get("/api/v1/me")

    assert expirou_idle.status_code == 401
    assert expirou_absoluta.status_code == 401


def test_reset_temporario_e_troca_obrigatoria_invalidam_credencial_antiga(
    repositorio: Any,
) -> None:
    admin_id = _criar_admin(repositorio)
    with _client(repositorio) as client:
        login, _ = _login(client, "admin", "SenhaInicial!123")
        criacao = client.post(
            "/api/v1/admin/contas",
            json={
                "usuario": "prof.a",
                "papel": "professor",
                "justificativa": "admissao",
            },
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": login["csrf_token"]},
        )
        professor_id = criacao.json()["id"]
        reset = client.post(
            f"/api/v1/admin/contas/{professor_id}/redefinir-senha",
            json={
                "justificativa": "solicitacao conferida",
                "referencia_verificacao": "chamada institucional 42",
            },
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": login["csrf_token"]},
        )
        temporary_password = reset.json()["credencial_temporaria"]
        login_professor, _ = _login(client, "prof.a", temporary_password)
        login_temporaria_repetida = client.post(
            "/api/v1/auth/login",
            json={"usuario": "prof.a", "senha": temporary_password},
            headers={"Origin": ORIGEM_TESTE},
        )
        troca = client.post(
            "/api/v1/auth/trocar-senha",
            json={"nova_senha": "NovaSenhaSegura!456"},
            headers={
                "Origin": ORIGEM_TESTE,
                "X-CSRF-Token": login_professor["csrf_token"],
            },
        )
        reutilizacao = client.post(
            "/api/v1/auth/login",
            json={"usuario": "prof.a", "senha": temporary_password},
            headers={"Origin": ORIGEM_TESTE},
        )

    assert admin_id > 0
    assert criacao.status_code == 201
    assert reset.status_code == 200
    assert temporary_password not in str(reset.json().get("hash", ""))
    assert login_professor["conta"]["troca_senha_obrigatoria"] is True
    assert login_temporaria_repetida.status_code == 401
    assert troca.status_code == 204
    assert reutilizacao.status_code == 401


def test_autorizacao_de_turma_exige_responsavel_e_admin_explicito(
    repositorio: Any, banco_sqlite: Any
) -> None:
    _criar_admin(repositorio)
    with _client(repositorio) as client:
        admin_login, _ = _login(client, "admin", "SenhaInicial!123")
        csrf_admin = admin_login["csrf_token"]
        criar_a = client.post(
            "/api/v1/admin/contas",
            json={"usuario": "prof.a", "papel": "professor", "justificativa": "criar"},
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": csrf_admin},
        )
        criar_b = client.post(
            "/api/v1/admin/contas",
            json={"usuario": "prof.b", "papel": "professor", "justificativa": "criar"},
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": csrf_admin},
        )
        professor_b_id = criar_b.json()["id"]
        with banco_sqlite() as session:
            perfil_b = (
                session.query(models.ProfessorWeb)
                .filter_by(conta_id=professor_b_id)
                .one()
            )
            session.add(
                models.Turma(
                    id=101,
                    materia="Inteligencia Artificial",
                    periodo="diurno",
                    responsavel_professor_id=None,
                )
            )
            session.commit()
            turma_id = 101
            responsavel_id = perfil_b.id
        transferencia = client.post(
            f"/api/v1/admin/turmas/{turma_id}/responsavel",
            json={
                "professor_id": responsavel_id,
                "justificativa": "atribuicao inicial",
            },
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": csrf_admin},
        )
        assert transferencia.status_code == 204

        def autenticar_com_troca(usuario: str, temporaria: str, nova: str) -> None:
            login_temp, _ = _login(client, usuario, temporaria)
            assert login_temp["conta"]["troca_senha_obrigatoria"] is True
            troca = client.post(
                "/api/v1/auth/trocar-senha",
                json={"nova_senha": nova},
                headers={
                    "Origin": ORIGEM_TESTE,
                    "X-CSRF-Token": login_temp["csrf_token"],
                },
            )
            assert troca.status_code == 204
            login_nova, _ = _login(client, usuario, nova)
            assert login_nova["conta"]["troca_senha_obrigatoria"] is False

        autenticar_com_troca(
            "prof.a", criar_a.json()["credencial_temporaria"], "SenhaProfessorA!123"
        )
        turma_de_b = client.get(f"/api/v1/turmas/{turma_id}")
        csrf_a = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        transferencia_por_a = client.post(
            f"/api/v1/admin/turmas/{turma_id}/responsavel",
            json={"professor_id": responsavel_id, "justificativa": "nao permitido"},
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": csrf_a},
        )
        autenticar_com_troca(
            "prof.b", criar_b.json()["credencial_temporaria"], "SenhaProfessorB!123"
        )
        turma_de_b_por_b = client.get(f"/api/v1/turmas/{turma_id}")
        login_admin, _ = _login(client, "admin", "SenhaInicial!123")
        turma_por_admin = client.get(f"/api/v1/turmas/{turma_id}")

    assert criar_a.status_code == criar_b.status_code == 201
    assert turma_de_b.status_code == 404
    assert transferencia_por_a.status_code == 403
    assert turma_de_b_por_b.status_code == 200
    assert turma_de_b_por_b.json()["responsavel_professor_id"] == responsavel_id
    assert turma_por_admin.status_code == 200
    assert login_admin["conta"]["papel"] == "admin"


def test_desativacao_invalida_sessoes_e_credenciais(
    repositorio: Any, banco_sqlite: Any
) -> None:
    _criar_admin(repositorio)
    with _client(repositorio) as client:
        login_admin, _ = _login(client, "admin", "SenhaInicial!123")
        criado = client.post(
            "/api/v1/admin/contas",
            json={"usuario": "prof", "papel": "professor", "justificativa": "criar"},
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": login_admin["csrf_token"]},
        )
        conta_id = criado.json()["id"]
        sessao_professor = repositorio.autenticar(
            "prof", criado.json()["credencial_temporaria"], "127.0.0.1"
        )
        with banco_sqlite() as session:
            professor_id = (
                session.query(models.ProfessorWeb).filter_by(conta_id=conta_id).one().id
            )
        desativar = client.post(
            f"/api/v1/admin/contas/{conta_id}/desativar",
            json={"justificativa": "conta nao autorizada"},
            headers={"Origin": ORIGEM_TESTE, "X-CSRF-Token": login_admin["csrf_token"]},
        )
        login_inativo = client.post(
            "/api/v1/auth/login",
            json={"usuario": "prof", "senha": criado.json()["credencial_temporaria"]},
            headers={"Origin": ORIGEM_TESTE},
        )

    assert professor_id > 0
    assert desativar.status_code == 204
    assert login_inativo.status_code == 401
    assert repositorio.autenticar_sessao(sessao_professor.token_sessao) is None
    with banco_sqlite() as session:
        assert (
            session.query(models.SessaoAutenticacaoWeb)
            .filter_by(conta_id=conta_id)
            .count()
            == 0
        )


def test_falha_de_auditoria_reverte_mutacao(
    banco_sqlite: Any,
) -> None:
    def falhar_auditoria(_session: Session, _evento: dict[str, Any]) -> None:
        raise RuntimeError("falha de auditoria")

    repositorio = PostgresContaRepository(
        banco_sqlite,
        segredo=SEGREDO_TESTE,
        clock=lambda: AGORA_INICIAL,
        parametros_hash=(1, 8192, 1),
        gravar_auditoria=falhar_auditoria,
    )

    with pytest.raises(RuntimeError, match="auditoria"):
        repositorio.criar_admin_bootstrap("admin", "SenhaInicial!123")

    with banco_sqlite() as session:
        assert session.query(models.ContaWeb).count() == 0
        assert session.query(models.EventoAuditoriaWeb).count() == 0


def test_bootstrap_repetido_nao_sobrescreve_senha(repositorio: Any) -> None:
    primeiro_id = repositorio.criar_admin_bootstrap("admin", "SenhaInicial!123")
    segundo_id = repositorio.criar_admin_bootstrap("admin", "OutraSenha!456")

    assert primeiro_id == segundo_id
    assert repositorio.verificar_senha("admin", "SenhaInicial!123")
    assert not repositorio.verificar_senha("admin", "OutraSenha!456")


def test_comando_bootstrap_recusa_senha_em_argumento(capsys: Any) -> None:
    resultado = bootstrap_main(["--senha", "segredo-nao-deve-ser-impresso"])

    assert resultado == 2
    assert "segredo-nao-deve-ser-impresso" not in capsys.readouterr().err


def test_segredos_nao_sao_escritos_nos_logs(repositorio: Any, caplog: Any) -> None:
    _criar_admin(repositorio)
    senha = "SenhaIncorreta!123"
    with caplog.at_level(logging.DEBUG), _client(repositorio) as client:
        resposta = client.post(
            "/api/v1/auth/login",
            json={"usuario": "admin", "senha": senha},
            headers={"Origin": ORIGEM_TESTE},
        )

    assert resposta.status_code == 401
    assert senha not in caplog.text
    assert SEGREDO_TESTE not in caplog.text


def test_origem_producao_precisa_ser_https_e_sem_caminho() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        WebSettings(
            environment="production",
            database_url="postgresql+psycopg://u:p@db.example:5432/face_prod",
            secret_key=SEGREDO_TESTE,
            retention_days=14,
            public_origin="http://web.example",
            database_disposable=False,
        )

    with pytest.raises(ValueError, match="somente esquema"):
        WebSettings(
            environment="test",
            database_url=DATABASE_URL_TESTE,
            secret_key=SEGREDO_TESTE,
            retention_days=14,
            database_disposable=True,
            public_origin="https://testserver/app",
        )


def test_migration_e_models_declaram_schema_novo_sem_aplicar_banco() -> None:
    assert "contas_web" in models.Base.metadata.tables
    assert "professores_web" in models.Base.metadata.tables
    assert "sessoes_autenticacao_web" in models.Base.metadata.tables
    assert "eventos_auditoria_web" in models.Base.metadata.tables
    assert "limites_login_web" in models.Base.metadata.tables
    turma = models.Base.metadata.tables["turmas"]
    assert turma.c.responsavel_professor_id.nullable is True
