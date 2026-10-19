"""Migration 0011 e corrida real de revisao contra worker em PostgreSQL local."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    PostgresPresencaWebRepository,
)

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_GESTAO_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_GESTAO_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_016"
NOME_BANCO = "task016_gestao_test_20261018"
COMENTARIO_BANCO = (
    "projeto_reconhecimento_facial: task 016 disposable web management database"
)
AGORA = dt.datetime(2026, 10, 18, 12, 0, tzinfo=dt.UTC)


def _url_autorizada() -> str:
    __tracebackhide__ = True
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("PostgreSQL task016 exige opt-in para banco descartavel.")
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} nao definida; nenhum arquivo .env e consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != NOME_BANCO:
        raise RuntimeError("Banco task016 recusado: destino inesperado.")
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Banco task016 recusado: o destino precisa ser local.")
    return url


def _alembic(url: str, *args: str) -> None:
    __tracebackhide__ = True
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env={**os.environ, "ALEMBIC_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode:
        seguro = make_url(url).render_as_string(hide_password=True)
        saida = f"{resultado.stdout}\n{resultado.stderr}".replace(url, seguro)
        raise RuntimeError(
            f"alembic {' '.join(args)} falhou sem expor credencial.\n{saida}"
        )


@pytest.fixture(scope="module")
def postgres_gestao_engine() -> Iterator[Engine]:
    __tracebackhide__ = True
    url = _url_autorizada()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    migration_iniciada = False
    try:
        with engine.connect() as connection:
            banco, comentario, endereco = connection.execute(
                text(
                    "SELECT current_database(), "
                    "shobj_description(oid, 'pg_database'), inet_server_addr()::text "
                    "FROM pg_database WHERE datname = current_database()"
                )
            ).one()
        if banco != NOME_BANCO or comentario != COMENTARIO_BANCO or endereco is None:
            raise RuntimeError(
                "Banco task016 recusado antes de DDL: nome, marcador ou localidade "
                "nao confirmados."
            )
        migration_iniciada = True
        if inspect(engine).has_table("eventos_auditoria_web"):
            # O banco tem nome/marcador task016; dados sintéticos anteriores podem
            # ser descartados aqui para que os downgrades protegidos sejam testados.
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "TRUNCATE eventos_auditoria_web, contas_web, alunos, "
                        "turmas, jobs_faciais_web, links_cadastro_web "
                        "RESTART IDENTITY CASCADE"
                    )
                )
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        _alembic(url, "check")
        yield engine
    finally:
        try:
            if migration_iniciada and inspect(engine).has_table(
                "eventos_auditoria_web"
            ):
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "TRUNCATE eventos_auditoria_web, contas_web, alunos, "
                            "turmas, jobs_faciais_web, links_cadastro_web "
                            "RESTART IDENTITY CASCADE"
                        )
                    )
            if migration_iniciada:
                _alembic(url, "downgrade", "base")
        finally:
            engine.dispose()


def test_migration_0011_cria_schema_de_revisao_e_preserva_indices_legados(
    postgres_gestao_engine: Engine,
) -> None:
    inspector = inspect(postgres_gestao_engine)
    colunas_presenca = {coluna["name"] for coluna in inspector.get_columns("presencas")}
    assert {
        "status",
        "origem",
        "versao",
        "horario_evidencia",
        "corrigida_em",
        "corrigida_por_conta_id",
    } <= colunas_presenca
    colunas_revisao = {
        coluna["name"] for coluna in inspector.get_columns("revisoes_presenca_web")
    }
    assert {
        "id",
        "sessao_id",
        "aluno_id",
        "versao_presenca_base",
        "decisao",
    } <= colunas_revisao
    indices_presenca = {indice["name"] for indice in inspector.get_indexes("presencas")}
    assert "uq_presencas_turma_aluno_dia" in indices_presenca
    assert "uq_presencas_legado_aluno_dia" in indices_presenca
    assert "uq_presencas_sessao_aluno" in indices_presenca
    indices_revisao = {
        indice["name"] for indice in inspector.get_indexes("revisoes_presenca_web")
    }
    assert "uq_revisoes_presenca_aberta" in indices_revisao
    with postgres_gestao_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0011"
        )


def test_worker_nao_grava_presenca_se_revisao_for_confirmada_enquanto_aguarda_lock(
    postgres_gestao_engine: Engine,
) -> None:
    # Reutiliza a fixture sintética de sessão/worker já exercitada pela task015.
    from test_presenca_sessao_postgresql import (
        _criar_contexto_presenca,
        _preparar_processamento_valido,
        _reservar_tentativa,
    )

    engine = postgres_gestao_engine
    contexto = _criar_contexto_presenca(engine)
    job_id = _reservar_tentativa(
        engine,
        PostgresPresencaWebRepository(engine),
        contexto,
        1,
        AGORA,
    )
    job, decisao = _preparar_processamento_valido(
        engine,
        contexto,
        job_id,
        recebida_em=AGORA + dt.timedelta(seconds=60),
        concluir_em=AGORA + dt.timedelta(seconds=63),
    )

    worker_engine = create_engine(
        make_url(os.environ[ENV_URL]),
        future=True,
        pool_pre_ping=True,
        connect_args={"application_name": "task016-worker-race"},
    )
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            with Session(engine) as transacao, transacao.begin():
                transacao.execute(
                    select(models.SessaoPresencaWeb)
                    .where(models.SessaoPresencaWeb.id == contexto.sessao_id)
                    .with_for_update()
                ).scalar_one()
                futuro = executor.submit(
                    PostgresPresencaWebRepository(worker_engine).concluir_presenca,
                    job,
                    decisao,
                    agora=AGORA + dt.timedelta(seconds=63),
                )
                limite = time.monotonic() + 8
                bloqueado = False
                while time.monotonic() < limite:
                    with engine.connect() as connection:
                        bloqueado = bool(
                            connection.execute(
                                text(
                                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                    "WHERE application_name = :app "
                                    "AND state = 'active' AND wait_event_type = 'Lock')"
                                ),
                                {"app": "task016-worker-race"},
                            ).scalar_one()
                        )
                    if bloqueado:
                        break
                    time.sleep(0.05)
                assert bloqueado, "worker nao aguardou o lock da sessao no PostgreSQL"
                transacao.add(
                    models.RevisaoPresencaWeb(
                        id=uuid4(),
                        turma_id=contexto.turma_id,
                        sessao_id=contexto.sessao_id,
                        aluno_id=contexto.aluno_id,
                        estado="aberta",
                        justificativa_solicitacao=(
                            "Revisao sintetica em corrida concorrente."
                        ),
                        via_acessivel=True,
                        solicitada_em=AGORA + dt.timedelta(seconds=62),
                        versao_presenca_base=0,
                    )
                )
            # O commit acima libera a sessao antes de aguardar o resultado do worker.
            assert futuro.result(timeout=8) is None
    finally:
        worker_engine.dispose()

    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM presencas "
                    "WHERE sessao_id = :sessao AND aluno_id = :aluno"
                ),
                {"sessao": contexto.sessao_id, "aluno": contexto.aluno_id},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM revisoes_presenca_web "
                    "WHERE sessao_id = :sessao AND aluno_id = :aluno "
                    "AND estado = 'aberta'"
                ),
                {"sessao": contexto.sessao_id, "aluno": contexto.aluno_id},
            ).scalar_one()
            == 1
        )

    with pytest.raises(RuntimeError, match="Downgrade 0011 recusado"):
        _alembic(os.environ[ENV_URL], "downgrade", "0010")
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0011"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM revisoes_presenca_web")
            ).scalar_one()
            == 1
        )
