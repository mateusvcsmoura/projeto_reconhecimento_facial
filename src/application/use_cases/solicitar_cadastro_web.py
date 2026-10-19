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
    finalidade_ate: dt.datetime | None = None


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
        *,
        credencial_acesso_hash: str | None = None,
        desafio_nonce_hash: str | None = None,
        desafio_direcao: str | None = None,
        desafio_expira_em: dt.datetime | None = None,
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
        fim_finalidade = contexto_convite.finalidade_ate or contexto_convite.expira_em
        if fim_finalidade.tzinfo is None or fim_finalidade.utcoffset() is None:
            raise ValueError("O fim da finalidade deve conter fuso horário.")
        expiracao = min(fim_finalidade.astimezone(dt.UTC), agora + PRAZO_MAXIMO)
        if expiracao <= agora:
            raise ValueError("A finalidade do cadastro foi encerrada.")
        desafio = (desafio_nonce_hash, desafio_direcao, desafio_expira_em)
        if any(valor is not None for valor in desafio) and (
            desafio_nonce_hash is None
            or len(desafio_nonce_hash) != 64
            or any(
                caractere not in "0123456789abcdef" for caractere in desafio_nonce_hash
            )
            or desafio_direcao not in {"esquerda", "direita"}
            or desafio_expira_em is None
            or desafio_expira_em.tzinfo is None
            or desafio_expira_em.utcoffset() is None
            or desafio_expira_em.astimezone(dt.UTC) <= agora
            or desafio_expira_em.astimezone(dt.UTC) > expiracao
        ):
            raise ValueError("O desafio de captura é inválido.")
        parametros: dict[str, object] = dict(
            convite_ref=convite,
            turma_id=contexto_convite.turma_id,
            matricula=matricula,
            nome=nome,
            consentimento_em=agora,
            consentimento_versao=versao,
            expira_em=expiracao,
            criado_em=agora,
        )
        if credencial_acesso_hash is not None:
            if len(credencial_acesso_hash) != 64 or any(
                caractere not in "0123456789abcdef"
                for caractere in credencial_acesso_hash
            ):
                raise ValueError("A credencial de acesso é inválida.")
            parametros["credencial_acesso_hash"] = credencial_acesso_hash
        if all(valor is not None for valor in desafio):
            parametros["desafio_nonce_hash"] = desafio_nonce_hash
            parametros["desafio_direcao"] = desafio_direcao
            parametros["desafio_expira_em"] = desafio_expira_em
        return self._repositorio.criar_cadastro(**parametros)

    def _agora(self) -> dt.datetime:
        agora = self._relogio()
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ValueError("O relógio deve retornar um instante com fuso.")
        return agora.astimezone(dt.UTC)
