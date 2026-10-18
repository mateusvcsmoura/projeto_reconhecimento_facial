"""Limpeza rastreável e repetível de referências temporárias descartadas."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Protocol

from src.domain.services.reference_storage import PrivateReferenceStorage

logger = logging.getLogger(__name__)


class RepositorioLimpezaReferencias(Protocol):
    def preparar_limpeza_provisoria(
        self, agora: dt.datetime, limite: int
    ) -> tuple[int, ...]: ...

    def limpar_arquivos_provisorios(self, solicitacao_id: int) -> tuple[str, ...]: ...

    def confirmar_limpeza_provisoria(
        self, solicitacao_id: int, *, agora: dt.datetime
    ) -> None: ...


class LimparReferenciasProvisorias:
    def __init__(
        self,
        repositorio: RepositorioLimpezaReferencias,
        storage: PrivateReferenceStorage,
        *,
        relogio: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._storage = storage
        self._relogio = relogio or (lambda: dt.datetime.now(dt.UTC))

    def executar(self, limite: int = 100) -> tuple[int, tuple[int, ...]]:
        if not 1 <= limite <= 1000:
            raise ValueError("O limite de limpeza deve estar entre 1 e 1000.")
        agora = self._relogio()
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        ids = self._repositorio.preparar_limpeza_provisoria(
            agora.astimezone(dt.UTC), limite
        )
        concluidas: list[int] = []
        falhas: list[int] = []
        for solicitacao_id in ids:
            try:
                for caminho in self._repositorio.limpar_arquivos_provisorios(
                    solicitacao_id
                ):
                    self._storage.remover(caminho)
                self._repositorio.confirmar_limpeza_provisoria(
                    solicitacao_id, agora=agora.astimezone(dt.UTC)
                )
                concluidas.append(solicitacao_id)
            except Exception as erro:
                logger.error(
                    "Limpeza de solicitação %s permanece pendente (%s).",
                    solicitacao_id,
                    type(erro).__name__,
                )
                falhas.append(solicitacao_id)
        return len(concluidas), tuple(falhas)
