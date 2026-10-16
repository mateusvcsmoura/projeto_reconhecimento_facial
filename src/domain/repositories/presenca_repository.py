"""Contrato de persistencia de presencas."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from src.domain.entities.turma import Periodo


@dataclass(frozen=True, slots=True)
class PresencaRegistrada:
    """Presenca e contexto de turma; turma_id nulo identifica o legado."""

    aluno_id: int
    matricula: str
    nome: str
    registrado_em: dt.datetime
    turma_id: int | None = None
    materia: str | None = None
    periodo: Periodo | None = None


class PresencaRepository(Protocol):
    def listar_da_turma(self, turma_id: int, dia: dt.date) -> list[PresencaRegistrada]:
        """Presencas de um dia, ordenadas por horario de chegada."""
        ...

    def listar_historico_da_turma(
        self, turma_id: int, dia: dt.date
    ) -> list[PresencaRegistrada]: ...

    def listar_legado(self, dia: dt.date) -> list[PresencaRegistrada]: ...

    def registrar_se_ausente(
        self, aluno_id: int, dia: dt.date, momento: dt.datetime, *, turma_id: int
    ) -> bool:
        """Registra presenca dentro da turma e do vinculo ativos.

        Devolve False somente se ja havia registro para esse aluno, turma e
        dia. Contexto invalido levanta erro de dominio.
        """
        ...

    def expurgar_anteriores_a(self, dia: dt.date) -> int:
        """Apaga presencas com data anterior ao limite e devolve a contagem.

        Dado pessoal nao deve ser guardado por mais tempo do que a
        finalidade exige (LGPD art. 15/16).
        """
        ...
