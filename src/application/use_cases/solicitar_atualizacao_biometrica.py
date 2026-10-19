"""Solicita atualização biométrica sem desativar a versão ainda válida."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Protocol

from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro
from src.domain.services.autorizacao import AtorWeb


class RepositorioAtualizacaoBiometrica(Protocol):
    def solicitar_atualizacao_biometrica(
        self,
        ator: AtorWeb,
        aluno_id: int,
        turma_id: int,
        *,
        expira_em: dt.datetime,
        agora: dt.datetime,
        credencial_captura_hash: str | None = None,
    ) -> SolicitacaoCadastro: ...


class SolicitarAtualizacaoBiometrica:
    def __init__(
        self,
        repositorio: RepositorioAtualizacaoBiometrica,
        *,
        relogio: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._relogio = relogio or (lambda: dt.datetime.now(dt.UTC))

    def executar(
        self,
        ator: AtorWeb,
        aluno_id: int,
        turma_id: int,
        *,
        expira_em: dt.datetime,
        credencial_captura_hash: str | None = None,
    ) -> SolicitacaoCadastro:
        agora = self._agora()
        if expira_em.tzinfo is None or expira_em.utcoffset() is None:
            raise ValueError("A expiração deve conter fuso horário.")
        if credencial_captura_hash is not None and (
            len(credencial_captura_hash) != 64
            or any(
                caractere not in "0123456789abcdef"
                for caractere in credencial_captura_hash
            )
        ):
            raise ValueError("A credencial de captura é inválida.")
        limite = agora + dt.timedelta(days=7)
        expiracao = min(expira_em.astimezone(dt.UTC), limite)
        if expiracao <= agora:
            raise ValueError("A solicitação deve expirar no futuro.")
        return self._repositorio.solicitar_atualizacao_biometrica(
            ator,
            aluno_id,
            turma_id,
            expira_em=expiracao,
            agora=agora,
            credencial_captura_hash=credencial_captura_hash,
        )

    def _agora(self) -> dt.datetime:
        instante = self._relogio()
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        return instante.astimezone(dt.UTC)
