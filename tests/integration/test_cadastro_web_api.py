"""Migração e fluxo transacional de links em PostgreSQL descartável local."""

from __future__ import annotations

import datetime as dt
import hashlib
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.application.use_cases.gerenciar_links import GerenciarLinks
from src.application.use_cases.solicitar_cadastro_web import (
    ConsentimentoWeb,
    ContextoConvite,
    DadosCadastroWeb,
    SolicitarCadastroWeb,
)
from src.domain.services.autorizacao import AtorWeb
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_link_repository import (
    PostgresLinkRepository,
)
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    PostgresSolicitacaoRepository,
)

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_CADASTRO_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_CADASTRO_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_014"
COMENTARIO_BANCO = (
    "projeto_reconhecimento_facial: task 014 disposable registration database"
)
AGORA = dt.datetime(2026, 10, 18, 15, 0, tzinfo=dt.UTC)


def _url_autorizada() -> str:
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("PostgreSQL task014 exige opt-in para banco descartável.")
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} não definida; nenhum .env será consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise RuntimeError("Banco task014 recusado: URL não é PostgreSQL.")
    if parsed.host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Banco task014 recusado: a conexão precisa ser local.")
    if "task014" not in parsed.database.lower():
        raise RuntimeError("Banco task014 recusado: nome sem marcador descartável.")
    return url


def _alembic(url: str, *argumentos: str) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=ROOT,
        env={**os.environ, "ALEMBIC_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode:
        raise RuntimeError(
            f"alembic {' '.join(argumentos)} falhou sem exibir URL.\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    url = _url_autorizada()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    migrations_started = False
    schema_ready = False
    try:
        with engine.connect() as connection:
            comment, address = connection.execute(
                text(
                    "SELECT shobj_description(oid, 'pg_database'), "
                    "inet_server_addr()::text FROM pg_database "
                    "WHERE datname = current_database()"
                )
            ).one()
        if comment != COMENTARIO_BANCO or address is None:
            raise RuntimeError(
                "Banco task014 recusado antes de DDL: "
                "marcador/localidade não confirmados."
            )
        migrations_started = True
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        _alembic(url, "check")
        schema_ready = True
        yield engine
    finally:
        try:
            try:
                if schema_ready:
                    with engine.begin() as connection:
                        connection.execute(
                            text(
                                "TRUNCATE links_cadastro_web, "
                                "solicitacoes_cadastro_web, eventos_auditoria_web, "
                                "contas_web, turmas, alunos "
                                "RESTART IDENTITY CASCADE"
                            )
                        )
            finally:
                if migrations_started:
                    _alembic(url, "downgrade", "base")
        finally:
            engine.dispose()


def test_migration_e_revogacao_transacional_do_link(postgres_engine: Engine) -> None:
    with Session(postgres_engine) as session, session.begin():
        conta = models.ContaWeb(
            usuario_normalizado="professor",
            senha_hash="hash-sintetico",
            papel="professor",
            ativa=True,
            troca_senha_obrigatoria=False,
            versao_credencial=1,
            criado_em=AGORA,
        )
        session.add(conta)
        session.flush()
        professor = models.ProfessorWeb(conta_id=conta.id, criado_em=AGORA)
        session.add(professor)
        session.flush()
        turma = models.Turma(
            materia="Inteligência Artificial",
            periodo="noturno",
            responsavel_professor_id=professor.id,
            criado_em=AGORA,
            atualizado_em=AGORA,
        )
        session.add(turma)
        session.flush()
        conta_id = conta.id
        professor_id = professor.id
        turma_id = turma.id

    actor = AtorWeb(conta_id, "professor", True, False, professor_id)
    links = PostgresLinkRepository(postgres_engine)
    link = GerenciarLinks(links, relogio=lambda: AGORA).criar(
        actor, turma_id, finalidade_ate=AGORA + dt.timedelta(days=10)
    )
    access = GerenciarLinks(links, relogio=lambda: AGORA).trocar(link.token)
    assert access is not None
    request_repository = PostgresSolicitacaoRepository(postgres_engine)
    nonce_hash = hashlib.sha256(b"nonce-sintetico").hexdigest()
    request = SolicitarCadastroWeb(request_repository, relogio=lambda: AGORA).criar(
        DadosCadastroWeb("000123", "Pessoa Sintética"),
        ContextoConvite(
            referencia=str(access.link_id),
            turma_id=access.turma_id,
            expira_em=access.expira_em,
            finalidade_ate=access.finalidade_ate,
        ),
        ConsentimentoWeb(True, "aviso-v1"),
        credencial_acesso_hash=hashlib.sha256(access.credencial.encode()).hexdigest(),
        desafio_nonce_hash=nonce_hash,
        desafio_direcao="esquerda",
        desafio_expira_em=AGORA + dt.timedelta(seconds=120),
    )

    assert links.revogar(actor, link.id, agora=AGORA) == (1, (request.id,))
    with Session(postgres_engine) as session:
        saved = session.get(models.SolicitacaoCadastroWeb, request.id)
        stored_link = session.get(models.LinkCadastroWeb, link.id)
        audit = session.scalars(
            select(models.EventoAuditoriaWeb).where(
                models.EventoAuditoriaWeb.acao == "link_cadastro_web_revogado"
            )
        ).one()
        assert saved is not None and saved.estado == "cancelada"
        assert saved.desafio_nonce_hash == nonce_hash
        assert stored_link is not None and stored_link.token_hash != link.token
        assert audit.alvo_id == str(link.id)
        assert audit.depois == {"solicitacoes_canceladas": 1}
    assert (
        links.contexto_credencial(
            hashlib.sha256(access.credencial.encode()).hexdigest(),
            agora=AGORA,
            solicitacao_id=request.id,
            exigir_link_ativo=True,
        )
        is None
    )
