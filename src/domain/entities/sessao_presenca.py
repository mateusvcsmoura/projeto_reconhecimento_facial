"""Sessão web de presença, separada da sessão de autenticação."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


def _utc(instante: dt.datetime) -> dt.datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("O instante deve incluir fuso horário.")
    return instante.astimezone(dt.UTC)


@dataclass(frozen=True, slots=True)
class SessaoPresenca:
    id: int | None
    turma_id: int
    criada_por_conta_id: int
    titulo: str
    inicio_em: dt.datetime
    fim_em: dt.datetime
    criada_em: dt.datetime
    revogada_em: dt.datetime | None = None
    revogada_por_conta_id: int | None = None
    versao: int = 1

    def __post_init__(self) -> None:
        if self.id is not None and (isinstance(self.id, bool) or self.id <= 0):
            raise ValueError("O identificador da sessão deve ser positivo.")
        if (
            isinstance(self.turma_id, bool)
            or not isinstance(self.turma_id, int)
            or self.turma_id <= 0
            or isinstance(self.criada_por_conta_id, bool)
            or not isinstance(self.criada_por_conta_id, int)
            or self.criada_por_conta_id <= 0
            or isinstance(self.versao, bool)
            or not isinstance(self.versao, int)
            or self.versao <= 0
        ):
            raise ValueError("Os identificadores ou a versão da sessão são inválidos.")
        titulo = " ".join(self.titulo.split())
        if not titulo or len(titulo) > 120:
            raise ValueError("O título deve conter entre 1 e 120 caracteres.")
        inicio = _utc(self.inicio_em)
        fim = _utc(self.fim_em)
        criada = _utc(self.criada_em)
        if fim <= inicio:
            raise ValueError("O fim da sessão deve ser posterior ao início.")
        revogada = _utc(self.revogada_em) if self.revogada_em is not None else None
        if (revogada is None) != (self.revogada_por_conta_id is None):
            raise ValueError("Os dados de revogação da sessão são incoerentes.")
        if self.revogada_por_conta_id is not None and (
            isinstance(self.revogada_por_conta_id, bool)
            or self.revogada_por_conta_id <= 0
        ):
            raise ValueError("O responsável pela revogação é inválido.")
        object.__setattr__(self, "titulo", titulo)
        object.__setattr__(self, "inicio_em", inicio)
        object.__setattr__(self, "fim_em", fim)
        object.__setattr__(self, "criada_em", criada)
        object.__setattr__(self, "revogada_em", revogada)

    @classmethod
    def nova(
        cls,
        *,
        turma_id: int,
        criada_por_conta_id: int,
        titulo: str,
        inicio_em: dt.datetime,
        fim_em: dt.datetime,
        criada_em: dt.datetime,
    ) -> SessaoPresenca:
        return cls(
            id=None,
            turma_id=turma_id,
            criada_por_conta_id=criada_por_conta_id,
            titulo=titulo,
            inicio_em=inicio_em,
            fim_em=fim_em,
            criada_em=criada_em,
        )

    @property
    def revogada(self) -> bool:
        return self.revogada_em is not None
