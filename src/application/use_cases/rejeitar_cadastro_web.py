"""Rejeita uma solicitação pendente e tenta remover recortes provisórios."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Protocol

from src.domain.entities.solicitacao_cadastro import ResultadoEncerramento
from src.domain.services.autorizacao import AtorWeb
from src.domain.services.reference_storage import PrivateReferenceStorage

logger = logging.getLogger(__name__)


class RepositorioRejeicaoCadastro(Protocol):
    def rejeitar_cadastro_web(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        justificativa: str,
        agora: dt.datetime,
    ) -> None: ...

    def limpar_arquivos_provisorios(self, solicitacao_id: int) -> tuple[str, ...]: ...

    def confirmar_limpeza_provisoria(
        self, solicitacao_id: int, *, agora: dt.datetime
    ) -> None: ...


class RejeitarCadastroWeb:
    def __init__(
        self,
        repositorio: RepositorioRejeicaoCadastro,
        storage: PrivateReferenceStorage,
        *,
        relogio: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._storage = storage
        self._relogio = relogio or (lambda: dt.datetime.now(dt.UTC))

    def executar(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        justificativa: str,
    ) -> ResultadoEncerramento:
        motivo = " ".join(justificativa.split())
        if not 10 <= len(motivo) <= 500:
            raise ValueError("A justificativa deve ter entre 10 e 500 caracteres.")
        instante = self._relogio()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        instante = instante.astimezone(dt.UTC)
        self._repositorio.rejeitar_cadastro_web(
            ator,
            solicitacao_id,
            justificativa=motivo,
            agora=instante,
        )
        pendente = False
        try:
            for caminho in self._repositorio.limpar_arquivos_provisorios(
                solicitacao_id
            ):
                self._storage.remover(caminho)
            self._repositorio.confirmar_limpeza_provisoria(
                solicitacao_id, agora=instante
            )
        except Exception as erro:
            pendente = True
            logger.error(
                "Limpeza de solicitação rejeitada %s permanece pendente (%s).",
                solicitacao_id,
                type(erro).__name__,
            )
        return ResultadoEncerramento(
            solicitacao_id=solicitacao_id,
            estado="rejeitada",
            limpeza_pendente=pendente,
        )
