"""Persistencia de alunos em PostgreSQL.

Todo o SQL do sistema vive aqui e no repositorio de presencas. Nenhum
caso de uso executa SQL (instructions/02-desenvolvedor.md, secao 4).
"""

from __future__ import annotations

import logging

from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from src.domain.entities.aluno import Aluno
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

    def listar(self) -> list[Aluno]:
        with sessao(self._engine) as session:
            linhas = session.scalars(
                select(models.Aluno).order_by(models.Aluno.nome)
            ).all()
            return [_para_entidade(linha) for linha in linhas]

    def cadastrar(self, matricula: str, nome: str, foto_arquivo: str | None) -> Aluno:
        try:
            with sessao(self._engine) as session:
                linha = models.Aluno(
                    matricula=matricula, nome=nome, foto_arquivo=foto_arquivo
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
