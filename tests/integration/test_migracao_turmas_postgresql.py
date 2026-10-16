"""Validacao PostgreSQL da migration 0004 em banco dedicado e descartavel."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect, text

from src.infrastructure.database.engine import criar_engine

ROOT = Path(__file__).resolve().parents[2]


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
            f"alembic {' '.join(argumentos)} falhou: "
            f"{resultado.stdout}\n{resultado.stderr}"
        )


def _tabelas_do_projeto(engine: Engine) -> set[str]:
    nomes = set(inspect(engine).get_table_names())
    return nomes & {"presencas", "aluno_turma", "turmas", "alunos"}


@pytest.fixture
def banco_migration_0003(
    migration_database_url: str,
) -> Iterator[tuple[Engine, str, int, int, bytes]]:
    """Prepara sinteticos em 0003, testa 0004 e limpa so o DB opt-in marcado."""
    engine = criar_engine(migration_database_url)
    preparado = False
    try:
        existentes = _tabelas_do_projeto(engine)
        if existentes:
            with engine.begin() as conexao:
                lista = ", ".join(sorted(existentes))
                conexao.execute(text(f"TRUNCATE {lista} RESTART IDENTITY CASCADE"))
        _alembic(migration_database_url, "downgrade", "base")
        _alembic(migration_database_url, "upgrade", "0003")
        preparado = True

        embedding = bytes.fromhex("0000803f00000000")
        with engine.begin() as conexao:
            aluno_id = conexao.execute(
                text(
                    "INSERT INTO alunos "
                    "(matricula, nome, embedding, embedding_modelo, embedding_dim, "
                    "consentimento_em) "
                    "VALUES ('synthetic-1', 'Pessoa Sintetica', :embedding, "
                    "'Facenet512', 2, TIMESTAMPTZ '2026-03-10 08:00:00-03') "
                    "RETURNING id"
                ),
                {"embedding": embedding},
            ).scalar_one()
            presenca_id = conexao.execute(
                text(
                    "INSERT INTO presencas "
                    "(aluno_id, registrado_em, data_referencia) "
                    "VALUES (:aluno, TIMESTAMPTZ '2026-03-10 08:00:00-03', "
                    "DATE '2026-03-10') RETURNING id"
                ),
                {"aluno": aluno_id},
            ).scalar_one()

        yield engine, migration_database_url, aluno_id, presenca_id, embedding
    finally:
        if preparado:
            existentes = _tabelas_do_projeto(engine)
            if existentes:
                with engine.begin() as conexao:
                    lista = ", ".join(sorted(existentes))
                    conexao.execute(text(f"TRUNCATE {lista} RESTART IDENTITY CASCADE"))
            _alembic(migration_database_url, "downgrade", "base")
        engine.dispose()


def test_upgrade_preserva_presencas_legadas_e_downgrade_recusa_dados_novos(
    banco_migration_0003: tuple[Engine, str, int, int, bytes],
) -> None:
    engine, url, aluno_id, presenca_id, embedding = banco_migration_0003
    with engine.connect() as conexao:
        antes = conexao.execute(
            text(
                "SELECT a.id, a.matricula, a.embedding, a.embedding_modelo, "
                "a.embedding_dim, a.consentimento_em, p.id, p.registrado_em, "
                "p.data_referencia FROM alunos a JOIN presencas p ON p.aluno_id=a.id"
            )
        ).one()

    _alembic(url, "upgrade", "0004")

    with engine.begin() as conexao:
        depois = conexao.execute(
            text(
                "SELECT a.id, a.matricula, a.embedding, a.embedding_modelo, "
                "a.embedding_dim, a.consentimento_em, p.id, p.registrado_em, "
                "p.data_referencia, p.turma_id FROM alunos a "
                "JOIN presencas p ON p.aluno_id=a.id"
            )
        ).one()
        assert depois[:9] == antes
        assert depois[9] is None
        turma_id = conexao.execute(
            text(
                "INSERT INTO turmas (materia, periodo) "
                "VALUES ('IA sintetica', 'diurno') RETURNING id"
            )
        ).scalar_one()
        conexao.execute(
            text(
                "INSERT INTO aluno_turma "
                "(turma_id, aluno_id, ativo, vinculado_em) "
                "VALUES (:turma, :aluno, true, now())"
            ),
            {"turma": turma_id, "aluno": aluno_id},
        )
        conexao.execute(
            text(
                "INSERT INTO presencas "
                "(aluno_id, turma_id, registrado_em, data_referencia) "
                "VALUES (:aluno, :turma, now(), DATE '2026-03-11')"
            ),
            {"aluno": aluno_id, "turma": turma_id},
        )

    with pytest.raises(RuntimeError, match="downgrade 0003 falhou"):
        _alembic(url, "downgrade", "0003")

    with engine.connect() as conexao:
        assert conexao.execute(text("SELECT count(*) FROM turmas")).scalar_one() == 1
        assert (
            conexao.execute(
                text("SELECT count(*) FROM presencas WHERE turma_id IS NOT NULL")
            ).scalar_one()
            == 1
        )
        linha = conexao.execute(
            text("SELECT embedding FROM alunos WHERE id=:id"), {"id": aluno_id}
        ).scalar_one()
        assert linha == embedding
        assert (
            conexao.execute(
                text("SELECT count(*) FROM presencas WHERE id=:id"),
                {"id": presenca_id},
            ).scalar_one()
            == 1
        )
