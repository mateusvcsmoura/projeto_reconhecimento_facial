"""Contrato de persistencia de turmas e vinculos de alunos."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from src.domain.entities.aluno import Aluno
from src.domain.entities.turma import Periodo, Turma


class TurmaRepository(Protocol):
    def criar(self, turma: Turma, agora: dt.datetime) -> Turma: ...

    def listar_ativas(self) -> list[Turma]: ...

    def listar_excluidas(self) -> list[Turma]: ...

    def obter(self, turma_id: int) -> Turma | None: ...

    def atualizar(
        self, turma_id: int, materia: str, periodo: Periodo, agora: dt.datetime
    ) -> Turma: ...

    def excluir_logicamente(self, turma_id: int, agora: dt.datetime) -> None: ...

    def vincular_matricula(
        self, turma_id: int, matricula: str, agora: dt.datetime
    ) -> tuple[Aluno, bool]: ...

    def desvincular_matricula(
        self, turma_id: int, matricula: str, agora: dt.datetime
    ) -> Aluno: ...
