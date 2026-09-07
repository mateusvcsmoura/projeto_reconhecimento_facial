"""Contrato de persistencia de presencas."""

from __future__ import annotations

import datetime as dt
from typing import Protocol


class PresencaRepository(Protocol):
    def registrar_se_ausente(
        self, aluno_id: int, dia: dt.date, momento: dt.datetime
    ) -> bool:
        """Registra a presenca do dia.

        Devolve True se inseriu, False se ja havia registro para o aluno
        naquele dia. A regra e garantida pela constraint UNIQUE do banco,
        e nao por um SELECT previo -- que era o desenho sujeito a corrida
        do prototipo (problema A4).
        """
        ...
