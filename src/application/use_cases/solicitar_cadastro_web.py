"""Cria uma solicitação pendente sem reservar matrícula nem criar aluno."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from src.domain.entities.solicitacao_cadastro import SolicitacaoCadastro

PRAZO_MAXIMO = dt.timedelta(days=7)


@dataclass(frozen=True, slots=True)
class DadosCadastroWeb:
    matricula: str
    nome: str


@dataclass(frozen=True, slots=True)
class ContextoConvite:
    referencia: str
    turma_id: int
    expira_em: dt.datetime


@dataclass(frozen=True, slots=True)
class ConsentimentoWeb:
    aceito: bool
    versao: str


class RepositorioSolicitacaoCadastro(Protocol):
    def criar_cadastro(self, **kwargs: object) -> SolicitacaoCadastro: ...


class SolicitarCadastroWeb:
    def __init__(
        self,
        repositorio: RepositorioSolicitacaoCadastro,
        *,
        relogio: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._repositorio = repositorio
        self._relogio = relogio or (lambda: dt.datetime.now(dt.UTC))

    def criar(
        self,
        dados: DadosCadastroWeb,
        contexto_convite: ContextoConvite,
        consentimento: ConsentimentoWeb,
    ) -> SolicitacaoCadastro:
        agora = self._agora()
        matricula = dados.matricula.strip()
        nome = " ".join(dados.nome.split())
        versao = consentimento.versao.strip()
        convite = contexto_convite.referencia.strip()
        if not consentimento.aceito or not versao:
            raise ValueError("O consentimento informado é obrigatório.")
        if not convite or contexto_convite.turma_id <= 0:
            raise ValueError("O contexto de convite é inválido.")
        if not matricula or len(matricula) > 32 or not nome or len(nome) > 255:
            raise ValueError("Matrícula ou nome inválido.")
        if contexto_convite.expira_em <= agora:
            raise ValueError("O convite está expirado.")
        expiracao = min(contexto_convite.expira_em, agora + PRAZO_MAXIMO)
        return self._repositorio.criar_cadastro(
            convite_ref=convite,
            turma_id=contexto_convite.turma_id,
            matricula=matricula,
            nome=nome,
            consentimento_em=agora,
            consentimento_versao=versao,
            expira_em=expiracao,
            criado_em=agora,
        )

    def _agora(self) -> dt.datetime:
        agora = self._relogio()
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        return agora.astimezone(dt.UTC)
