"""Passos do cenario de banco (banco.feature).

Verificam que as regras estao no BANCO, e nao apenas na aplicacao: um bug
no codigo nao pode ser capaz de gravar registro invalido.
"""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pytest_bdd import given, parsers, scenarios, then, when
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

scenarios("banco.feature")

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
RAIZ = Path(__file__).resolve().parents[2]


def _alembic(*args: str, url: str) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=RAIZ,
        env={**os.environ, "ALEMBIC_DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stderr


@pytest.fixture
def contexto(banco_limpo: Engine, database_url: str) -> dict[str, Any]:
    return {"engine": banco_limpo, "url": database_url, "erro": None}


# -- Dado ------------------------------------------------------------------


@given("um banco PostgreSQL vazio")
def banco_vazio(contexto: dict[str, Any]) -> None:
    _alembic("downgrade", "base", url=contexto["url"])


@given("um banco com as migrations aplicadas")
def banco_migrado(contexto: dict[str, Any]) -> None:
    assert "alunos" in inspect(contexto["engine"]).get_table_names()


@given("um aluno com presencas registradas")
def aluno_com_presencas(contexto: dict[str, Any]) -> None:
    with contexto["engine"].begin() as conexao:
        aluno_id = conexao.execute(
            text(
                "INSERT INTO alunos (matricula, nome) VALUES ('1001', 'Ana')"
                " RETURNING id"
            )
        ).scalar_one()
        conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, :m, :d)"
            ),
            {"a": aluno_id, "m": AGORA, "d": AGORA.date()},
        )
    contexto["aluno_id"] = aluno_id


# -- Quando ----------------------------------------------------------------


@when("as migrations forem aplicadas")
def aplicar_migrations(contexto: dict[str, Any]) -> None:
    _alembic("upgrade", "head", url=contexto["url"])


@when("as migrations forem revertidas")
def reverter_migrations(contexto: dict[str, Any]) -> None:
    _alembic("downgrade", "base", url=contexto["url"])


@when("eu inserir dois alunos com a mesma matricula")
def inserir_matricula_duplicada(contexto: dict[str, Any]) -> None:
    with contexto["engine"].begin() as conexao:
        conexao.execute(
            text("INSERT INTO alunos (matricula, nome) VALUES ('1001', 'Ana')")
        )
    try:
        with contexto["engine"].begin() as conexao:
            conexao.execute(
                text("INSERT INTO alunos (matricula, nome) VALUES ('1001', 'Outro')")
            )
    except IntegrityError as erro:
        contexto["erro"] = erro


@when("eu inserir uma presenca para um aluno inexistente")
def inserir_presenca_orfa(contexto: dict[str, Any]) -> None:
    try:
        with contexto["engine"].begin() as conexao:
            conexao.execute(
                text(
                    "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                    " VALUES (999999, now(), CURRENT_DATE)"
                )
            )
    except IntegrityError as erro:
        contexto["erro"] = erro


@when("o aluno for excluido")
def excluir_aluno(contexto: dict[str, Any]) -> None:
    with contexto["engine"].begin() as conexao:
        conexao.execute(
            text("DELETE FROM alunos WHERE id = :a"), {"a": contexto["aluno_id"]}
        )


# -- Entao -----------------------------------------------------------------


@then(parsers.parse('as tabelas "{primeira}" e "{segunda}" devem existir'))
def tabelas_existem(contexto: dict[str, Any], primeira: str, segunda: str) -> None:
    tabelas = set(inspect(contexto["engine"]).get_table_names())
    assert {primeira, segunda} <= tabelas


@then("a constraint de presenca unica por dia deve existir")
def constraint_existe(contexto: dict[str, Any]) -> None:
    uniques = {
        u["name"]
        for u in inspect(contexto["engine"]).get_unique_constraints("presencas")
    }
    assert "uq_presencas_aluno_dia" in uniques


@then("o banco deve recusar o segundo")
@then("o banco deve recusar a insercao")
def banco_recusou(contexto: dict[str, Any]) -> None:
    assert isinstance(contexto["erro"], IntegrityError)


@then("as presencas dele devem desaparecer junto")
def presencas_removidas(contexto: dict[str, Any]) -> None:
    with contexto["engine"].connect() as conexao:
        total = conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one()
    assert total == 0


@then("as tabelas da aplicacao nao devem existir")
def tabelas_removidas(contexto: dict[str, Any]) -> None:
    tabelas = set(inspect(contexto["engine"]).get_table_names())
    assert "alunos" not in tabelas
    assert "presencas" not in tabelas
    # Restaura o schema para nao afetar os testes seguintes da sessao.
    _alembic("upgrade", "head", url=contexto["url"])
