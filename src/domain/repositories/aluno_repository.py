"""Contrato de persistencia de alunos."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding


class AlunoRepository(Protocol):
    def validar_turma_ativa(self, turma_id: int) -> None: ...

    def existe_matricula_global(self, matricula: str) -> bool: ...

    def listar_por_turma(self, turma_id: int) -> list[Aluno]: ...

    def listar_referencias(
        self, modelo: str, *, turma_id: int
    ) -> list[tuple[Aluno, FaceEmbedding]]:
        """Alunos com embedding utilizavel para o modelo informado.

        Filtrar por modelo no repositorio evita carregar vetores que seriam
        descartados na comparacao -- e evita o pior caso: compara-los assim
        mesmo e identificar a pessoa errada em silencio.
        """
        ...

    def obter_global_por_matricula(self, matricula: str) -> Aluno | None: ...

    def cadastrar_em_turma(
        self,
        turma_id: int,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
        consentimento_em: dt.datetime,
    ) -> Aluno:
        """Insere aluno e vinculo na mesma transacao SQL.

        Levanta AlunoJaCadastrado se a matricula ja existir.
        """
        ...

    def excluir_global(self, aluno_id: int) -> None:
        """Remove o aluno e, por cascade, todas as suas presencas.

        Direito do titular a eliminacao (LGPD art. 18, VI).
        """
        ...
