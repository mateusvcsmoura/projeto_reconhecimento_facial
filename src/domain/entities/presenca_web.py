"""Entidades da presença por sessão e da revisão manual web."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class StatusPresenca(StrEnum):
    PRESENTE = "presente"
    ANULADA = "anulada"


class OrigemPresenca(StrEnum):
    BIOMETRICA = "biometrica"
    MANUAL = "manual"
    LEGADO = "legado"


@dataclass(frozen=True, slots=True)
class Presenca:
    id: int
    aluno_id: int
    turma_id: int
    sessao_id: int | None
    status: StatusPresenca
    origem: OrigemPresenca
    registrado_em: dt.datetime
    data_referencia: dt.date
    horario_evidencia: dt.datetime | None
    corrigida_em: dt.datetime | None
    corrigida_por_conta_id: int | None
    versao: int


@dataclass(frozen=True, slots=True)
class RevisaoPresenca:
    id: UUID
    turma_id: int
    sessao_id: int
    aluno_id: int
    matricula: str | None
    nome: str | None
    estado: str
    justificativa_solicitacao: str
    via_acessivel: bool
    solicitada_em: dt.datetime
    versao_presenca_base: int
    decisao: StatusPresenca | None = None
    justificativa_decisao: str | None = None
    decidida_em: dt.datetime | None = None
    decidida_por_conta_id: int | None = None
