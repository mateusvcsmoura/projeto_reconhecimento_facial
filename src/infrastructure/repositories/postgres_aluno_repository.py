"""Persistencia de alunos em PostgreSQL.

Todo o SQL do sistema vive aqui e no repositorio de presencas. Nenhum
caso de uso executa SQL (instructions/02-desenvolvedor.md, secao 4).
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    AlunoJaCadastrado,
    TurmaInativa,
    TurmaNaoEncontrada,
)
from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao

logger = logging.getLogger(__name__)


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


def _para_entidade(linha: models.Aluno) -> Aluno:
    return Aluno(
        id=linha.id,
        matricula=linha.matricula,
        nome=linha.nome,
        foto_arquivo=linha.foto_arquivo,
        consentimento_em=linha.consentimento_em,
    )


class PostgresAlunoRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def validar_turma_ativa(self, turma_id: int) -> None:
        with sessao(self._engine) as session:
            _exigir_turma_ativa(session, turma_id)

    def existe_matricula_global(self, matricula: str) -> bool:
        with sessao(self._engine) as session:
            encontrado = session.scalar(
                select(models.Aluno.id).where(models.Aluno.matricula == matricula)
            )
        return encontrado is not None

    def obter_global_por_matricula(self, matricula: str) -> Aluno | None:
        with sessao(self._engine) as session:
            linha = session.scalar(
                select(models.Aluno).where(models.Aluno.matricula == matricula)
            )
            return _para_entidade(linha) if linha is not None else None

    def listar_por_turma(self, turma_id: int) -> list[Aluno]:
        with sessao(self._engine) as session:
            _exigir_turma_ativa(session, turma_id)
            linhas = session.scalars(
                select(models.Aluno)
                .join(
                    models.AlunoTurma,
                    models.AlunoTurma.aluno_id == models.Aluno.id,
                )
                .join(models.Turma, models.Turma.id == models.AlunoTurma.turma_id)
                .where(models.Turma.id == turma_id)
                .where(models.Turma.excluida_em.is_(None))
                .where(models.AlunoTurma.ativo.is_(True))
                .order_by(models.Aluno.nome, models.Aluno.id)
            ).all()
            return [_para_entidade(linha) for linha in linhas]

    def listar_referencias(
        self, modelo: str, *, turma_id: int
    ) -> list[tuple[Aluno, FaceEmbedding]]:
        with sessao(self._engine) as session:
            _exigir_turma_ativa(session, turma_id)
            linhas = session.scalars(
                select(models.Aluno)
                .join(
                    models.AlunoTurma,
                    models.AlunoTurma.aluno_id == models.Aluno.id,
                )
                .join(models.Turma, models.Turma.id == models.AlunoTurma.turma_id)
                .where(models.Turma.id == turma_id)
                .where(models.Turma.excluida_em.is_(None))
                .where(models.AlunoTurma.ativo.is_(True))
                .where(models.Aluno.embedding.is_not(None))
                .where(models.Aluno.embedding_modelo == modelo)
                .order_by(models.Aluno.id)
            ).all()

            referencias = []
            for linha in linhas:
                assert linha.embedding is not None  # garantido pelo WHERE
                embedding = FaceEmbedding.de_bytes(linha.embedding, modelo)
                referencias.append((_para_entidade(linha), embedding))

        return referencias

    def cadastrar_em_turma(
        self,
        turma_id: int,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
        consentimento_em: dt.datetime,
    ) -> Aluno:
        try:
            with sessao(self._engine) as session:
                _exigir_turma_ativa(session, turma_id, bloquear=True)
                linha = models.Aluno(
                    matricula=matricula,
                    nome=nome,
                    foto_arquivo=foto_arquivo,
                    embedding=embedding.para_bytes() if embedding else None,
                    embedding_modelo=embedding.modelo if embedding else None,
                    embedding_dim=embedding.dimensao if embedding else None,
                    consentimento_em=consentimento_em,
                )
                session.add(linha)
                session.flush()
                session.add(
                    models.AlunoTurma(
                        turma_id=turma_id,
                        aluno_id=linha.id,
                        ativo=True,
                        vinculado_em=consentimento_em,
                        desvinculado_em=None,
                    )
                )
                session.flush()
                aluno = _para_entidade(linha)
        except IntegrityError as exc:
            # A unicidade e garantida pelo banco. Verificar antes com um
            # SELECT nao elimina a corrida -- so a constraint elimina.
            if "uq_alunos_matricula" in str(exc.orig):
                raise AlunoJaCadastrado(matricula) from exc
            raise

        logger.info("Aluno cadastrado (id=%s)", aluno.id)
        return aluno

    def excluir_global(self, aluno_id: int) -> None:
        with sessao(self._engine) as session:
            session.execute(delete(models.Aluno).where(models.Aluno.id == aluno_id))
        # As presencas caem por ON DELETE CASCADE -- a integridade e do
        # banco, nao de uma varredura da aplicacao.
        logger.info("Aluno excluido (id=%s)", aluno_id)
