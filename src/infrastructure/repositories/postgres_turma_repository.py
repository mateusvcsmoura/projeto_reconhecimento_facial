"""Persistencia transacional de turmas e vinculos no PostgreSQL."""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from src.domain.entities.aluno import Aluno
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import (
    AlunoNaoEncontrado,
    AlunoSemConsentimento,
    TurmaInativa,
    TurmaNaoEncontrada,
    VinculoNaoEncontrado,
)
from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao

logger = logging.getLogger(__name__)


def _para_aluno(linha: models.Aluno) -> Aluno:
    return Aluno(
        id=linha.id,
        matricula=linha.matricula,
        nome=linha.nome,
        foto_arquivo=linha.foto_arquivo,
        consentimento_em=linha.consentimento_em,
    )


def _para_turma(linha: models.Turma) -> Turma:
    return Turma(
        id=linha.id,
        materia=linha.materia,
        periodo=Periodo(linha.periodo),
        criado_em=linha.criado_em,
        atualizado_em=linha.atualizado_em,
        excluida_em=linha.excluida_em,
    )


def _exigir_turma_ativa(
    session: Session, turma_id: int, *, bloquear: bool = False
) -> models.Turma:
    consulta = select(models.Turma).where(models.Turma.id == turma_id)
    if bloquear:
        consulta = consulta.with_for_update()
    turma = session.scalar(consulta)
    if turma is None:
        raise TurmaNaoEncontrada(turma_id)
    if turma.excluida_em is not None:
        raise TurmaInativa(turma_id)
    return turma


class PostgresTurmaRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def criar(self, turma: Turma, agora: dt.datetime) -> Turma:
        linha = models.Turma(
            materia=turma.materia,
            periodo=turma.periodo.value,
            criado_em=agora,
            atualizado_em=agora,
        )
        with sessao(self._engine) as session:
            session.add(linha)
            session.flush()
            resultado = _para_turma(linha)
        logger.info("Turma criada (id=%s)", resultado.id)
        return resultado

    def listar_ativas(self) -> list[Turma]:
        with sessao(self._engine) as session:
            linhas = session.scalars(
                select(models.Turma)
                .where(models.Turma.excluida_em.is_(None))
                .order_by(models.Turma.id)
            ).all()
            return [_para_turma(linha) for linha in linhas]

    def listar_excluidas(self) -> list[Turma]:
        with sessao(self._engine) as session:
            linhas = session.scalars(
                select(models.Turma)
                .where(models.Turma.excluida_em.is_not(None))
                .order_by(models.Turma.id)
            ).all()
            return [_para_turma(linha) for linha in linhas]

    def obter(self, turma_id: int) -> Turma | None:
        with sessao(self._engine) as session:
            linha = session.scalar(
                select(models.Turma).where(models.Turma.id == turma_id)
            )
            return _para_turma(linha) if linha is not None else None

    def atualizar(
        self, turma_id: int, materia: str, periodo: Periodo, agora: dt.datetime
    ) -> Turma:
        turma_validada = Turma.nova(materia, periodo)
        with sessao(self._engine) as session:
            linha = _exigir_turma_ativa(session, turma_id, bloquear=True)
            linha.materia = turma_validada.materia
            linha.periodo = turma_validada.periodo.value
            linha.atualizado_em = agora
            session.flush()
            resultado = _para_turma(linha)
        logger.info("Turma atualizada (id=%s)", turma_id)
        return resultado

    def excluir_logicamente(self, turma_id: int, agora: dt.datetime) -> None:
        with sessao(self._engine) as session:
            linha = _exigir_turma_ativa(session, turma_id, bloquear=True)
            # Mesmo sem alterar vinculos, obter os locks nessa ordem mantem
            # exclusao, desvinculacao e presenca serializadas (turma -> aluno).
            session.scalars(
                select(models.AlunoTurma.aluno_id)
                .where(models.AlunoTurma.turma_id == turma_id)
                .order_by(models.AlunoTurma.aluno_id)
                .with_for_update()
            ).all()
            linha.excluida_em = agora
            linha.atualizado_em = agora
            session.flush()
        logger.info("Turma excluida logicamente (id=%s)", turma_id)

    def vincular_matricula(
        self, turma_id: int, matricula: str, agora: dt.datetime
    ) -> tuple[Aluno, bool]:
        with sessao(self._engine) as session:
            _exigir_turma_ativa(session, turma_id, bloquear=True)
            linha_aluno = session.scalar(
                select(models.Aluno).where(models.Aluno.matricula == matricula)
            )
            if linha_aluno is None:
                raise AlunoNaoEncontrado(matricula)
            if linha_aluno.consentimento_em is None:
                raise AlunoSemConsentimento(matricula)

            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(models.AlunoTurma.turma_id == turma_id)
                .where(models.AlunoTurma.aluno_id == linha_aluno.id)
                .with_for_update()
            )
            if vinculo is not None and vinculo.ativo:
                return _para_aluno(linha_aluno), False
            if vinculo is None:
                vinculo = models.AlunoTurma(
                    turma_id=turma_id,
                    aluno_id=linha_aluno.id,
                    ativo=True,
                    vinculado_em=agora,
                    desvinculado_em=None,
                )
                session.add(vinculo)
            else:
                vinculo.ativo = True
                vinculo.vinculado_em = agora
                vinculo.desvinculado_em = None
            session.flush()
            aluno = _para_aluno(linha_aluno)

        logger.info(
            "Aluno vinculado a turma (aluno_id=%s turma_id=%s)", aluno.id, turma_id
        )
        return aluno, True

    def desvincular_matricula(
        self, turma_id: int, matricula: str, agora: dt.datetime
    ) -> Aluno:
        with sessao(self._engine) as session:
            _exigir_turma_ativa(session, turma_id, bloquear=True)
            linha_aluno = session.scalar(
                select(models.Aluno).where(models.Aluno.matricula == matricula)
            )
            if linha_aluno is None:
                raise AlunoNaoEncontrado(matricula)
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(models.AlunoTurma.turma_id == turma_id)
                .where(models.AlunoTurma.aluno_id == linha_aluno.id)
                .with_for_update()
            )
            if vinculo is None or not vinculo.ativo:
                raise VinculoNaoEncontrado(turma_id, matricula)
            vinculo.ativo = False
            vinculo.desvinculado_em = agora
            session.flush()
            aluno = _para_aluno(linha_aluno)

        logger.info("Aluno desvinculado (aluno_id=%s turma_id=%s)", aluno.id, turma_id)
        return aluno
