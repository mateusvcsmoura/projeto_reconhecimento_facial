"""Persistencia de alunos em PostgreSQL.

Todo o SQL do sistema vive aqui e no repositorio de presencas. Nenhum
caso de uso executa SQL (instructions/02-desenvolvedor.md, secao 4).
"""

from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import IntegrityError

from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import AlunoJaCadastrado
from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao

logger = logging.getLogger(__name__)


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

    def existe_matricula(self, matricula: str) -> bool:
        with sessao(self._engine) as session:
            encontrado = session.scalar(
                select(models.Aluno.id).where(models.Aluno.matricula == matricula)
            )
        return encontrado is not None

    def obter_por_matricula(self, matricula: str) -> Aluno | None:
        with sessao(self._engine) as session:
            linha = session.scalar(
                select(models.Aluno).where(models.Aluno.matricula == matricula)
            )
            return _para_entidade(linha) if linha is not None else None

    def listar_referencias(self, modelo: str) -> list[tuple[Aluno, FaceEmbedding]]:
        with sessao(self._engine) as session:
            linhas = session.scalars(
                select(models.Aluno)
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

    def cadastrar(
        self,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
        consentimento_em: dt.datetime,
    ) -> Aluno:
        try:
            with sessao(self._engine) as session:
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
                aluno = _para_entidade(linha)
        except IntegrityError as exc:
            # A unicidade e garantida pelo banco. Verificar antes com um
            # SELECT nao elimina a corrida -- so a constraint elimina.
            if "uq_alunos_matricula" in str(exc.orig):
                raise AlunoJaCadastrado(matricula) from exc
            raise

        logger.info("Aluno cadastrado (id=%s)", aluno.id)
        return aluno

    def excluir(self, aluno_id: int) -> None:
        with sessao(self._engine) as session:
            session.execute(
                delete(models.Aluno).where(models.Aluno.id == aluno_id)
            )
        # As presencas caem por ON DELETE CASCADE -- a integridade e do
        # banco, nao de uma varredura da aplicacao.
        logger.info("Aluno excluido (id=%s)", aluno_id)
