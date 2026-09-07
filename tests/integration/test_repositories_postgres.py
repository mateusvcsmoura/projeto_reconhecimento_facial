"""Fase 2 -- repositories contra PostgreSQL real.

Os testes unitarios provam a regra com dubles; estes provam que a
implementacao concreta honra o mesmo contrato.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine, text

from src.domain.errors import AlunoJaCadastrado
from src.infrastructure.repositories.postgres_aluno_repository import (
    PostgresAlunoRepository,
)
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)

TZ = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def alunos(banco_limpo: Engine) -> PostgresAlunoRepository:
    return PostgresAlunoRepository(banco_limpo)


@pytest.fixture
def presencas(banco_limpo: Engine) -> PostgresPresencaRepository:
    return PostgresPresencaRepository(banco_limpo)


# -- alunos ----------------------------------------------------------------


def test_cadastrar_devolve_o_id_gerado_pelo_banco(
    alunos: PostgresAlunoRepository,
) -> None:
    aluno = alunos.cadastrar(matricula="42", nome="Maria Silva", foto_arquivo="42.jpg")

    assert aluno.id > 0
    assert aluno.matricula == "42"
    assert aluno.foto_arquivo == "42.jpg"


def test_matricula_duplicada_vira_erro_de_dominio(
    alunos: PostgresAlunoRepository,
) -> None:
    """A IntegrityError do banco nao vaza para as camadas de cima."""
    alunos.cadastrar("42", "Maria", None)

    with pytest.raises(AlunoJaCadastrado) as capturado:
        alunos.cadastrar("42", "Outro", None)

    assert capturado.value.matricula == "42"


def test_existe_matricula(alunos: PostgresAlunoRepository) -> None:
    alunos.cadastrar("42", "Maria", None)

    assert alunos.existe_matricula("42") is True
    assert alunos.existe_matricula("43") is False


def test_listar_vem_ordenado_por_nome(alunos: PostgresAlunoRepository) -> None:
    alunos.cadastrar("2", "Bruno", None)
    alunos.cadastrar("1", "Ana", None)

    assert [a.nome for a in alunos.listar()] == ["Ana", "Bruno"]


def test_listar_sem_alunos_devolve_lista_vazia(
    alunos: PostgresAlunoRepository,
) -> None:
    assert alunos.listar() == []


def test_aluno_sem_foto_vem_com_foto_arquivo_nulo(
    alunos: PostgresAlunoRepository,
) -> None:
    alunos.cadastrar("42", "Maria", None)
    assert alunos.listar()[0].foto_arquivo is None


def test_entidade_devolvida_nao_carrega_sqlalchemy(
    alunos: PostgresAlunoRepository,
) -> None:
    """A fronteira devolve dataclass pura, nao objeto de sessao."""
    aluno = alunos.cadastrar("42", "Maria", None)
    assert type(aluno).__module__.startswith("src.domain")


# -- presencas -------------------------------------------------------------


def test_primeira_presenca_do_dia_e_inserida(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    aluno = alunos.cadastrar("42", "Maria", None)
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)

    assert presencas.registrar_se_ausente(aluno.id, momento.date(), momento) is True


def test_segunda_presenca_no_mesmo_dia_devolve_false(
    alunos: PostgresAlunoRepository,
    presencas: PostgresPresencaRepository,
    banco_limpo: Engine,
) -> None:
    """A constraint do banco resolve, sem SELECT previo e sem corrida."""
    aluno = alunos.cadastrar("42", "Maria", None)
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)

    assert presencas.registrar_se_ausente(aluno.id, momento.date(), momento) is True
    assert (
        presencas.registrar_se_ausente(
            aluno.id, momento.date(), momento.replace(hour=17)
        )
        is False
    )

    with banco_limpo.connect() as conexao:
        total = conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one()
    assert total == 1


def test_dias_diferentes_geram_duas_presencas(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    aluno = alunos.cadastrar("42", "Maria", None)

    for dia in (dt.date(2026, 3, 10), dt.date(2026, 3, 11)):
        momento = dt.datetime.combine(dia, dt.time(8, 0), tzinfo=TZ)
        assert presencas.registrar_se_ausente(aluno.id, dia, momento) is True


def test_alunos_diferentes_no_mesmo_dia_nao_se_bloqueiam(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    ana = alunos.cadastrar("1", "Ana", None)
    bruno = alunos.cadastrar("2", "Bruno", None)
    dia = dt.date(2026, 3, 10)
    momento = dt.datetime.combine(dia, dt.time(8, 0), tzinfo=TZ)

    assert presencas.registrar_se_ausente(ana.id, dia, momento) is True
    assert presencas.registrar_se_ausente(bruno.id, dia, momento) is True


def test_instante_gravado_preserva_o_fuso(
    alunos: PostgresAlunoRepository,
    presencas: PostgresPresencaRepository,
    banco_limpo: Engine,
) -> None:
    aluno = alunos.cadastrar("42", "Maria", None)
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
    presencas.registrar_se_ausente(aluno.id, momento.date(), momento)

    with banco_limpo.connect() as conexao:
        gravado = conexao.execute(
            text("SELECT registrado_em FROM presencas")
        ).scalar_one()

    assert gravado == momento
