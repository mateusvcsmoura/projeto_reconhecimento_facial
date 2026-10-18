"""Aprovação administrativa independente e auditada de cadastro web."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Protocol

from src.domain.entities.solicitacao_cadastro import ResultadoAprovacao
from src.domain.services.autorizacao import AtorWeb
from src.domain.services.reference_storage import PrivateReferenceStorage

logger = logging.getLogger(__name__)
METODOS_IDENTIDADE = {
    "documento_presencial",
    "codigo_institucional",
    "contato_institucional",
}


class RepositorioAprovacaoCadastro(Protocol):
    def aprovar_cadastro(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        metodo_identidade: str,
        justificativa: str,
        agora: dt.datetime,
    ) -> ResultadoAprovacao: ...

    def limpar_arquivos_provisorios(self, solicitacao_id: int) -> tuple[str, ...]: ...

    def confirmar_limpeza_provisoria(
        self, solicitacao_id: int, *, agora: dt.datetime
    ) -> None: ...


class AprovarCadastroWeb:
    def __init__(
        self,
        repositorio: RepositorioAprovacaoCadastro,
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
        metodo_identidade: str,
        justificativa: str,
    ) -> ResultadoAprovacao:
        metodo = metodo_identidade.strip()
        motivo = " ".join(justificativa.split())
        if metodo not in METODOS_IDENTIDADE:
            raise ValueError(
                "Informe um método independente de conferência de identidade."
            )
        if not 10 <= len(motivo) <= 500:
            raise ValueError("A justificativa deve ter entre 10 e 500 caracteres.")
        resultado = self._repositorio.aprovar_cadastro(
            ator,
            solicitacao_id,
            metodo_identidade=metodo,
            justificativa=motivo,
            agora=self._agora(),
        )
        pendente = False
        if not resultado.aluno_existente:
            return resultado
        try:
            caminhos = self._repositorio.limpar_arquivos_provisorios(solicitacao_id)
            for caminho in caminhos:
                self._storage.remover(caminho)
            self._repositorio.confirmar_limpeza_provisoria(
                solicitacao_id, agora=self._agora()
            )
        except Exception as erro:
            pendente = True
            logger.error(
                "Limpeza biométrica provisória pendente para solicitação %s (%s).",
                solicitacao_id,
                type(erro).__name__,
            )
        return ResultadoAprovacao(
            aluno_id=resultado.aluno_id,
            turma_id=resultado.turma_id,
            aluno_existente=resultado.aluno_existente,
            limpeza_pendente=pendente,
        )

    def _agora(self) -> dt.datetime:
        instante = self._relogio()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        return instante.astimezone(dt.UTC)
