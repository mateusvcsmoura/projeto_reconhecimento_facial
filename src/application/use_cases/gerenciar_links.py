"""Emite e valida links de finalidade especifica sem persistir seus segredos."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from src.domain.services.autorizacao import AtorWeb

PRAZO_LINK = timedelta(days=7)
PRAZO_CREDENCIAL_ACESSO = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class LinkCadastroEmitido:
    id: UUID
    token: str
    turma_id: int
    finalidade: str
    criado_em: datetime
    expira_em: datetime
    finalidade_ate: datetime


@dataclass(frozen=True, slots=True)
class AcessoLinkEmitido:
    credencial: str
    link_id: UUID
    turma_id: int
    finalidade: str
    expira_em: datetime
    finalidade_ate: datetime


@dataclass(frozen=True, slots=True)
class ResultadoRevogacaoLink:
    link_id: UUID
    solicitacoes_canceladas: int
    solicitacao_ids: tuple[int, ...]


class RepositorioLinksCadastro(Protocol):
    def criar_link(self, **kwargs: object) -> UUID: ...

    def trocar_token(self, **kwargs: object) -> dict[str, object] | None: ...

    def contexto_credencial(
        self, credencial_hash: str, **kwargs: object
    ) -> dict[str, object] | None: ...

    def revogar(
        self, ator: AtorWeb, link_id: UUID, **kwargs: object
    ) -> tuple[int, tuple[int, ...]]: ...


class GerenciarLinks:
    """Regra de domínio/aplicação para link compartilhado de cadastro."""

    def __init__(
        self,
        repositorio: RepositorioLinksCadastro,
        *,
        relogio: Callable[[], datetime] | None = None,
        gerar_segredo: Callable[[], str] | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._relogio = relogio or (lambda: datetime.now(UTC))
        self._gerar_segredo = gerar_segredo or (lambda: secrets.token_urlsafe(32))

    def criar(
        self, ator: AtorWeb, turma_id: int, *, finalidade_ate: datetime
    ) -> LinkCadastroEmitido:
        agora = self._agora()
        fim = self._utc(finalidade_ate)
        if turma_id <= 0 or fim <= agora:
            raise ValueError("A turma ou o fim da finalidade são inválidos.")
        token = self._segredo()
        expira_em = min(agora + PRAZO_LINK, fim)
        link_id = self._repositorio.criar_link(
            ator=ator,
            turma_id=turma_id,
            finalidade="cadastro",
            token_hash=self._hash(token),
            criado_em=agora,
            expira_em=expira_em,
            finalidade_ate=fim,
        )
        return LinkCadastroEmitido(
            id=link_id,
            token=token,
            turma_id=turma_id,
            finalidade="cadastro",
            criado_em=agora,
            expira_em=expira_em,
            finalidade_ate=fim,
        )

    def trocar(self, token: str) -> AcessoLinkEmitido | None:
        agora = self._agora()
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            return None
        credencial = self._segredo()
        link = self._repositorio.trocar_token(
            token_hash=self._hash(token),
            credencial_hash=self._hash(credencial),
            agora=agora,
            credencial_expira_em=agora + PRAZO_CREDENCIAL_ACESSO,
        )
        if link is None:
            return None
        link_id = link.get("link_id")
        turma_id = link.get("turma_id")
        finalidade = link.get("finalidade")
        expira_credencial = link.get("credencial_expira_em")
        finalidade_ate = link.get("finalidade_ate")
        if (
            not isinstance(link_id, UUID)
            or not isinstance(turma_id, int)
            or isinstance(turma_id, bool)
            or finalidade != "cadastro"
            or not isinstance(expira_credencial, datetime)
            or not isinstance(finalidade_ate, datetime)
        ):
            return None
        return AcessoLinkEmitido(
            credencial=credencial,
            link_id=link_id,
            turma_id=turma_id,
            finalidade="cadastro",
            expira_em=self._utc(expira_credencial),
            finalidade_ate=self._utc(finalidade_ate),
        )

    def revogar(self, ator: AtorWeb, link_id: UUID) -> ResultadoRevogacaoLink:
        quantidade, solicitacao_ids = self._repositorio.revogar(
            ator, link_id, agora=self._agora()
        )
        return ResultadoRevogacaoLink(link_id, quantidade, solicitacao_ids)

    def _segredo(self) -> str:
        segredo = self._gerar_segredo()
        if not isinstance(segredo, str) or len(segredo) < 43:
            raise ValueError("O segredo aleatório deve conter ao menos 256 bits.")
        return segredo

    def _agora(self) -> datetime:
        return self._utc(self._relogio())

    @staticmethod
    def _utc(instante: object) -> datetime:
        if not isinstance(instante, datetime) or instante.tzinfo is None:
            raise ValueError("O instante deve conter fuso horário.")
        return instante.astimezone(UTC)

    @staticmethod
    def _hash(segredo: str) -> str:
        return hashlib.sha256(segredo.encode("utf-8")).hexdigest()
