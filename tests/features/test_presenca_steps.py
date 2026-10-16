"""Passos do cenario de presenca (presenca.feature).

Rodam contra PostgreSQL real: a regra "uma presenca por dia" e garantida
pela constraint do banco, entao testa-la com duble provaria menos.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import Engine

from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import VinculoInativo
from src.infrastructure.repositories.postgres_aluno_repository import (
    PostgresAlunoRepository,
)
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)
from src.infrastructure.repositories.postgres_turma_repository import (
    PostgresTurmaRepository,
)

scenarios("presenca.feature")

TZ = ZoneInfo("America/Sao_Paulo")
HOJE = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)


@pytest.fixture
def contexto(banco_limpo: Engine) -> dict[str, Any]:
    return {
        "alunos": PostgresAlunoRepository(banco_limpo),
        "presencas": PostgresPresencaRepository(banco_limpo),
        "turmas": PostgresTurmaRepository(banco_limpo),
        "turma_id": None,
        "aluno": None,
        "registrou": None,
        "erro": None,
    }


def _turma_id(contexto: dict[str, Any]) -> int:
    if contexto["turma_id"] is None:
        turma = contexto["turmas"].criar(Turma.nova("IA BDD", Periodo.DIURNO), HOJE)
        assert turma.id is not None
        contexto["turma_id"] = turma.id
    return contexto["turma_id"]


@given("que o sistema esta operacional")
def sistema_operacional(contexto: dict[str, Any]) -> None:
    assert contexto["alunos"] is not None


@given(parsers.parse('que o aluno "{nome}" esta cadastrado'))
def aluno_cadastrado(contexto: dict[str, Any], nome: str) -> None:
    contexto["aluno"] = contexto["alunos"].cadastrar_em_turma(
        _turma_id(contexto), "1001", nome, None, None, HOJE
    )


@given("que nenhum aluno esta cadastrado")
def nenhum_aluno(contexto: dict[str, Any]) -> None:
    contexto["aluno"] = None


@given(parsers.parse('que a presenca de "{nome}" ja foi registrada hoje'))
def presenca_de_hoje(contexto: dict[str, Any], nome: str) -> None:
    contexto["presencas"].registrar_se_ausente(
        contexto["aluno"].id, HOJE.date(), HOJE, turma_id=_turma_id(contexto)
    )


@given(parsers.parse('que a presenca de "{nome}" foi registrada ontem'))
def presenca_de_ontem(contexto: dict[str, Any], nome: str) -> None:
    ontem = HOJE - dt.timedelta(days=1)
    contexto["presencas"].registrar_se_ausente(
        contexto["aluno"].id, ontem.date(), ontem, turma_id=_turma_id(contexto)
    )


@when(parsers.parse('o operador confirmar a presenca de "{nome}"'))
def confirmar_presenca(contexto: dict[str, Any], nome: str) -> None:
    caso = RegistrarPresenca(contexto["presencas"], TZ)
    contexto["registrou"] = caso.executar(
        contexto["aluno"].id, turma_id=_turma_id(contexto), agora=HOJE
    )


@when("o operador confirmar a presenca de um aluno inexistente")
def confirmar_inexistente(contexto: dict[str, Any]) -> None:
    caso = RegistrarPresenca(contexto["presencas"], TZ)
    try:
        caso.executar(999999, turma_id=_turma_id(contexto), agora=HOJE)
    except Exception as erro:
        contexto["erro"] = erro


@then("a presenca deve ser registrada")
def presenca_registrada(contexto: dict[str, Any]) -> None:
    assert contexto["registrou"] is True


@then("nenhuma nova presenca deve ser registrada")
def presenca_nao_duplicada(contexto: dict[str, Any]) -> None:
    assert contexto["registrou"] is False


@then("o operador deve ser informado de que a presenca ja existe")
def operador_informado(contexto: dict[str, Any]) -> None:
    # O caso de uso comunica isso pelo valor de retorno; a CLI o traduz em
    # "Presenca ja registrada hoje", coberto em tests/unit/test_menu.py.
    assert contexto["registrou"] is False


@then("o registro deve falhar porque o aluno nao pertence a turma")
def falha_por_vinculo(contexto: dict[str, Any]) -> None:
    assert isinstance(contexto["erro"], VinculoInativo)
