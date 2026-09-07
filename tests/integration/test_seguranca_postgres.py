"""Fase 6 -- exclusao em cascata, retencao e consentimento no PostgreSQL."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, text

from src.domain.entities.face_embedding import FaceEmbedding
from src.infrastructure.repositories.postgres_aluno_repository import (
    PostgresAlunoRepository,
)
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)

TZ = ZoneInfo("America/Sao_Paulo")
MODELO = "Facenet512"
AGORA = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)


@pytest.fixture
def alunos(banco_limpo: Engine) -> PostgresAlunoRepository:
    return PostgresAlunoRepository(banco_limpo)


@pytest.fixture
def presencas(banco_limpo: Engine) -> PostgresPresencaRepository:
    return PostgresPresencaRepository(banco_limpo)


# -- consentimento ---------------------------------------------------------


def test_consentimento_e_persistido(alunos: PostgresAlunoRepository) -> None:
    aluno = alunos.cadastrar("42", "Maria", None, None, AGORA)

    recuperado = alunos.obter_por_matricula("42")

    assert recuperado is not None
    assert recuperado.consentimento_em == AGORA
    assert aluno.consentimento_em == AGORA


def test_obter_por_matricula_inexistente_devolve_none(
    alunos: PostgresAlunoRepository,
) -> None:
    assert alunos.obter_por_matricula("999") is None


# -- exclusao --------------------------------------------------------------


def test_exclusao_leva_embedding_e_presencas_junto(
    alunos: PostgresAlunoRepository,
    presencas: PostgresPresencaRepository,
    banco_limpo: Engine,
) -> None:
    """A cascata e da constraint, nao de uma varredura da aplicacao."""
    embedding = FaceEmbedding.de_valores([1.0, 0.0, 0.0], MODELO)
    aluno = alunos.cadastrar("42", "Maria", "42.jpg", embedding, AGORA)
    presencas.registrar_se_ausente(aluno.id, AGORA.date(), AGORA)

    with banco_limpo.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one() == 1

    alunos.excluir(aluno.id)

    with banco_limpo.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM alunos")).scalar_one() == 0
        assert conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one() == 0
    assert alunos.listar_referencias(MODELO) == []


def test_exclusao_nao_afeta_os_demais_alunos(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    ana = alunos.cadastrar("1", "Ana", None, None, AGORA)
    bruno = alunos.cadastrar("2", "Bruno", None, None, AGORA)
    presencas.registrar_se_ausente(ana.id, AGORA.date(), AGORA)
    presencas.registrar_se_ausente(bruno.id, AGORA.date(), AGORA)

    alunos.excluir(ana.id)

    assert alunos.obter_por_matricula("2") is not None
    assert alunos.obter_por_matricula("1") is None


# -- retencao --------------------------------------------------------------


def test_expurgo_remove_apenas_o_que_excedeu_o_prazo(
    alunos: PostgresAlunoRepository,
    presencas: PostgresPresencaRepository,
    banco_limpo: Engine,
) -> None:
    aluno = alunos.cadastrar("42", "Maria", None, None, AGORA)
    for dia in (dt.date(2020, 1, 1), dt.date(2024, 6, 1), dt.date(2026, 3, 10)):
        momento = dt.datetime.combine(dia, dt.time(8, 0), tzinfo=TZ)
        presencas.registrar_se_ausente(aluno.id, dia, momento)

    removidas = presencas.expurgar_anteriores_a(dt.date(2025, 1, 1))

    assert removidas == 2
    with banco_limpo.connect() as conexao:
        restantes = conexao.execute(
            text("SELECT data_referencia FROM presencas")
        ).scalars().all()
    assert restantes == [dt.date(2026, 3, 10)]


def test_expurgo_sem_nada_a_remover_devolve_zero(
    presencas: PostgresPresencaRepository,
) -> None:
    assert presencas.expurgar_anteriores_a(dt.date(2020, 1, 1)) == 0


def test_expurgo_nao_apaga_o_aluno(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    """Retencao vale para o historico de presenca, nao para o cadastro."""
    aluno = alunos.cadastrar("42", "Maria", None, None, AGORA)
    dia = dt.date(2020, 1, 1)
    presencas.registrar_se_ausente(
        aluno.id, dia, dt.datetime.combine(dia, dt.time(8, 0), tzinfo=TZ)
    )

    presencas.expurgar_anteriores_a(dt.date(2025, 1, 1))

    assert alunos.obter_por_matricula("42") is not None
