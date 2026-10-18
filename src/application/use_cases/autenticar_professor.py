"""Caso de uso de autenticacao de contas professor/admin."""

from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.repositories.postgres_conta_repository import (
    PostgresContaRepository,
    ResultadoLogin,
    normalizar_usuario,
    validar_senha,
)

__all__ = [
    "AutenticarProfessor",
    "ContextoCliente",
    "normalizar_usuario",
    "validar_senha",
]


@dataclass(frozen=True)
class ContextoCliente:
    endereco_ip: str | None
    token_sessao_anterior: str | None = None


class AutenticarProfessor:
    """Mantem o contrato de aplicacao independente do transporte HTTP."""

    def __init__(self, contas: PostgresContaRepository) -> None:
        self._contas = contas

    def executar(
        self, usuario: str, senha: str, contexto_cliente: ContextoCliente
    ) -> ResultadoLogin:
        return self._contas.autenticar(
            usuario,
            senha,
            contexto_cliente.endereco_ip,
            contexto_cliente.token_sessao_anterior,
        )
