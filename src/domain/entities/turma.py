"""Entidade pura de turma e vocabulario dos periodos letivos."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

from src.domain.errors import DadosInvalidos

MATERIA_MAXIMA = 120


class Periodo(StrEnum):
    MATUTINO = "matutino"
    DIURNO = "diurno"
    NOTURNO = "noturno"


@dataclass(frozen=True, slots=True)
class Turma:
    """Turma; `id=None` representa uma entrada validada ainda nao persistida."""

    id: int | None
    materia: str
    periodo: Periodo
    criado_em: dt.datetime | None = None
    atualizado_em: dt.datetime | None = None
    excluida_em: dt.datetime | None = None

    def __post_init__(self) -> None:
        materia = " ".join(self.materia.split())
        if not materia:
            raise DadosInvalidos("Informe a materia da turma.")
        if len(materia) > MATERIA_MAXIMA:
            raise DadosInvalidos(
                f"A materia pode ter no maximo {MATERIA_MAXIMA} caracteres."
            )
        if not isinstance(self.periodo, Periodo):
            raise DadosInvalidos("O periodo deve ser matutino, diurno ou noturno.")
        if self.id is not None and (isinstance(self.id, bool) or self.id <= 0):
            raise DadosInvalidos("O identificador da turma deve ser positivo.")
        for instante in (self.criado_em, self.atualizado_em, self.excluida_em):
            if instante is not None and (
                instante.tzinfo is None or instante.utcoffset() is None
            ):
                raise DadosInvalidos(
                    "Os instantes da turma devem incluir fuso horario."
                )
        object.__setattr__(self, "materia", materia)

    @classmethod
    def nova(cls, materia: str, periodo: str | Periodo) -> Turma:
        try:
            periodo_validado = (
                periodo if isinstance(periodo, Periodo) else Periodo(periodo)
            )
        except ValueError as erro:
            raise DadosInvalidos(
                "O periodo deve ser matutino, diurno ou noturno."
            ) from erro
        return cls(id=None, materia=materia, periodo=periodo_validado)

    @property
    def ativa(self) -> bool:
        return self.excluida_em is None
