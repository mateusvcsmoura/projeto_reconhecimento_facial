"""Caso de uso: registrar a presenca do dia."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from src.domain.repositories.presenca_repository import PresencaRepository


class RegistrarPresenca:
    def __init__(self, presencas: PresencaRepository, tz: ZoneInfo) -> None:
        self._presencas = presencas
        self._tz = tz

    def executar(
        self,
        aluno_id: int,
        *,
        turma_id: int,
        agora: dt.datetime | None = None,
    ) -> bool:
        """Devolve True se registrou, False se ja havia presenca hoje.

        O "dia" e decidido aqui, no fuso da aplicacao, e persistido junto
        com o instante. No prototipo o dia era derivado por date() sobre um
        TEXT livre, e nao funcionava para os dados gravados em dd/mm/aaaa.
        """
        momento = agora or dt.datetime.now(self._tz)
        dia = momento.astimezone(self._tz).date()
        return self._presencas.registrar_se_ausente(
            aluno_id, dia, momento, turma_id=turma_id
        )
