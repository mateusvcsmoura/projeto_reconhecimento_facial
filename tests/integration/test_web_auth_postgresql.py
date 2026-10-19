"""Integracao PostgreSQL task010; exige banco isolado e opt-in proprio."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from src.config.web_settings import WebSettings
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_conta_repository import (
    ConflitoConta,
    PostgresContaRepository,
)
from src.presentation.web.app import WebServices, create_app

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_AUTH_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_AUTH_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_010"
COMENTARIO_BANCO = (
    "projeto_reconhecimento_facial: task 010 disposable authentication database"
)
SEGREDO_TESTE = "somente-segredo-sintetico-task010-maior-que-trinta-e-dois"


def _revisao_atual() -> str:
    revisao = ScriptDirectory.from_config(
        Config(str(ROOT / "alembic.ini"))
    ).get_current_head()
    assert revisao is not None
    return revisao


def _alembic(url: str, *argumentos: str) -> None:
    ambiente = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=ROOT,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode:
        raise RuntimeError(
            f"alembic {' '.join(argumentos)} falhou sem exibir a URL do banco.\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )


def _limpar_tabelas_auth(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE eventos_auditoria_web, limites_login_web, "
                "sessoes_autenticacao_web, professores_web, contas_web, "
                "presencas, aluno_turma, turmas, alunos "
                "RESTART IDENTITY CASCADE"
            )
        )


def _url_autorizada() -> str:
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip(
            "PostgreSQL task010 exige autorizacao explicita para banco descartavel."
        )
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} nao definida; nenhum arquivo .env e consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database is None:
        raise RuntimeError(
            "Banco task010 recusado: a URL precisa apontar para PostgreSQL."
        )
    nome = parsed.database.lower()
    if not any(marcador in nome for marcador in ("test", "task010", "web_auth")):
        raise RuntimeError("Banco task010 recusado: nome sem marcador de descarte.")
    return url


@pytest.fixture(scope="module")
def postgres_auth_engine() -> Iterator[Engine]:
    url = _url_autorizada()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    schema_preparado = False
    try:
        with engine.connect() as connection:
            comentario = connection.execute(
                text(
                    "SELECT shobj_description(oid, 'pg_database') "
                    "FROM pg_database WHERE datname = current_database()"
                )
            ).scalar_one_or_none()
        if comentario != COMENTARIO_BANCO:
            raise RuntimeError(
                "Banco task010 recusado antes de DDL: comentario de descarte ausente."
            )
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        schema_preparado = True
        yield engine
    finally:
        try:
            if schema_preparado:
                _limpar_tabelas_auth(engine)
                _alembic(url, "downgrade", "base")
        finally:
            engine.dispose()


@pytest.fixture(autouse=True)
def banco_auth_limpo_por_teste(postgres_auth_engine: Engine) -> None:
    _limpar_tabelas_auth(postgres_auth_engine)


@pytest.fixture
def repositorio_auth(postgres_auth_engine: Engine) -> PostgresContaRepository:
    factory: sessionmaker[Session] = sessionmaker(
        bind=postgres_auth_engine, expire_on_commit=False, future=True
    )
    return PostgresContaRepository(
        factory,
        segredo=SEGREDO_TESTE,
        parametros_hash=(1, 8192, 1),
    )


def test_migration_unicidade_e_professor_associado(
    postgres_auth_engine: Engine, repositorio_auth: PostgresContaRepository
) -> None:
    with postgres_auth_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == _revisao_atual()
        )

    admin_id = repositorio_auth.criar_admin_bootstrap("admin", "SenhaInicial!123")
    professor_id, _, _ = repositorio_auth.criar_conta(
        admin_id, "professor", "professor", "cadastro sintetico"
    )
    with pytest.raises(ConflitoConta):
        repositorio_auth.criar_conta(
            admin_id, " PROFESSOR ", "professor", "tentativa duplicada"
        )

    with postgres_auth_engine.connect() as connection:
        conta = connection.execute(
            text(
                "SELECT c.usuario_normalizado, p.id "
                "FROM contas_web c JOIN professores_web p ON p.conta_id = c.id "
                "WHERE c.id = :id"
            ),
            {"id": professor_id},
        ).one()
        assert conta.usuario_normalizado == "professor"
        assert conta.id > 0
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM eventos_auditoria_web "
                    "WHERE ator_conta_id = :id"
                ),
                {"id": admin_id},
            ).scalar_one()
            == 1
        )

    for comando in (
        "UPDATE eventos_auditoria_web SET acao = 'adulterada'",
        "DELETE FROM eventos_auditoria_web",
    ):
        with pytest.raises(DBAPIError), postgres_auth_engine.begin() as connection:
            connection.execute(text(comando))


def test_falha_do_trigger_de_auditoria_reverte_conta(
    postgres_auth_engine: Engine, repositorio_auth: PostgresContaRepository
) -> None:
    admin_id = repositorio_auth.criar_admin_bootstrap("admin", "SenhaInicial!123")
    with postgres_auth_engine.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION falhar_auditoria_task010() RETURNS trigger AS $$ "
                "BEGIN RAISE EXCEPTION 'falha sintetica de auditoria'; END; "
                "$$ LANGUAGE plpgsql"
            )
        )
        connection.execute(
            text(
                "CREATE TRIGGER trg_falhar_auditoria_task010 "
                "BEFORE INSERT ON eventos_auditoria_web FOR EACH ROW "
                "EXECUTE FUNCTION falhar_auditoria_task010()"
            )
        )
    try:
        with pytest.raises(DBAPIError):
            repositorio_auth.criar_conta(
                admin_id, "nao.persistir", "professor", "teste rollback"
            )
    finally:
        with postgres_auth_engine.begin() as connection:
            connection.execute(
                text(
                    "DROP TRIGGER trg_falhar_auditoria_task010 ON eventos_auditoria_web"
                )
            )
            connection.execute(text("DROP FUNCTION falhar_auditoria_task010()"))

    with postgres_auth_engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM contas_web "
                    "WHERE usuario_normalizado = 'nao.persistir'"
                )
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM professores_web")
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM eventos_auditoria_web "
                    "WHERE acao = 'conta_criada'"
                )
            ).scalar_one()
            == 0
        )


def test_professor_nao_acessa_ou_transfere_turma_de_outro(
    postgres_auth_engine: Engine, repositorio_auth: PostgresContaRepository
) -> None:
    repositorio_auth.criar_admin_bootstrap("admin", "SenhaInicial!123")
    settings = WebSettings(
        environment="test",
        database_url=str(postgres_auth_engine.url),
        secret_key=SEGREDO_TESTE,
        retention_days=14,
        public_origin="https://testserver",
        database_disposable=True,
    )
    app = create_app(settings, WebServices(auth_repository=repositorio_auth))
    with TestClient(app, base_url="https://testserver") as client:
        resposta_admin = client.post(
            "/api/v1/auth/login",
            json={"usuario": "admin", "senha": "SenhaInicial!123"},
            headers={"Origin": "https://testserver"},
        )
        assert resposta_admin.status_code == 200
        admin = resposta_admin.json()
        headers_admin = {
            "Origin": "https://testserver",
            "X-CSRF-Token": admin["csrf_token"],
        }
        professores = {
            usuario: client.post(
                "/api/v1/admin/contas",
                json={
                    "usuario": usuario,
                    "papel": "professor",
                    "justificativa": "teste sintetico",
                },
                headers=headers_admin,
            ).json()
            for usuario in ("prof.a", "prof.b")
        }
        factory = repositorio_auth.session_factory
        with factory.begin() as session:
            perfil_b = session.scalar(
                select(models.ProfessorWeb).where(
                    models.ProfessorWeb.conta_id == professores["prof.b"]["id"]
                )
            )
            assert perfil_b is not None
            turma = models.Turma(materia="IA sintetica", periodo="diurno")
            session.add(turma)
            session.flush()
            turma_id = turma.id
            perfil_b_id = perfil_b.id

        resposta_transferencia = client.post(
            f"/api/v1/admin/turmas/{turma_id}/responsavel",
            json={
                "professor_id": perfil_b_id,
                "justificativa": "atribuicao inicial",
            },
            headers=headers_admin,
        )
        assert resposta_transferencia.status_code == 204

        def ativar_professor(
            usuario: str, senha_temporaria: str, senha_nova: str
        ) -> str:
            resposta_login = client.post(
                "/api/v1/auth/login",
                json={"usuario": usuario, "senha": senha_temporaria},
                headers={"Origin": "https://testserver"},
            )
            assert resposta_login.status_code == 200
            csrf = resposta_login.json()["csrf_token"]
            resposta_troca = client.post(
                "/api/v1/auth/trocar-senha",
                json={"nova_senha": senha_nova},
                headers={"Origin": "https://testserver", "X-CSRF-Token": csrf},
            )
            assert resposta_troca.status_code == 204
            resposta_login_nova = client.post(
                "/api/v1/auth/login",
                json={"usuario": usuario, "senha": senha_nova},
                headers={"Origin": "https://testserver"},
            )
            assert resposta_login_nova.status_code == 200
            return client.get("/api/v1/auth/csrf").json()["csrf_token"]

        csrf_a = ativar_professor(
            "prof.a",
            professores["prof.a"]["credencial_temporaria"],
            "SenhaProfessorA!123",
        )
        leitura_a = client.get(f"/api/v1/turmas/{turma_id}")
        alteracao_a = client.post(
            f"/api/v1/admin/turmas/{turma_id}/responsavel",
            json={"professor_id": perfil_b_id, "justificativa": "nao permitido"},
            headers={"Origin": "https://testserver", "X-CSRF-Token": csrf_a},
        )
        ativar_professor(
            "prof.b",
            professores["prof.b"]["credencial_temporaria"],
            "SenhaProfessorB!123",
        )
        leitura_b = client.get(f"/api/v1/turmas/{turma_id}")
        client.post(
            "/api/v1/auth/login",
            json={"usuario": "admin", "senha": "SenhaInicial!123"},
            headers={"Origin": "https://testserver"},
        )
        leitura_admin = client.get(f"/api/v1/turmas/{turma_id}")

    assert leitura_a.status_code == 404
    assert alteracao_a.status_code == 403
    assert leitura_b.status_code == 200
    assert leitura_admin.status_code == 200
