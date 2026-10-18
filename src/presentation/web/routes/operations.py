"""Consulta segura do estado de uma operação por credencial opaca."""

from __future__ import annotations

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, status

from src.application.services.fila_facial import (
    FilaFacial,
    OperacaoNaoEncontrada,
)
from src.presentation.web.schemas import OperationStatusResponse

EstadoOperacaoPublica = Literal[
    "recebida", "enfileirada", "processando", "concluida", "rejeitada"
]


def criar_rotas_operacoes(fila: FilaFacial | None) -> APIRouter:
    router = APIRouter(prefix="/api/v1/operacoes", tags=["operacoes"])

    @router.get("/{operacao_id}", response_model=OperationStatusResponse)
    def consultar_operacao(
        operacao_id: UUID,
        authorization: Annotated[str | None, Header()] = None,
    ) -> OperationStatusResponse:
        if fila is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Consulta de operações indisponível.",
            )
        if authorization is None:
            raise HTTPException(status_code=404, detail="Operação não encontrada.")
        esquema, separador, credencial = authorization.partition(" ")
        if esquema.lower() != "bearer" or not separador or not credencial.strip():
            raise HTTPException(status_code=404, detail="Operação não encontrada.")
        try:
            operacao = fila.consultar(operacao_id, credencial.strip())
        except OperacaoNaoEncontrada as exc:
            raise HTTPException(
                status_code=404, detail="Operação não encontrada."
            ) from exc
        return OperationStatusResponse(
            id=operacao.id,
            estado=cast(EstadoOperacaoPublica, operacao.estado.value),
            criada_em=operacao.criada_em,
            atualizada_em=operacao.atualizada_em,
            codigo=operacao.codigo,
        )

    return router
