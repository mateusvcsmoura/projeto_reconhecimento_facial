from __future__ import annotations

import importlib
from typing import Any

import pytest

MIGRATION = "migrations.versions.0008_desafio_verificacao_web"


class ResultadoExistencia:
    @staticmethod
    def scalar_one() -> bool:
        return True


class ConexaoComDesafioPendente:
    @staticmethod
    def execute(_statement: Any) -> ResultadoExistencia:
        return ResultadoExistencia()


def test_downgrade_recusa_remover_desafios_persistidos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = importlib.import_module(MIGRATION)
    operacoes: list[str] = []
    monkeypatch.setattr(migration.op, "get_bind", lambda: ConexaoComDesafioPendente())
    monkeypatch.setattr(
        migration.op, "drop_index", lambda *_args, **_kwargs: operacoes.append("index")
    )
    monkeypatch.setattr(
        migration.op, "drop_table", lambda *_args, **_kwargs: operacoes.append("table")
    )

    with pytest.raises(RuntimeError, match="desafios persistidos"):
        migration.downgrade()

    assert operacoes == []
