"""Ativa uma nova versão biométrica somente após aprovação administrativa."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Protocol

from sqlalchemy.exc import SQLAlchemyError

from src.domain.services.autorizacao import AtorWeb
from src.domain.services.reference_storage import PrivateReferenceStorage

logger = logging.getLogger(__name__)


class RepositorioAprovacaoAtualizacao(Protocol):
    def aprovar_atualizacao_biometrica(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        justificativa: str,
        agora: dt.datetime,
    ) -> int: ...

    def descartar_candidato_com_falha_sql(
        self, ator: AtorWeb, solicitacao_id: int, *, agora: dt.datetime
    ) -> tuple[str, ...]: ...

    def confirmar_limpeza_provisoria(
        self, solicitacao_id: int, *, agora: dt.datetime
    ) -> None: ...


class AprovarAtualizacaoBiometrica:
    def __init__(
        self,
        repositorio: RepositorioAprovacaoAtualizacao,
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
    ) -> int:
        if ator.papel != "admin":
            raise PermissionError("Somente administrador pode aprovar uma atualização.")
        motivo = " ".join(justificativa.split())
        if not 10 <= len(motivo) <= 500:
            raise ValueError("A justificativa deve ter entre 10 e 500 caracteres.")
        agora = self._relogio()
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        instante = agora.astimezone(dt.UTC)
        try:
            return self._repositorio.aprovar_atualizacao_biometrica(
                ator,
                solicitacao_id,
                justificativa=motivo,
                agora=instante,
            )
        except SQLAlchemyError:
            self._compensar_candidato(ator, solicitacao_id, instante)
            raise

    def _compensar_candidato(
        self, ator: AtorWeb, solicitacao_id: int, agora: dt.datetime
    ) -> None:
        try:
            caminhos = self._repositorio.descartar_candidato_com_falha_sql(
                ator, solicitacao_id, agora=agora
            )
            for caminho in caminhos:
                self._storage.remover(caminho)
            self._repositorio.confirmar_limpeza_provisoria(solicitacao_id, agora=agora)
        except Exception as erro:
            logger.error(
                "Compensação da atualização %s permanece pendente (%s).",
                solicitacao_id,
                type(erro).__name__,
            )
