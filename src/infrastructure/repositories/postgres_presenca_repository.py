"""Persistencia de presencas em PostgreSQL."""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import Engine, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao

logger = logging.getLogger(__name__)


class PostgresPresencaRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def registrar_se_ausente(
        self, aluno_id: int, dia: dt.date, momento: dt.datetime
    ) -> bool:
        comando = (
            pg_insert(models.Presenca.__table__)
            .values(aluno_id=aluno_id, registrado_em=momento, data_referencia=dia)
            .on_conflict_do_nothing(constraint="uq_presencas_aluno_dia")
            .returning(models.Presenca.__table__.c.id)
        )

        with sessao(self._engine) as session:
            inserido = session.execute(comando).scalar()

        if inserido is None:
            logger.info("Presenca ja registrada hoje (aluno_id=%s)", aluno_id)
            return False

        logger.info("Presenca registrada (aluno_id=%s)", aluno_id)
        return True

    def expurgar_anteriores_a(self, dia: dt.date) -> int:
        comando = delete(models.Presenca).where(
            models.Presenca.data_referencia < dia
        )
        with sessao(self._engine) as session:
            removidas = session.execute(comando).rowcount

        logger.info("Expurgo de presencas anteriores a %s: %s linhas", dia, removidas)
        return int(removidas)
