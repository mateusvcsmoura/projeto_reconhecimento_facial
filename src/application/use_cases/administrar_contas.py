"""Casos de uso administrativos para contas e responsabilidades de turma."""

from __future__ import annotations

from datetime import datetime

from src.infrastructure.repositories.postgres_conta_repository import (
    PostgresContaRepository,
)


class AdministrarContas:
    def __init__(self, contas: PostgresContaRepository) -> None:
        self._contas = contas

    def criar(
        self,
        ator_id: int,
        usuario: str,
        papel: str,
        justificativa: str,
        *,
        request_id: str | None = None,
    ) -> tuple[int, str, datetime]:
        return self._contas.criar_conta(
            ator_id, usuario, papel, justificativa, request_id=request_id
        )

    def redefinir_senha(
        self,
        ator_id: int,
        conta_id: int,
        justificativa: str,
        referencia_verificacao: str,
        *,
        request_id: str | None = None,
    ) -> tuple[str, datetime]:
        return self._contas.redefinir_senha(
            ator_id,
            conta_id,
            justificativa,
            referencia_verificacao,
            request_id=request_id,
        )

    def desativar(
        self,
        ator_id: int,
        conta_id: int,
        justificativa: str,
        *,
        request_id: str | None = None,
    ) -> None:
        self._contas.desativar_conta(
            ator_id, conta_id, justificativa, request_id=request_id
        )

    def transferir_turma(
        self,
        ator_id: int,
        turma_id: int,
        professor_id: int,
        justificativa: str,
        *,
        request_id: str | None = None,
    ) -> None:
        self._contas.transferir_turma(
            ator_id,
            turma_id,
            professor_id,
            justificativa,
            request_id=request_id,
        )
