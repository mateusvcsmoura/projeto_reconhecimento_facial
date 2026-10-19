"""Dependências de autenticação reutilizáveis pelas rotas de domínio web."""

from __future__ import annotations

import hmac
from typing import Protocol

from fastapi import HTTPException, Request, status

from src.config.web_settings import WebSettings
from src.infrastructure.repositories.postgres_conta_repository import (
    COOKIE_SESSAO,
    ContaAutenticada,
)


class RepositorioAuthWeb(Protocol):
    def autenticar_sessao(self, token: str | None) -> ContaAutenticada | None: ...

    def validar_csrf(self, conta: ContaAutenticada, token_csrf: str | None) -> bool: ...


class DependenciasAuthWeb:
    """Aplica a mesma sessão, Origin, CSRF e papel usados pelo auth router."""

    def __init__(
        self, settings: WebSettings, repository: RepositorioAuthWeb | None
    ) -> None:
        self._settings = settings
        self._repository = repository

    def repository(self) -> RepositorioAuthWeb:
        if self._repository is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Autenticação indisponível.",
            )
        return self._repository

    def exigir_origem(self, request: Request) -> None:
        origem = request.headers.get("origin")
        esperada = self._settings.public_origin
        if (
            origem is None
            or esperada is None
            or not hmac.compare_digest(origem, esperada)
        ):
            raise HTTPException(status_code=403, detail="Origem recusada.")

    def exigir_conta(self, request: Request) -> ContaAutenticada:
        conta = self.repository().autenticar_sessao(request.cookies.get(COOKIE_SESSAO))
        if conta is None:
            raise HTTPException(status_code=401, detail="Autenticação necessária.")
        return conta

    def exigir_mutacao(
        self,
        request: Request,
    ) -> ContaAutenticada:
        conta = self.exigir_conta(request)
        self.exigir_origem(request)
        if not self.repository().validar_csrf(
            conta, request.headers.get("x-csrf-token")
        ):
            raise HTTPException(status_code=403, detail="Verificação CSRF recusada.")
        return conta

    def exigir_admin(
        self,
        request: Request,
    ) -> ContaAutenticada:
        conta = self.exigir_conta(request)
        if conta.papel != "admin" or conta.troca_senha_obrigatoria:
            raise HTTPException(status_code=403, detail="Operação não autorizada.")
        return conta
