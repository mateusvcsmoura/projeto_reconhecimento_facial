"""Contrato de persistencia de presencas."""

from __future__ import annotations

import datetime as dt
from typing import NamedTuple, Protocol


class PresencaRegistrada(NamedTuple):
    """Uma presenca ja gravada, com o aluno resolvido para exibicao."""

    aluno_id: int
    matricula: str
    nome: str
    registrado_em: dt.datetime


class PresencaRepository(Protocol):
    def listar_do_dia(self, dia: dt.date) -> list[PresencaRegistrada]:
        """Presencas de um dia, ordenadas por horario de chegada."""
        ...

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

    def expurgar_anteriores_a(self, dia: dt.date) -> int:
        """Apaga presencas com data anterior ao limite e devolve a contagem.

        Dado pessoal nao deve ser guardado por mais tempo do que a
        finalidade exige (LGPD art. 15/16).
        """
        ...
