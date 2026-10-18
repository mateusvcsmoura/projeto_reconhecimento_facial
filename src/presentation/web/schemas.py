"""Schemas estaveis da fundacao HTTP."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

ComponentStatus = Literal["available", "unavailable"]


class HealthLiveResponse(BaseModel):
    status: Literal["live"]


class HealthReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    componentes: dict[str, ComponentStatus]


class PublicErrorResponse(BaseModel):
    codigo: str
    mensagem: str
    request_id: str


class OperationStatusResponse(BaseModel):
    id: UUID
    estado: Literal["recebida", "enfileirada", "processando", "concluida", "rejeitada"]
    criada_em: datetime
    atualizada_em: datetime
    codigo: str | None = None
