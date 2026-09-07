"""Contrato de persistencia de alunos."""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.aluno import Aluno


class AlunoRepository(Protocol):
    def existe_matricula(self, matricula: str) -> bool: ...

    def listar(self) -> list[Aluno]: ...

    def cadastrar(self, matricula: str, nome: str, foto_arquivo: str | None) -> Aluno:
        """Insere e devolve o aluno com o id atribuido pelo banco.

        Levanta AlunoJaCadastrado se a matricula ja existir.
        """
        ...
