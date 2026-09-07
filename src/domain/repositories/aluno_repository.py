"""Contrato de persistencia de alunos."""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding


class AlunoRepository(Protocol):
    def existe_matricula(self, matricula: str) -> bool: ...

    def listar_referencias(self, modelo: str) -> list[tuple[Aluno, FaceEmbedding]]:
        """Alunos com embedding utilizavel para o modelo informado.

        Filtrar por modelo no repositorio evita carregar vetores que seriam
        descartados na comparacao -- e evita o pior caso: compara-los assim
        mesmo e identificar a pessoa errada em silencio.
        """
        ...

    def cadastrar(
        self,
        matricula: str,
        nome: str,
        foto_arquivo: str | None,
        embedding: FaceEmbedding | None,
    ) -> Aluno:
        """Insere e devolve o aluno com o id atribuido pelo banco.

        Levanta AlunoJaCadastrado se a matricula ja existir.
        """
        ...
