from __future__ import annotations

import importlib.util
from io import StringIO
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations


def _carregar_migration():
    caminho = Path(__file__).parents[2] / "migrations" / "versions" / "0004_turmas.py"
    spec = importlib.util.spec_from_file_location("migration_0004_turmas", caminho)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_upgrade_compila_ddl_postgresql_sem_conexao() -> None:
    migration = _carregar_migration()
    saida = StringIO()
    contexto = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": saida},
    )

    with Operations.context(contexto):
        migration.upgrade()

    sql = saida.getvalue()
    assert "CREATE TABLE turmas" in sql
    assert "CREATE TABLE aluno_turma" in sql
    assert "ADD COLUMN turma_id BIGINT" in sql
    assert "CREATE UNIQUE INDEX uq_presencas_legado_aluno_dia" in sql
    assert "uq_presencas_turma_aluno_dia" in sql
    assert sql.index("CREATE UNIQUE INDEX uq_presencas_legado_aluno_dia") < sql.index(
        "DROP CONSTRAINT uq_presencas_aluno_dia"
    )


def test_downgrade_com_dados_novos_aborta_antes_de_qualquer_ddl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = _carregar_migration()
    ddl: list[str] = []

    class Resultado:
        def scalar_one(self) -> bool:
            return True

    class Conexao:
        def execute(self, comando: object) -> Resultado:
            return Resultado()

    monkeypatch.setattr(migration.op, "get_bind", lambda: Conexao())
    for nome in (
        "create_unique_constraint",
        "drop_index",
        "drop_constraint",
        "drop_column",
        "drop_table",
    ):
        monkeypatch.setattr(
            migration.op,
            nome,
            lambda *args, _nome=nome, **kwargs: ddl.append(_nome),
        )

    with pytest.raises(RuntimeError, match="dados de turmas"):
        migration.downgrade()

    assert ddl == []
