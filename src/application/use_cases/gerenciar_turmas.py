"""Casos de uso para turmas e vinculos com alunos existentes."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from zoneinfo import ZoneInfo

from src.domain.entities.aluno import Aluno
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import DadosInvalidos, TurmaInativa, TurmaNaoEncontrada
from src.domain.repositories.turma_repository import TurmaRepository


class GerenciarTurmas:
    def __init__(
        self,
        turmas: TurmaRepository,
        tz: ZoneInfo,
        *,
        relogio: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._turmas = turmas
        self._tz = tz
        self._relogio = relogio or (lambda: dt.datetime.now(self._tz))

    def criar(self, materia: str, periodo: str | Periodo) -> Turma:
        nova = Turma.nova(materia, periodo)
        return self._turmas.criar(nova, self._agora())

    def listar_ativas(self) -> list[Turma]:
        return self._turmas.listar_ativas()

    def listar_excluidas(self) -> list[Turma]:
        return self._turmas.listar_excluidas()

    def obter(self, turma_id: int) -> Turma | None:
        return self._turmas.obter(turma_id)

    def obter_ativa(self, turma_id: int) -> Turma:
        turma = self._turmas.obter(turma_id)
        if turma is None:
            raise TurmaNaoEncontrada(turma_id)
        if not turma.ativa:
            raise TurmaInativa(turma_id)
        return turma

    def atualizar(self, turma_id: int, materia: str, periodo: str | Periodo) -> Turma:
        validada = Turma.nova(materia, periodo)
        return self._turmas.atualizar(
            turma_id, validada.materia, validada.periodo, self._agora()
        )

    def excluir(self, turma_id: int) -> None:
        self._turmas.excluir_logicamente(turma_id, self._agora())

    def vincular(self, turma_id: int, matricula: str) -> tuple[Aluno, bool]:
        matricula_limpa = matricula.strip()
        if not matricula_limpa:
            raise DadosInvalidos("Informe a matricula do aluno.")
        return self._turmas.vincular_matricula(turma_id, matricula_limpa, self._agora())

    def desvincular(self, turma_id: int, matricula: str) -> Aluno:
        matricula_limpa = matricula.strip()
        if not matricula_limpa:
            raise DadosInvalidos("Informe a matricula do aluno.")
        return self._turmas.desvincular_matricula(
            turma_id, matricula_limpa, self._agora()
        )

    def _agora(self) -> dt.datetime:
        instante = self._relogio()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relogio de turmas deve devolver um instante com fuso.")
        return instante.astimezone(self._tz)
