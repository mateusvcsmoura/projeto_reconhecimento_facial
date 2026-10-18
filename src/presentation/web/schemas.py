"""Schemas estaveis da fundacao HTTP."""

from __future__ import annotations

from typing import Literal

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
