"""Criação e revogação de sessões de presença web."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Protocol
from uuid import UUID

from src.domain.entities.sessao_presenca import SessaoPresenca
from src.domain.services.autorizacao import AtorWeb


class RepositorioSessoesPresenca(Protocol):
    def criar_sessao(self, ator: AtorWeb, sessao: SessaoPresenca) -> SessaoPresenca: ...

    def revogar_sessao(
        self, ator: AtorWeb, sessao_id: int, *, agora: dt.datetime
    ) -> tuple[int, tuple[UUID, ...]]: ...


class GerenciarSessoes:
    def __init__(
        self,
        repositorio: RepositorioSessoesPresenca,
        *,
        relogio: Callable[[], dt.datetime],
    ) -> None:
        self._repositorio = repositorio
        self._relogio = relogio

    def criar(
        self,
        ator: AtorWeb,
        *,
        turma_id: int,
        inicio_em: dt.datetime,
        fim_em: dt.datetime,
        titulo: str,
    ) -> SessaoPresenca:
        agora = self._utc(self._relogio())
        sessao = SessaoPresenca.nova(
            turma_id=turma_id,
            criada_por_conta_id=ator.conta_id,
            titulo=titulo,
            inicio_em=inicio_em,
            fim_em=fim_em,
            criada_em=agora,
        )
        return self._repositorio.criar_sessao(ator, sessao)

    def revogar(self, ator: AtorWeb, sessao_id: int) -> tuple[int, tuple[UUID, ...]]:
        if isinstance(sessao_id, bool) or sessao_id <= 0:
            raise ValueError("O identificador da sessão é inválido.")
        return self._repositorio.revogar_sessao(
            ator, sessao_id, agora=self._utc(self._relogio())
        )

    @staticmethod
    def _utc(instante: dt.datetime) -> dt.datetime:
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso horário.")
        return instante.astimezone(dt.UTC)
