"""Persistencia de presencas em PostgreSQL."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, cast

from sqlalchemy import CursorResult, Engine, Select, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from src.domain.entities.turma import Periodo
from src.domain.errors import TurmaInativa, TurmaNaoEncontrada, VinculoInativo
from src.domain.repositories.presenca_repository import PresencaRegistrada
from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao

logger = logging.getLogger(__name__)


def _exigir_turma(
    session: Session, turma_id: int, *, ativa: bool, bloquear: bool = False
) -> models.Turma:
    consulta = select(models.Turma).where(models.Turma.id == turma_id)
    if bloquear:
        consulta = consulta.with_for_update()
    turma = session.scalar(consulta)
    if turma is None:
        raise TurmaNaoEncontrada(turma_id)
    if ativa and turma.excluida_em is not None:
        raise TurmaInativa(turma_id)
    return turma


def _presenca_registrada(linha: Row[Any]) -> PresencaRegistrada:
    aluno_id, matricula, nome, registrado_em, turma_id, materia, periodo = linha
    return PresencaRegistrada(
        aluno_id=int(cast(Any, aluno_id)),
        matricula=str(matricula),
        nome=str(nome),
        registrado_em=cast(dt.datetime, registrado_em),
        turma_id=int(cast(Any, turma_id)) if turma_id is not None else None,
        materia=str(materia) if materia is not None else None,
        periodo=Periodo(str(periodo)) if periodo is not None else None,
    )


class PostgresPresencaRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _consulta_base() -> Select[Any]:
        return (
            select(
                models.Aluno.id,
                models.Aluno.matricula,
                models.Aluno.nome,
                models.Presenca.registrado_em,
                models.Presenca.turma_id,
                models.Turma.materia,
                models.Turma.periodo,
            )
            .join(models.Presenca, models.Presenca.aluno_id == models.Aluno.id)
            .outerjoin(models.Turma, models.Turma.id == models.Presenca.turma_id)
        )

    def listar_da_turma(self, turma_id: int, dia: dt.date) -> list[PresencaRegistrada]:
        consulta = (
            self._consulta_base()
            .where(models.Presenca.turma_id == turma_id)
            .where(models.Presenca.data_referencia == dia)
            .order_by(models.Presenca.registrado_em, models.Presenca.id)
        )
        with sessao(self._engine) as session:
            _exigir_turma(session, turma_id, ativa=True)
            return [_presenca_registrada(linha) for linha in session.execute(consulta)]

    def listar_historico_da_turma(
        self, turma_id: int, dia: dt.date
    ) -> list[PresencaRegistrada]:
        consulta = (
            self._consulta_base()
            .where(models.Presenca.turma_id == turma_id)
            .where(models.Presenca.data_referencia == dia)
            .order_by(models.Presenca.registrado_em, models.Presenca.id)
        )
        with sessao(self._engine) as session:
            _exigir_turma(session, turma_id, ativa=False)
            return [_presenca_registrada(linha) for linha in session.execute(consulta)]

    def listar_legado(self, dia: dt.date) -> list[PresencaRegistrada]:
        consulta = (
            self._consulta_base()
            .where(models.Presenca.turma_id.is_(None))
            .where(models.Presenca.data_referencia == dia)
            .order_by(models.Presenca.registrado_em, models.Presenca.id)
        )
        with sessao(self._engine) as session:
            return [_presenca_registrada(linha) for linha in session.execute(consulta)]

    def registrar_se_ausente(
        self,
        aluno_id: int,
        dia: dt.date,
        momento: dt.datetime,
        *,
        turma_id: int,
    ) -> bool:
        with sessao(self._engine) as session:
            _exigir_turma(session, turma_id, ativa=True, bloquear=True)
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(models.AlunoTurma.turma_id == turma_id)
                .where(models.AlunoTurma.aluno_id == aluno_id)
                .with_for_update()
            )
            if vinculo is None or not vinculo.ativo:
                raise VinculoInativo(turma_id, aluno_id)

            comando = (
                pg_insert(models.Presenca)
                .values(
                    turma_id=turma_id,
                    aluno_id=aluno_id,
                    registrado_em=momento,
                    data_referencia=dia,
                )
                .on_conflict_do_nothing(constraint="uq_presencas_turma_aluno_dia")
                .returning(models.Presenca.id)
            )
            inserido = session.execute(comando).scalar()

        if inserido is None:
            logger.info(
                "Presenca ja registrada (aluno_id=%s turma_id=%s)",
                aluno_id,
                turma_id,
            )
            return False

        logger.info("Presenca registrada (aluno_id=%s turma_id=%s)", aluno_id, turma_id)
        return True

    def expurgar_anteriores_a(self, dia: dt.date) -> int:
        comando = delete(models.Presenca).where(models.Presenca.data_referencia < dia)
        with sessao(self._engine) as session:
            resultado = cast(CursorResult[Any], session.execute(comando))
            removidas = resultado.rowcount

        logger.info("Expurgo de presencas anteriores a %s: %s linhas", dia, removidas)
        return int(removidas)
