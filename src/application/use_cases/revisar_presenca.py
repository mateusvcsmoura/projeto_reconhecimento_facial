"""Solicitação e decisão auditada de revisão manual de presença."""

from __future__ import annotations

import datetime as dt
from typing import Protocol
from uuid import UUID

from src.domain.entities.presenca_web import Presenca, RevisaoPresenca, StatusPresenca
from src.domain.services.autorizacao import AtorWeb


class RepositorioRevisaoPresenca(Protocol):
    def solicitar_revisao(self, **kwargs: object) -> RevisaoPresenca: ...

    def decidir_revisao(self, **kwargs: object) -> Presenca: ...


class RevisarPresenca:
    def __init__(self, repositorio: RepositorioRevisaoPresenca) -> None:
        self._repositorio = repositorio

    def solicitar(
        self,
        *,
        sessao_id: int,
        turma_id: int,
        matricula: str,
        link_id: UUID,
        justificativa: str,
        via_acessivel: bool,
        agora: dt.datetime,
        request_id: str | None = None,
    ) -> RevisaoPresenca:
        motivo = _justificativa(justificativa)
        if (
            isinstance(sessao_id, bool)
            or sessao_id <= 0
            or isinstance(turma_id, bool)
            or turma_id <= 0
            or not matricula.strip()
            or len(matricula) > 32
            or not isinstance(via_acessivel, bool)
        ):
            raise ValueError("Os dados da revisão são inválidos.")
        return self._repositorio.solicitar_revisao(
            sessao_id=sessao_id,
            turma_id=turma_id,
            matricula=matricula,
            link_id=link_id,
            justificativa=motivo,
            via_acessivel=via_acessivel,
            agora=_utc(agora),
            request_id=request_id,
        )

    def executar(
        self,
        ator: AtorWeb,
        revisao_id: UUID,
        decisao: str | StatusPresenca,
        justificativa: str,
        versao_esperada: int,
        *,
        identidade_confirmada: bool = False,
        agora: dt.datetime,
        request_id: str | None = None,
    ) -> Presenca:
        motivo = _justificativa(justificativa)
        try:
            estado = StatusPresenca(decisao)
        except ValueError as erro:
            raise ValueError("A decisão deve ser presente ou anulada.") from erro
        if isinstance(versao_esperada, bool) or versao_esperada < 0:
            raise ValueError("A versão esperada é inválida.")
        if not isinstance(identidade_confirmada, bool):
            raise ValueError("A confirmação de identidade é inválida.")
        if estado is StatusPresenca.PRESENTE and not identidade_confirmada:
            raise ValueError(
                "Presença manual exige verificação independente da identidade."
            )
        return self._repositorio.decidir_revisao(
            ator=ator,
            revisao_id=revisao_id,
            decisao=estado,
            justificativa=motivo,
            versao_esperada=versao_esperada,
            identidade_confirmada=identidade_confirmada,
            agora=_utc(agora),
            request_id=request_id,
        )


def _justificativa(valor: str) -> str:
    if not isinstance(valor, str):
        raise ValueError("Informe uma justificativa.")
    limpa = " ".join(valor.split())
    if not limpa or len(limpa) > 500:
        raise ValueError("A justificativa deve conter entre 1 e 500 caracteres.")
    return limpa


def _utc(instante: dt.datetime) -> dt.datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("O instante deve incluir fuso horário.")
    return instante.astimezone(dt.UTC)
