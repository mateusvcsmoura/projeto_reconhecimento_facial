"""Estado e regras temporais das tentativas de presença por sessão."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from src.domain.entities.sessao_presenca import SessaoPresenca

PRAZO_ENVIO_TENTATIVA = dt.timedelta(seconds=120)


class EstadoTentativaPresenca(StrEnum):
    INICIADA = "iniciada"
    RECEBIDA = "recebida"
    ENFILEIRADA = "enfileirada"
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    EXPIRADA = "expirada"
    REJEITADA = "rejeitada"


ESTADOS_TENTATIVA_ATIVOS = frozenset(
    {
        EstadoTentativaPresenca.INICIADA,
        EstadoTentativaPresenca.RECEBIDA,
        EstadoTentativaPresenca.ENFILEIRADA,
        EstadoTentativaPresenca.PROCESSANDO,
    }
)


@dataclass(frozen=True, slots=True)
class TentativaPresenca:
    id: UUID
    sessao_id: int
    turma_id: int
    aluno_id: int
    ordinal: int
    estado: EstadoTentativaPresenca
    iniciada_em: dt.datetime
    prazo_envio: dt.datetime
    versao_sessao: int
    conjunto_id: int
    versao_referencia: int
    recebida_em: dt.datetime | None = None
    concluida_em: dt.datetime | None = None
    motivo_tecnico: str | None = None

    def __post_init__(self) -> None:
        if (
            self.sessao_id <= 0
            or self.turma_id <= 0
            or self.aluno_id <= 0
            or self.conjunto_id <= 0
            or self.versao_referencia <= 0
            or self.versao_sessao <= 0
            or self.ordinal not in (1, 2, 3)
        ):
            raise ValueError("O escopo ou ordinal da tentativa é inválido.")
        for instante in (self.iniciada_em, self.prazo_envio):
            if instante.tzinfo is None or instante.utcoffset() is None:
                raise ValueError("Os prazos da tentativa devem incluir fuso horário.")
        if self.prazo_envio <= self.iniciada_em:
            raise ValueError("O prazo de envio deve ser posterior à emissão.")
        for instante_opcional in (self.recebida_em, self.concluida_em):
            if instante_opcional is not None and (
                instante_opcional.tzinfo is None
                or instante_opcional.utcoffset() is None
            ):
                raise ValueError(
                    "Os instantes da tentativa devem incluir fuso horário."
                )


@dataclass(frozen=True, slots=True)
class ResultadoPresencaPersistida:
    presenca_id: int
    duplicada: bool


def calcular_prazo_tentativa(sessao: SessaoPresenca, agora: dt.datetime) -> dt.datetime:
    """Permite iniciar na borda inicial, nunca na final; envio tem teto de 120s."""

    if agora.tzinfo is None or agora.utcoffset() is None:
        raise ValueError("O início da tentativa deve incluir fuso horário.")
    instante = agora.astimezone(dt.UTC)
    if sessao.revogada or instante < sessao.inicio_em or instante >= sessao.fim_em:
        raise ValueError("A sessão não está aberta para novas tentativas.")
    return min(
        instante + PRAZO_ENVIO_TENTATIVA,
        sessao.fim_em + PRAZO_ENVIO_TENTATIVA,
    )
