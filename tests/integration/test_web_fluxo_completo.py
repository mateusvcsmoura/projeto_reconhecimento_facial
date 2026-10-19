"""Fluxo HTTP sintético contra a composição real e PostgreSQL descartável task019."""

from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import os
import subprocess
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from src.application.services.fila_facial import TipoJobFacial
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ResultadoWorker,
    WorkerFacial,
)
from src.application.use_cases.verificar_presenca_web import ConcluirPresenca
from src.config.web_settings import WebSettings
from src.domain.services.desafio_captura import EvidenciaEtapa, OrientacaoPose
from src.domain.services.face_recognition import ResultadoFacial
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    PostgresPresencaWebRepository,
)
from src.presentation.web.app import WebServices
from src.web_main import create_web_app

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_BACKEND_GATE_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_BACKEND_GATE_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_019"
NOME_BANCO = "task019_web_backend_gate_test_20261019"
COMENTARIO_BANCO = (
    "projeto_reconhecimento_facial: task 019 disposable backend gate database"
)
ORIGEM = "https://testserver"
SEGREDO = "segredo-sintetico-task019-maior-que-trinta-e-dois-caracteres"


def _alembic(url: str, *args: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": url}
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    if resultado.returncode:
        parsed = make_url(url)
        saida = f"{resultado.stdout}\n{resultado.stderr}".replace(
            url, parsed.render_as_string(hide_password=True)
        )
        if parsed.password:
            saida = saida.replace(parsed.password, "<REDACTED>")
        raise RuntimeError(
            f"alembic {' '.join(args)} falhou; URL e credenciais foram omitidas.\n"
            f"{saida}"
        )


@pytest.fixture(scope="module")
def postgres_gate_url() -> Iterator[str]:
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("PostgreSQL task019 exige opt-in para banco descartável.")
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} não definida; nenhum arquivo .env é consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != NOME_BANCO:
        raise RuntimeError("Banco task019 recusado: nome inesperado.")
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Banco task019 recusado: destino precisa ser local.")

    engine = create_engine(url, future=True, pool_pre_ping=True)
    migration_iniciada = False
    try:
        with engine.connect() as connection:
            nome, comentario, endereco = connection.execute(
                text(
                    "SELECT current_database(), "
                    "shobj_description(oid, 'pg_database'), inet_server_addr()::text "
                    "FROM pg_database WHERE datname = current_database()"
                )
            ).one()
        if nome != NOME_BANCO or comentario != COMENTARIO_BANCO or endereco is None:
            raise RuntimeError(
                "Banco task019 recusado antes de DDL: marcador/localidade ausentes."
            )
        migration_iniciada = True
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        _alembic(url, "check")
        yield url
    finally:
        if migration_iniciada:
            with engine.begin() as connection:
                tabelas = connection.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
                    )
                ).scalars()
                nomes = [
                    engine.dialect.identifier_preparer.quote(nome) for nome in tabelas
                ]
                if nomes:
                    connection.execute(
                        text("TRUNCATE TABLE " + ", ".join(nomes) + " CASCADE")
                    )
            _alembic(url, "downgrade", "base")
        engine.dispose()


def _login_admin(client: TestClient) -> dict[str, str]:
    resposta = client.post(
        "/api/v1/auth/login",
        json={"usuario": "admin", "senha": "SenhaAdmin!019"},
        headers={"Origin": ORIGEM},
    )
    assert resposta.status_code == 200, resposta.text
    return {"Origin": ORIGEM, "X-CSRF-Token": resposta.json()["csrf_token"]}


def _criar_professor(
    client: TestClient, headers: dict[str, str], usuario: str
) -> dict[str, object]:
    resposta = client.post(
        "/api/v1/admin/contas",
        json={
            "usuario": usuario,
            "papel": "professor",
            "justificativa": "cadastro sintético da task019",
        },
        headers=headers,
    )
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def _ativar_professor(
    client: TestClient, usuario: str, senha_temporaria: str, nova_senha: str
) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario, "senha": senha_temporaria},
        headers={"Origin": ORIGEM},
    )
    assert login.status_code == 200, login.text
    troca = client.post(
        "/api/v1/auth/trocar-senha",
        json={"nova_senha": nova_senha},
        headers={
            "Origin": ORIGEM,
            "X-CSRF-Token": login.json()["csrf_token"],
        },
    )
    assert troca.status_code == 204, troca.text
    login_final = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario, "senha": nova_senha},
        headers={"Origin": ORIGEM},
    )
    assert login_final.status_code == 200, login_final.text
    return {"Origin": ORIGEM, "X-CSRF-Token": login_final.json()["csrf_token"]}


def _login_professor(client: TestClient, usuario: str, senha: str) -> dict[str, str]:
    resposta = client.post(
        "/api/v1/auth/login",
        json={"usuario": usuario, "senha": senha},
        headers={"Origin": ORIGEM},
    )
    assert resposta.status_code == 200, resposta.text
    return {"Origin": ORIGEM, "X-CSRF-Token": resposta.json()["csrf_token"]}


def _semear_referencias_sinteticas(
    services: WebServices, turma_id: int, admin_id: int, agora: dt.datetime
) -> tuple[str, str]:
    assert services.auth_repository is not None
    factory = services.auth_repository.session_factory
    matricula_aprovada = "SYN-019-001"
    matricula_pendente = "SYN-019-002"
    with factory.begin() as session:
        aluno = models.Aluno(
            matricula=matricula_aprovada,
            nome="=FORMULA-SINTETICA",
            consentimento_em=agora,
        )
        sem_referencias = models.Aluno(
            matricula=matricula_pendente,
            nome="Pessoa Sintética Pendente",
            consentimento_em=agora,
        )
        session.add_all((aluno, sem_referencias))
        session.flush()
        session.add_all(
            (
                models.AlunoTurma(turma_id=turma_id, aluno_id=aluno.id, ativo=True),
                models.AlunoTurma(
                    turma_id=turma_id, aluno_id=sem_referencias.id, ativo=True
                ),
            )
        )
        cadastro = models.SolicitacaoCadastroWeb(
            tipo="cadastro",
            estado="aprovada",
            convite_ref="convite-sintetico-task019",
            turma_id=turma_id,
            matricula=matricula_aprovada,
            nome=aluno.nome,
            consentimento_em=agora,
            consentimento_versao="termos-sinteticos-v1",
            expira_em=agora + dt.timedelta(days=1),
            criada_em=agora - dt.timedelta(minutes=1),
            decidida_em=agora,
            decidida_por_conta_id=admin_id,
            metodo_identidade="identidade_sintetica",
            justificativa="aprovação sintética exclusiva para teste",
        )
        session.add(cadastro)
        session.flush()
        conjunto = models.ConjuntoReferenciasWeb(
            solicitacao_id=cadastro.id,
            aluno_id=aluno.id,
            versao=1,
            estado="ativo",
            job_id=str(uuid4()),
            embedding_modelo="FaceNet512",
            embedding_dim=512,
            criado_em=agora,
            ativado_em=agora,
        )
        session.add(conjunto)
        session.flush()
        session.add_all(
            [
                models.ReferenciaFacialWeb(
                    conjunto_id=conjunto.id,
                    ordinal=ordinal,
                    caminho_privado_relativo=f"sintetico/{ordinal}.bin",
                    embedding=bytes(2048),
                    embedding_modelo="FaceNet512",
                    embedding_dim=512,
                    consentimento_em=agora,
                    consentimento_versao="termos-sinteticos-v1",
                    capturada_em=agora,
                )
                for ordinal in (1, 2, 3)
            ]
        )
    return matricula_aprovada, matricula_pendente


def test_fluxo_http_postgres_com_ownership_cadastro_aprovado_e_presenca_fake(
    postgres_gate_url: str, tmp_path: Path
) -> None:
    agora = dt.datetime.now(dt.UTC).replace(microsecond=0)
    settings = WebSettings(
        environment="test",
        database_url=postgres_gate_url,
        secret_key=SEGREDO,
        retention_days=10,
        database_disposable=True,
        public_origin=ORIGEM,
        purpose_end_at=agora + dt.timedelta(days=2),
        capture_temp_dir=tmp_path / "capturas",
        reference_storage_dir=tmp_path / "referencias",
    )
    settings.capture_temp_dir.mkdir(parents=True, exist_ok=True)
    app = create_web_app(settings)
    services: WebServices = app.state.web_services
    assert services.auth_repository is not None
    assert services.fila_facial is not None
    assert services.capture_storage is not None
    admin_id = services.auth_repository.criar_admin_bootstrap("admin", "SenhaAdmin!019")

    try:
        with TestClient(app, base_url=ORIGEM) as admin_client:
            headers_admin = _login_admin(admin_client)
            professor_a = _criar_professor(admin_client, headers_admin, "prof.a")
            professor_b = _criar_professor(admin_client, headers_admin, "prof.b")
            with TestClient(app, base_url=ORIGEM) as professor_b_setup:
                _ativar_professor(
                    professor_b_setup,
                    "prof.b",
                    str(professor_b["credencial_temporaria"]),
                    "SenhaProfessorB!019",
                )
            factory = services.auth_repository.session_factory
            with factory() as session:
                professor_b_id = session.scalar(
                    select(models.ProfessorWeb.id).where(
                        models.ProfessorWeb.conta_id == professor_b["id"]
                    )
                )
            assert professor_b_id is not None
            turma_resposta = admin_client.post(
                "/api/v1/turmas",
                json={
                    "materia": "IA sintética task019",
                    "periodo": "diurno",
                    "responsavel_professor_id": professor_b_id,
                    "confirmar": True,
                    "justificativa": "teste integrado sintético",
                },
                headers=headers_admin,
            )
            assert turma_resposta.status_code == 201, turma_resposta.text
            turma_id = int(turma_resposta.json()["id"])
            matricula_aprovada, matricula_pendente = _semear_referencias_sinteticas(
                services, turma_id, admin_id, agora
            )

            with (
                TestClient(app, base_url=ORIGEM) as professor_a_client,
                TestClient(app, base_url=ORIGEM) as professor_b_client,
                TestClient(app, base_url=ORIGEM) as aluno_client,
            ):
                headers_a = _ativar_professor(
                    professor_a_client,
                    "prof.a",
                    str(professor_a["credencial_temporaria"]),
                    "SenhaProfessorA!019",
                )
                headers_b = _login_professor(
                    professor_b_client,
                    "prof.b",
                    "SenhaProfessorB!019",
                )
                assert (
                    professor_a_client.get(
                        f"/api/v1/turmas/{turma_id}", headers=headers_a
                    ).status_code
                    == 404
                )
                assert (
                    professor_b_client.get(
                        f"/api/v1/turmas/{turma_id}", headers=headers_b
                    ).status_code
                    == 200
                )

                inicio = dt.datetime.now(dt.UTC).replace(microsecond=0)
                sessao_resposta = professor_b_client.post(
                    f"/api/v1/turmas/{turma_id}/sessoes",
                    json={
                        "titulo": "Aula sintética task019",
                        "inicio_em": (inicio - dt.timedelta(minutes=1)).isoformat(),
                        "fim_em": (inicio + dt.timedelta(minutes=20)).isoformat(),
                    },
                    headers=headers_b,
                )
                assert sessao_resposta.status_code == 201, sessao_resposta.text
                sessao_id = int(sessao_resposta.json()["id"])
                link_resposta = professor_b_client.post(
                    f"/api/v1/sessoes/{sessao_id}/links", headers=headers_b
                )
                assert link_resposta.status_code == 201, link_resposta.text
                acesso_resposta = aluno_client.post(
                    "/api/v1/acessos-link",
                    json={"token": link_resposta.json()["token"]},
                )
                assert acesso_resposta.status_code == 200, acesso_resposta.text
                credencial_link = acesso_resposta.json()["credencial"]

                sem_aprovacao = aluno_client.post(
                    f"/api/v1/sessoes/{sessao_id}/tentativas",
                    headers={
                        "Authorization": f"Bearer {credencial_link}",
                        "Idempotency-Key": "task019-sem-aprovacao-001",
                    },
                    json={"matricula": matricula_pendente},
                )
                assert sem_aprovacao.status_code == 404

                tentativa_resposta = aluno_client.post(
                    f"/api/v1/sessoes/{sessao_id}/tentativas",
                    headers={
                        "Authorization": f"Bearer {credencial_link}",
                        "Idempotency-Key": "task019-presenca-aprovada-001",
                    },
                    json={"matricula": matricula_aprovada},
                )
                assert tentativa_resposta.status_code == 201, tentativa_resposta.text
                tentativa = tentativa_resposta.json()
                credencial_captura = tentativa["credencial_captura"]
                desafio = tentativa["desafio"]
                facial = ResultadoFacial(
                    identidade_ok=True,
                    desafio_ok=True,
                    antispoofing_ok=True,
                    qualidade_ok=True,
                    motivo_tecnico=None,
                    versao_referencia=1,
                    politica="mediana-3",
                )

                class VerificadorSintetico:
                    def processar(self, _job, capturas):
                        etapa = len(capturas)
                        assert etapa in (1, 2, 3)
                        orientacao = (
                            OrientacaoPose(desafio["orientacao"])
                            if etapa == 2
                            else OrientacaoPose.FRENTE
                        )
                        assert services.desafio_captura is not None
                        resultado_desafio = services.desafio_captura.validar_etapa(
                            _job.id,
                            etapa,
                            EvidenciaEtapa(
                                quantidade_rostos=1,
                                orientacao=orientacao,
                                identidade_ok=True,
                                qualidade_ok=True,
                                antispoofing_ok=True,
                                versao_referencia=1,
                            ),
                            dt.datetime.now(dt.UTC),
                        )
                        if etapa < 3:
                            assert resultado_desafio.proxima_etapa == etapa + 1
                            return ResultadoWorker(
                                True,
                                CodigoResultadoWorker.CONCLUIDA,
                                aguardando_etapa=True,
                            )
                        assert resultado_desafio.desafio_ok
                        assert len(capturas) == 3
                        assert services.presenca_repository is not None
                        ConcluirPresenca(services.presenca_repository).executar(
                            _job, facial, agora=dt.datetime.now(dt.UTC)
                        )
                        return ResultadoWorker(
                            True,
                            CodigoResultadoWorker.CONCLUIDA,
                            resultado_facial=facial,
                            finalizacao_persistida=True,
                        )

                worker = WorkerFacial(
                    services.fila_facial,
                    services.capture_storage,
                    processadores={TipoJobFacial.PRESENCA: VerificadorSintetico()},
                    intervalo_heartbeat_segundos=3600,
                )
                try:
                    worker.inicializar()
                    worker.preaquecer()
                    for etapa in (1, 2, 3):
                        captura = aluno_client.post(
                            f"/api/v1/tentativas/{tentativa['id']}/capturas",
                            headers={"Authorization": f"Bearer {credencial_captura}"},
                            json={
                                "etapa": etapa,
                                "nonce": desafio["nonce"],
                                "captura_base64": base64.b64encode(
                                    f"frame-sintetico-{etapa}".encode()
                                ).decode("ascii"),
                            },
                        )
                        assert captura.status_code == 202, captura.text
                        assert worker.executar_um()
                        if etapa < 3:
                            status_etapa = aluno_client.get(
                                f"/api/v1/tentativas/{tentativa['id']}",
                                headers={
                                    "Authorization": f"Bearer {credencial_captura}"
                                },
                            )
                            assert status_etapa.status_code == 200, status_etapa.text
                            desafio = status_etapa.json()["desafio"]
                finally:
                    worker.fechar()

                status_final = aluno_client.get(
                    f"/api/v1/tentativas/{tentativa['id']}",
                    headers={"Authorization": f"Bearer {credencial_captura}"},
                )
                assert status_final.status_code == 200, status_final.text
                assert status_final.json()["estado"] == "concluida"

                data_local = inicio.astimezone(ZoneInfo("America/Sao_Paulo")).date()
                url_csv = (
                    f"/api/v1/turmas/{turma_id}/presencas.csv"
                    f"?inicio={data_local.isoformat()}&fim={data_local.isoformat()}"
                )
                painel = professor_b_client.get(
                    f"/api/v1/turmas/{turma_id}/painel", headers=headers_b
                )
                assert painel.status_code == 200, painel.text
                sessao_painel = next(
                    item for item in painel.json()["sessoes"] if item["id"] == sessao_id
                )
                assert sessao_painel["presencas_presentes"] == 1
                assert sessao_painel["presencas_anuladas"] == 0

                csv_antes = professor_b_client.get(url_csv, headers=headers_b)
                assert csv_antes.status_code == 200, csv_antes.text
                linhas_antes = list(
                    csv.DictReader(StringIO(csv_antes.content.decode("utf-8")))
                )
                assert len(linhas_antes) == 1
                assert linhas_antes[0]["nome"] == "'=FORMULA-SINTETICA"
                assert linhas_antes[0]["status"] == "presente"
                assert linhas_antes[0]["correcao_manual"] == "não"
                assert "embedding" not in csv_antes.text.lower()
                assert credencial_link not in csv_antes.text
                assert desafio["nonce"] not in csv_antes.text

                assert (
                    professor_a_client.get(
                        f"/api/v1/turmas/{turma_id}/painel", headers=headers_a
                    ).status_code
                    == 404
                )
                assert (
                    professor_a_client.get(url_csv, headers=headers_a).status_code
                    == 404
                )

                pedido_revisao = aluno_client.post(
                    "/api/v1/revisoes",
                    headers={"Authorization": f"Bearer {credencial_link}"},
                    json={
                        "sessao_id": sessao_id,
                        "matricula": matricula_aprovada,
                        "justificativa": "Correção manual sintética auditada.",
                        "via_acessivel": True,
                    },
                )
                assert pedido_revisao.status_code == 202, pedido_revisao.text
                revisoes_b = professor_b_client.get(
                    f"/api/v1/turmas/{turma_id}/revisoes?estado=aberta",
                    headers=headers_b,
                )
                assert revisoes_b.status_code == 200, revisoes_b.text
                revisao = next(
                    item
                    for item in revisoes_b.json()
                    if item["id"] == pedido_revisao.json()["protocolo"]
                )
                assert revisao["matricula"] == matricula_aprovada
                assert (
                    professor_a_client.get(
                        f"/api/v1/turmas/{turma_id}/revisoes?estado=aberta",
                        headers=headers_a,
                    ).status_code
                    == 404
                )
                decisao = professor_b_client.post(
                    f"/api/v1/revisoes/{revisao['id']}/decidir",
                    headers=headers_b,
                    json={
                        "decisao": "anulada",
                        "justificativa": "Anulação sintética para validar auditoria.",
                        "versao_esperada": revisao["versao_presenca"],
                        "identidade_confirmada": False,
                    },
                )
                assert decisao.status_code == 200, decisao.text
                assert decisao.json()["status"] == "anulada"
                assert decisao.json()["origem"] == "biometrica"
                assert decisao.json()["versao"] == revisao["versao_presenca"] + 1

                painel_corrigido = professor_b_client.get(
                    f"/api/v1/turmas/{turma_id}/painel", headers=headers_b
                )
                sessao_corrigida = next(
                    item
                    for item in painel_corrigido.json()["sessoes"]
                    if item["id"] == sessao_id
                )
                assert sessao_corrigida["presencas_presentes"] == 0
                assert sessao_corrigida["presencas_anuladas"] == 1
                csv_corrigido = professor_b_client.get(url_csv, headers=headers_b)
                linha_corrigida = next(
                    csv.DictReader(StringIO(csv_corrigido.content.decode("utf-8")))
                )
                assert linha_corrigida["status"] == "anulada"
                assert linha_corrigida["correcao_manual"] == "sim"

        with factory() as session:
            presencas = list(
                session.scalars(
                    select(models.Presenca).where(
                        models.Presenca.tentativa_id == tentativa["id"]
                    )
                )
            )
            assert len(presencas) == 1
            assert presencas[0].origem == "biometrica"
            assert presencas[0].status == "anulada"
            assert presencas[0].versao == 2
            assert (
                session.scalar(
                    select(models.EventoAuditoriaWeb.id).where(
                        models.EventoAuditoriaWeb.acao == "presenca_corrigida_manual",
                        models.EventoAuditoriaWeb.alvo_id == str(presencas[0].id),
                    )
                )
                is not None
            )
            pendente = session.scalar(
                select(models.Aluno).where(models.Aluno.matricula == matricula_pendente)
            )
            assert pendente is not None
            assert (
                session.scalar(
                    select(models.Presenca.id).where(
                        models.Presenca.aluno_id == pendente.id
                    )
                )
                is None
            )
    finally:
        services.on_shutdown()


def test_rate_limit_postgres_serializa_concorrencia_e_reabre_janela(
    postgres_gate_url: str,
) -> None:
    engine = create_engine(postgres_gate_url, future=True, pool_pre_ping=True)
    repository = PostgresPresencaWebRepository(
        sessionmaker(bind=engine, expire_on_commit=False, future=True),
        timezone_name="America/Sao_Paulo",
    )
    instante = dt.datetime.now(dt.UTC).replace(microsecond=0)
    chave = hashlib.sha256(uuid4().bytes).hexdigest()

    def requisicao(_ordinal: int) -> int | None:
        return repository.limitar_requisicao(
            chave,
            agora=instante,
            limite=5,
            janela=dt.timedelta(minutes=1),
        )

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            resultados = list(pool.map(requisicao, range(12)))
        assert resultados.count(None) == 5
        assert all(
            isinstance(espera, int) and espera > 0
            for espera in resultados
            if espera is not None
        )
        assert (
            repository.limitar_requisicao(
                chave,
                agora=instante + dt.timedelta(minutes=1),
                limite=5,
                janela=dt.timedelta(minutes=1),
            )
            is None
        )
    finally:
        engine.dispose()
