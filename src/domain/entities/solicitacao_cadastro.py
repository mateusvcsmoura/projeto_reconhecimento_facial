"""Metadados nao biometricos de uma solicitacao de cadastro web."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Literal

TipoSolicitacao = Literal["cadastro", "atualizacao"]
EstadoSolicitacao = Literal[
    "em_coleta",
    "em_validacao",
    "pendente_aprovacao",
    "aprovada",
    "rejeitada",
    "cancelada",
    "expirada",
]


@dataclass(frozen=True, slots=True)
class SolicitacaoCadastro:
    """DTO seguro para fluxo de aplicacao; nao contem referencias biometricas."""

    id: int
    tipo: TipoSolicitacao
    estado: EstadoSolicitacao
    turma_id: int
    aluno_id: int | None
    matricula: str | None
    nome: str | None
    expira_em: dt.datetime
    consentimento_em: dt.datetime | None
    consentimento_versao: str | None
    desafio_nonce_hash: str | None = None
    desafio_direcao: str | None = None
    desafio_expira_em: dt.datetime | None = None
    # Metadados para a conferência do professor; preenchidos na listagem da turma.
    criada_em: dt.datetime | None = None
    link_criado_em: dt.datetime | None = None


@dataclass(frozen=True, slots=True)
class ResultadoAprovacao:
    aluno_id: int
    turma_id: int
    aluno_existente: bool
    estado: Literal["aprovada"] = "aprovada"
    limpeza_pendente: bool = False


@dataclass(frozen=True, slots=True)
class ResultadoEncerramento:
    solicitacao_id: int
    estado: Literal["rejeitada", "cancelada"]
    limpeza_pendente: bool = False
