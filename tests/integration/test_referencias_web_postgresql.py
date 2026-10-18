"""Migração e concorrência reais da task011, apenas em PostgreSQL descartável."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.application.use_cases.aprovar_cadastro_web import AprovarCadastroWeb
from src.application.use_cases.solicitar_cadastro_web import (
    ConsentimentoWeb,
    ContextoConvite,
    DadosCadastroWeb,
    SolicitarCadastroWeb,
)
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.referencia_facial import (
    PreparacaoReferencia,
    ReferenciaParaPersistir,
)
from src.domain.services.autorizacao import AtorWeb
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    PostgresSolicitacaoRepository,
)

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_REFERENCES_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_REFERENCES_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_011"
COMENTARIO_BANCO = (
    "projeto_reconhecimento_facial: task 011 disposable references database"
)
UTC = ZoneInfo("UTC")
AGORA = dt.datetime(2026, 10, 18, 12, tzinfo=UTC)


class _StorageFake:
    def salvar(self, solicitacao_id: int, ordinal: int, recorte: bytes) -> str:
        return f"synthetic/{solicitacao_id}/{ordinal}.bin"

    def remover(self, caminho_relativo: str) -> None:
        assert caminho_relativo.startswith("synthetic/")


def _url_autorizada() -> str:
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("PostgreSQL task011 exige opt-in para banco descartável.")
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} não definida; nenhum .env será consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise RuntimeError("Banco task011 recusado: URL não é PostgreSQL.")
    if parsed.host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Banco task011 recusado: a conexão precisa ser local.")
    if not any(marcador in parsed.database.lower() for marcador in ("test", "task011")):
        raise RuntimeError("Banco task011 recusado: nome sem marcador descartável.")
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


def _limpar(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE referencias_faciais_web, conjuntos_referencias_web, "
                "solicitacoes_cadastro_web, eventos_auditoria_web, "
                "limites_login_web, sessoes_autenticacao_web, professores_web, "
                "contas_web, presencas, aluno_turma, turmas, alunos "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    url = _url_autorizada()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    schema_preparado = False
    try:
        with engine.connect() as connection:
            comentario, endereco = connection.execute(
                text(
                    "SELECT shobj_description(oid, 'pg_database'), "
                    "inet_server_addr()::text FROM pg_database "
                    "WHERE datname = current_database()"
                )
            ).one()
        if comentario != COMENTARIO_BANCO:
            raise RuntimeError(
                "Banco task011 recusado antes do DDL: marcador descartável ausente."
            )
        if endereco is None:
            raise RuntimeError(
                "Banco task011 recusado: não foi possível confirmar o servidor local."
            )
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        schema_preparado = True
        _alembic(url, "check")
        yield engine
    finally:
        try:
            if schema_preparado:
                _limpar(engine)
                _alembic(url, "downgrade", "base")
        finally:
            engine.dispose()


@pytest.fixture(autouse=True)
def banco_limpo(postgres_engine: Engine) -> None:
    _limpar(postgres_engine)


def _preparacoes(sufixo: str) -> tuple[PreparacaoReferencia, ...]:
    return tuple(
        PreparacaoReferencia(
            ordinal=ordinal,
            captura_id=f"{sufixo}-{ordinal}",
            recorte=f"recorte-sintetico-{sufixo}-{ordinal}".encode(),
            embedding=FaceEmbedding.de_valores(
                np.arange(1, 513, dtype=np.float32) + ordinal,
                "FaceNet512",
            ),
        )
        for ordinal in (1, 2, 3)
    )


def _preparar_cadastro(
    repo: PostgresSolicitacaoRepository,
    turma_id: int,
    matricula: str,
    nome: str,
    sufixo: str,
) -> int:
    solicitacao = SolicitarCadastroWeb(repo, relogio=lambda: AGORA).criar(
        DadosCadastroWeb(matricula=matricula, nome=nome),
        ContextoConvite(
            referencia=f"convite-opaco-{sufixo}",
            turma_id=turma_id,
            expira_em=AGORA + dt.timedelta(days=4),
        ),
        ConsentimentoWeb(aceito=True, versao="termos-sinteticos-v1"),
    )
    refs = tuple(
        ReferenciaParaPersistir(
            ordinal=preparacao.ordinal,
            caminho_privado_relativo=f"synthetic/{solicitacao.id}/{preparacao.ordinal}.bin",
            embedding=preparacao.embedding,
        )
        for preparacao in _preparacoes(sufixo)
    )
    repo.anexar_referencias(
        solicitacao.id,
        job_id=uuid.uuid4(),
        referencias=refs,
        consentimento_em=AGORA,
        consentimento_versao="termos-sinteticos-v1",
        agora=AGORA,
    )
    return solicitacao.id


def test_migration_0006_cria_schema_e_indice_unico_ativo(
    postgres_engine: Engine,
) -> None:
    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0006"
        )
        indices = connection.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'conjuntos_referencias_web' "
                "AND indexname = 'uq_conjuntos_referencias_web_aluno_ativo'"
            )
        ).scalar_one()
    assert "UNIQUE INDEX" in indices
    assert "WHERE" in indices
    assert "ativo" in indices


def test_downgrade_recusa_remover_solicitacao_persistida(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        turma = models.Turma(materia="Turma sintética", periodo="diurno")
        session.add(turma)
        session.flush()
        session.add(
            models.SolicitacaoCadastroWeb(
                tipo="cadastro",
                estado="em_coleta",
                convite_ref="referencia-opaca-sintetica",
                turma_id=turma.id,
                matricula="000-migration",
                nome="Pessoa Sintética",
                consentimento_em=AGORA,
                consentimento_versao="termos-sinteticos-v1",
                expira_em=AGORA + dt.timedelta(days=1),
                criada_em=AGORA,
            )
        )
        session.commit()

    with pytest.raises(RuntimeError, match="Downgrade recusado"):
        _alembic(_url_autorizada(), "downgrade", "0005")

    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0006"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM solicitacoes_cadastro_web")
            ).scalar_one()
            == 1
        )


def test_corrida_de_aprovacao_nao_substitui_aluno_existente(
    postgres_engine: Engine,
) -> None:
    with Session(postgres_engine) as session:
        admin = models.ContaWeb(
            usuario_normalizado="admin",
            senha_hash="hash-sintetico",
            papel="admin",
            ativa=True,
            troca_senha_obrigatoria=False,
        )
        contas = [
            models.ContaWeb(
                usuario_normalizado=f"professor-{indice}",
                senha_hash="hash-sintetico",
                papel="professor",
                ativa=True,
                troca_senha_obrigatoria=False,
            )
            for indice in (1, 2)
        ]
        session.add_all([admin, *contas])
        session.flush()
        professores = [models.ProfessorWeb(conta_id=conta.id) for conta in contas]
        session.add_all(professores)
        session.flush()
        turmas = [
            models.Turma(
                materia=f"IA {indice}",
                periodo="diurno",
                responsavel_professor_id=professor.id,
            )
            for indice, professor in enumerate(professores, start=1)
        ]
        session.add_all(turmas)
        session.commit()
        professor_ids = [professor.id for professor in professores]
        turma_ids = [turma.id for turma in turmas]
        conta_ids = [conta.id for conta in contas]

    repo = PostgresSolicitacaoRepository(postgres_engine)
    solicitacao_ids = [
        _preparar_cadastro(repo, turma_ids[i], "000-race", f"Nome {i}", f"race-{i}")
        for i in range(2)
    ]
    barreira = threading.Barrier(2)

    def aprovar(indice: int):
        ator = AtorWeb(
            conta_ids[indice], "professor", True, False, professor_ids[indice]
        )
        caso = AprovarCadastroWeb(repo, _StorageFake(), relogio=lambda: AGORA)
        barreira.wait(timeout=5)
        return caso.executar(
            ator,
            solicitacao_ids[indice],
            "documento_presencial",
            "Conferência independente de identidade",
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(aprovar, range(2)))

    assert len({resultado.aluno_id for resultado in resultados}) == 1
    assert sorted(resultado.aluno_existente for resultado in resultados) == [
        False,
        True,
    ]
    with Session(postgres_engine) as session:
        aluno = session.scalar(
            select(models.Aluno).where(models.Aluno.matricula == "000-race")
        )
        assert aluno is not None
        assert aluno.nome in ("Nome 0", "Nome 1")
        assert aluno.embedding is None and aluno.foto_arquivo is None
        assert (
            session.scalar(
                select(func.count(models.AlunoTurma.aluno_id)).where(
                    models.AlunoTurma.aluno_id == aluno.id,
                    models.AlunoTurma.ativo.is_(True),
                )
            )
            == 2
        )
