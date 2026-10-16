from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects import postgresql

from scripts.import_legacy_sqlite import _comando_presenca_legada


def test_importador_compila_conflito_apenas_para_indice_parcial_legado() -> None:
    comando = _comando_presenca_legada(
        7,
        dt.datetime(2026, 3, 10, 8, 0, tzinfo=dt.UTC),
        dt.date(2026, 3, 10),
    )

    sql = str(comando.compile(dialect=postgresql.dialect()))

    assert "turma_id" in sql
    assert "ON CONFLICT (aluno_id, data_referencia) WHERE turma_id IS NULL" in sql
    assert "uq_presencas_aluno_dia" not in sql
