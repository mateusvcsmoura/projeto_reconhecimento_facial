"""Rotas de emissão, troca e revogação de links de cadastro."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.application.use_cases.gerenciar_links import GerenciarLinks
from src.config.web_settings import WebSettings
from src.domain.services.autorizacao import AcessoTurmaNegado
from src.infrastructure.repositories.postgres_conta_repository import (
    ContaAutenticada,
)
from src.presentation.web.dependencies import DependenciasAuthWeb

if TYPE_CHECKING:
    from src.presentation.web.app import WebServices

logger = logging.getLogger(__name__)


class _Schema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TrocarLinkRequest(_Schema):
    token: str = Field(min_length=43, max_length=128)


def criar_rotas_links(settings: WebSettings, services: WebServices) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["cadastro-links"])
    auth = DependenciasAuthWeb(settings, services.auth_repository)

    def links_repository() -> Any:
        if services.link_repository is None:
            raise HTTPException(
                status_code=503, detail="Links de cadastro indisponíveis."
            )
        return services.link_repository

    def finalidade_ate() -> datetime:
        if settings.purpose_end_at is None:
            raise HTTPException(
                status_code=503,
                detail="O fim da finalidade do cadastro não está configurado.",
            )
        return settings.purpose_end_at

    @router.post(
        "/turmas/{turma_id}/links-cadastro", status_code=status.HTTP_201_CREATED
    )
    def criar_link(
        turma_id: int,
        request: Request,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        if turma_id <= 0:
            raise HTTPException(status_code=404, detail="Turma não encontrada.")
        repo_conta = auth.repository()
        turma = repo_conta.autorizar_turma(turma_id)  # type: ignore[attr-defined]
        if turma is None:
            raise HTTPException(status_code=404, detail="Turma não encontrada.")
        try:
            link = GerenciarLinks(links_repository(), relogio=services.now_utc).criar(
                conta.como_ator(), turma_id, finalidade_ate=finalidade_ate()
            )
        except AcessoTurmaNegado:
            raise HTTPException(
                status_code=404, detail="Turma não encontrada."
            ) from None
        except ValueError:
            raise HTTPException(
                status_code=422, detail="A turma não pode receber um link."
            ) from None
        return {
            "id": str(link.id),
            "token": link.token,
            "finalidade": link.finalidade,
            "criado_em": link.criado_em.isoformat(),
            "expira_em": link.expira_em.isoformat(),
        }

    @router.post("/acessos-link", status_code=status.HTTP_200_OK)
    def trocar_link(body: TrocarLinkRequest) -> dict[str, object]:
        acesso = GerenciarLinks(links_repository(), relogio=services.now_utc).trocar(
            body.token
        )
        if acesso is None:
            raise HTTPException(status_code=404, detail="Link indisponível.")
        return {
            "credencial": acesso.credencial,
            "finalidade": acesso.finalidade,
            "expira_em": acesso.expira_em.isoformat(),
            "finalidade_ate": acesso.finalidade_ate.isoformat(),
        }

    @router.post("/links/{link_id}/revogar", status_code=status.HTTP_200_OK)
    def revogar_link(
        link_id: UUID,
        conta: ContaAutenticada = Depends(auth.exigir_mutacao),  # noqa: B008
    ) -> dict[str, object]:
        try:
            resultado = GerenciarLinks(
                links_repository(), relogio=services.now_utc
            ).revogar(conta.como_ator(), link_id)
        except (LookupError, PermissionError, AcessoTurmaNegado):
            raise HTTPException(
                status_code=404, detail="Link não encontrado."
            ) from None
        limpeza_pendente = False
        if resultado.solicitacao_ids:
            if (
                services.reference_storage is None
                or services.solicitacao_repository is None
            ):
                limpeza_pendente = True
            else:
                for solicitacao_id in resultado.solicitacao_ids:
                    try:
                        caminhos = (
                            services.solicitacao_repository.limpar_arquivos_provisorios(  # type: ignore[attr-defined]
                                solicitacao_id
                            )
                        )
                        for caminho in caminhos:
                            services.reference_storage.remover(caminho)
                        services.solicitacao_repository.confirmar_limpeza_provisoria(  # type: ignore[attr-defined]
                            solicitacao_id, agora=services.now_utc()
                        )
                    except Exception as erro:
                        limpeza_pendente = True
                        logger.error(
                            "Limpeza biométrica após revogação pendente (%s).",
                            type(erro).__name__,
                        )
        return {
            "id": str(resultado.link_id),
            "revogado": True,
            "solicitacoes_canceladas": resultado.solicitacoes_canceladas,
            "limpeza_pendente": limpeza_pendente,
        }

    return router
