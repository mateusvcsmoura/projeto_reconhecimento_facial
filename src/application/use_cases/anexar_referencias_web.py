"""Anexa exatamente três recortes distintos a uma solicitação pendente."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.domain.entities.referencia_facial import (
    PreparacaoReferencia,
    ReferenciaParaPersistir,
    validar_tres_referencias,
)
from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro
from src.domain.errors import AnexoJaProcessado
from src.domain.services.reference_storage import PrivateReferenceStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ContextoJobReferencias:
    job_id: uuid.UUID
    consentimento_em: dt.datetime
    consentimento_versao: str


class RepositorioAnexoReferencias(Protocol):
    def obter_solicitacao(self, solicitacao_id: int) -> SolicitacaoCadastro: ...

    def estado_do_job(self, solicitacao_id: int, job_id: uuid.UUID) -> str | None: ...

    def anexar_referencias(
        self,
        solicitacao_id: int,
        *,
        job_id: uuid.UUID,
        referencias: tuple[ReferenciaParaPersistir, ...],
        consentimento_em: dt.datetime,
        consentimento_versao: str,
        agora: dt.datetime,
    ) -> str: ...


class AnexarReferencias:
    def __init__(
        self,
        repositorio: RepositorioAnexoReferencias,
        storage: PrivateReferenceStorage,
        *,
        relogio: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._storage = storage
        self._relogio = relogio or (lambda: dt.datetime.now(dt.UTC))

    def executar(
        self,
        solicitacao_id: int,
        preparacoes: tuple[PreparacaoReferencia, ...] | list[PreparacaoReferencia],
        contexto_job: ContextoJobReferencias,
    ) -> str:
        existente = self._repositorio.estado_do_job(solicitacao_id, contexto_job.job_id)
        if existente is not None:
            return existente
        solicitacao = self._repositorio.obter_solicitacao(solicitacao_id)
        agora = self._agora()
        if solicitacao.estado not in {"em_coleta", "em_validacao"}:
            raise ValueError("A solicitação não está recebendo referências.")
        if solicitacao.expira_em <= agora:
            raise ValueError("A solicitação está expirada.")
        consentimento_em = contexto_job.consentimento_em
        versao = contexto_job.consentimento_versao.strip()
        if (
            consentimento_em.tzinfo is None
            or consentimento_em.utcoffset() is None
            or not versao
        ):
            raise ValueError("É necessário consentimento válido antes da coleta.")
        canonicas = validar_tres_referencias(tuple(preparacoes))
        caminhos: list[str] = []
        try:
            referencias: list[ReferenciaParaPersistir] = []
            for preparacao in canonicas:
                caminho = self._storage.salvar(
                    solicitacao_id, preparacao.ordinal, preparacao.recorte
                )
                caminhos.append(caminho)
                referencias.append(
                    ReferenciaParaPersistir(
                        ordinal=preparacao.ordinal,
                        caminho_privado_relativo=caminho,
                        embedding=preparacao.embedding,
                    )
                )
            try:
                return self._repositorio.anexar_referencias(
                    solicitacao_id,
                    job_id=contexto_job.job_id,
                    referencias=tuple(referencias),
                    consentimento_em=consentimento_em.astimezone(dt.UTC),
                    consentimento_versao=versao,
                    agora=agora,
                )
            except AnexoJaProcessado as repeticao:
                self._compensar(caminhos)
                return repeticao.estado
        except Exception:
            self._compensar(caminhos)
            raise

    def _compensar(self, caminhos: list[str]) -> None:
        for caminho in caminhos:
            try:
                self._storage.remover(caminho)
            except Exception as erro:
                logger.error(
                    "Falha ao compensar recorte da solicitação web (%s).",
                    type(erro).__name__,
                )

    def _agora(self) -> dt.datetime:
        instante = self._relogio()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        return instante.astimezone(dt.UTC)
