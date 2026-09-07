"""Casos de uso de consulta: listagens para o operador.

Sao leituras: nao alteram estado e nao dependem de camera nem de modelo.
Existem para que a apresentacao nao precise conhecer repositorio nem SQL.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from src.domain.entities.aluno import Aluno
from src.domain.repositories.aluno_repository import AlunoRepository
from src.domain.repositories.presenca_repository import (
    PresencaRegistrada,
    PresencaRepository,
)


@dataclass(frozen=True, slots=True)
class AlunoListado:
    """Aluno com o que a interface precisa saber para orientar o operador."""

    aluno: Aluno
    pronto_para_reconhecimento: bool

    @property
    def situacao(self) -> str:
        if self.pronto_para_reconhecimento:
            return "pronto"
        # Sem embedding do modelo em uso, o aluno existe mas e invisivel ao
        # reconhecimento. O operador precisa saber disso antes da aula.
        return "sem embedding"


class ListarAlunos:
    def __init__(self, alunos: AlunoRepository, modelo: str) -> None:
        self._alunos = alunos
        self._modelo = modelo

    def executar(self) -> list[AlunoListado]:
        prontos = {
            aluno.id for aluno, _ in self._alunos.listar_referencias(self._modelo)
        }
        return [
            AlunoListado(aluno=aluno, pronto_para_reconhecimento=aluno.id in prontos)
            for aluno in self._alunos.listar()
        ]


class ListarPresencasDoDia:
    def __init__(self, presencas: PresencaRepository, tz: ZoneInfo) -> None:
        self._presencas = presencas
        self._tz = tz

    def hoje(self) -> dt.date:
        return dt.datetime.now(self._tz).date()

    def executar(self, dia: dt.date | None = None) -> list[PresencaRegistrada]:
        return self._presencas.listar_do_dia(dia or self.hoje())

    def horario_local(self, registro: PresencaRegistrada) -> str:
        return registro.registrado_em.astimezone(self._tz).strftime("%H:%M")
