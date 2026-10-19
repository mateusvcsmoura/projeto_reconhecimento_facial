"""Fase 1 -- schema PostgreSQL e migrations.

Estes testes existem porque o prototipo tinha o defeito oposto: o schema
era criado pela aplicacao com CREATE TABLE IF NOT EXISTS, e por isso o
banco real divergia silenciosamente do que o codigo declarava.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from src.infrastructure.database.models import Base


def test_migration_cria_as_tabelas_esperadas(engine: Engine) -> None:
    tabelas = set(inspect(engine).get_table_names())
    assert {"alunos", "presencas", "turmas", "aluno_turma"} <= tabelas


def test_schema_do_banco_bate_com_os_modelos(engine: Engine) -> None:
    """Sem divergencia entre codigo e banco -- o problema P1 do baseline."""
    inspetor = inspect(engine)
    for tabela in ("alunos", "presencas", "turmas", "aluno_turma"):
        colunas_banco = {c["name"] for c in inspetor.get_columns(tabela)}
        colunas_modelo = set(Base.metadata.tables[tabela].columns.keys())
        assert colunas_banco == colunas_modelo, tabela


def test_chaves_primarias_sao_identity(engine: Engine) -> None:
    with engine.connect() as conexao:
        resultado = conexao.execute(
            text(
                """
                SELECT table_name, is_identity
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND column_name = 'id'
                  AND table_name IN ('alunos', 'presencas', 'turmas')
                """
            )
        ).all()
    assert {(linha[0], linha[1]) for linha in resultado} == {
        ("alunos", "YES"),
        ("presencas", "YES"),
        ("turmas", "YES"),
    }


def test_constraints_esperadas_existem(engine: Engine) -> None:
    inspetor = inspect(engine)

    uniques_alunos = {u["name"] for u in inspetor.get_unique_constraints("alunos")}
    assert "uq_alunos_matricula" in uniques_alunos

    uniques_presencas = {
        u["name"] for u in inspetor.get_unique_constraints("presencas")
    }
    assert "uq_presencas_aluno_dia" not in uniques_presencas
    assert "uq_presencas_turma_aluno_dia" not in uniques_presencas

    checks_alunos = {c["name"] for c in inspetor.get_check_constraints("alunos")}
    assert {
        "ck_alunos_nome_nao_vazio",
        "ck_alunos_matricula_nao_vazia",
    } <= checks_alunos

    fks = inspetor.get_foreign_keys("presencas")
    assert {fk["referred_table"] for fk in fks} == {"alunos", "turmas", "aluno_turma"}
    fk_aluno = next(fk for fk in fks if fk["referred_table"] == "alunos")
    assert fk_aluno["options"]["ondelete"] == "CASCADE"

    indices = {i["name"] for i in inspetor.get_indexes("presencas")}
    assert {
        "ix_presencas_data_referencia",
        "ix_presencas_turma_data",
        "uq_presencas_turma_aluno_dia",
        "uq_presencas_legado_aluno_dia",
        "uq_presencas_sessao_aluno",
    } <= indices


def test_matricula_duplicada_e_rejeitada(banco_limpo: Engine) -> None:
    with banco_limpo.begin() as conexao:
        conexao.execute(
            text("INSERT INTO alunos (matricula, nome) VALUES ('100', 'Aluno Um')")
        )
    with pytest.raises(IntegrityError), banco_limpo.begin() as conexao:
        conexao.execute(
            text("INSERT INTO alunos (matricula, nome) VALUES ('100', 'Outro')")
        )


def test_nome_vazio_e_rejeitado(banco_limpo: Engine) -> None:
    with pytest.raises(IntegrityError), banco_limpo.begin() as conexao:
        conexao.execute(
            text("INSERT INTO alunos (matricula, nome) VALUES ('101', '   ')")
        )


def test_presenca_orfa_e_rejeitada(banco_limpo: Engine) -> None:
    """A FK que o SQLite nunca teve (PRAGMA foreign_keys estava desligado)."""
    with pytest.raises(IntegrityError), banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (999999, now(), CURRENT_DATE)"
            )
        )


def test_segunda_presenca_no_mesmo_dia_e_rejeitada(banco_limpo: Engine) -> None:
    """Sem turma, a unicidade parcial protege apenas registros legados."""
    with banco_limpo.begin() as conexao:
        aluno_id = conexao.execute(
            text(
                "INSERT INTO alunos (matricula, nome) VALUES ('200', 'Aluno Dois')"
                " RETURNING id"
            )
        ).scalar_one()
        conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, now(), DATE '2026-03-10')"
            ),
            {"a": aluno_id},
        )

    with pytest.raises(IntegrityError), banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, now(), DATE '2026-03-10')"
            ),
            {"a": aluno_id},
        )


def test_on_conflict_do_nothing_nao_duplica(banco_limpo: Engine) -> None:
    """O caminho explicito legado usa o indice parcial por conflito."""
    with banco_limpo.begin() as conexao:
        aluno_id = conexao.execute(
            text(
                "INSERT INTO alunos (matricula, nome) VALUES ('201', 'Aluno')"
                " RETURNING id"
            )
        ).scalar_one()

        primeiro = conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, now(), DATE '2026-03-10')"
                " ON CONFLICT (aluno_id, data_referencia)"
                " WHERE sessao_id IS NULL AND turma_id IS NULL DO NOTHING"
                " RETURNING id"
            ),
            {"a": aluno_id},
        ).scalar()
        segundo = conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, now(), DATE '2026-03-10')"
                " ON CONFLICT (aluno_id, data_referencia)"
                " WHERE sessao_id IS NULL AND turma_id IS NULL DO NOTHING"
                " RETURNING id"
            ),
            {"a": aluno_id},
        ).scalar()
        total = conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one()

    assert primeiro is not None
    assert segundo is None
    assert total == 1


def test_exclusao_de_aluno_remove_presencas_em_cascata(banco_limpo: Engine) -> None:
    with banco_limpo.begin() as conexao:
        aluno_id = conexao.execute(
            text(
                "INSERT INTO alunos (matricula, nome) VALUES ('202', 'Aluno')"
                " RETURNING id"
            )
        ).scalar_one()
        conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, now(), DATE '2026-03-10')"
            ),
            {"a": aluno_id},
        )
        conexao.execute(text("DELETE FROM alunos WHERE id = :a"), {"a": aluno_id})
        restantes = conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one()

    assert restantes == 0


def test_registrado_em_preserva_o_fuso(banco_limpo: Engine) -> None:
    """TIMESTAMPTZ, nao TEXT: o defeito de formato de data nao pode voltar."""
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=dt.timezone(dt.timedelta(hours=-3)))
    with banco_limpo.begin() as conexao:
        aluno_id = conexao.execute(
            text(
                "INSERT INTO alunos (matricula, nome) VALUES ('203', 'Aluno')"
                " RETURNING id"
            )
        ).scalar_one()
        conexao.execute(
            text(
                "INSERT INTO presencas (aluno_id, registrado_em, data_referencia)"
                " VALUES (:a, :m, DATE '2026-03-10')"
            ),
            {"a": aluno_id, "m": momento},
        )
        lido = conexao.execute(text("SELECT registrado_em FROM presencas")).scalar_one()

    assert lido == momento
