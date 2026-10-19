"""Porta única de aplicação para persistir a decisão facial web como presença."""

from __future__ import annotations

import datetime as dt
from typing import Protocol

from src.application.services.fila_facial import JobFacial
from src.domain.entities.tentativa_presenca import ResultadoPresencaPersistida
from src.domain.services.face_recognition import ResultadoFacial


class RepositorioConclusaoPresenca(Protocol):
    def concluir_presenca(
        self,
        job: JobFacial,
        decisao: ResultadoFacial,
        *,
        agora: dt.datetime,
    ) -> ResultadoPresencaPersistida | None: ...


class ConcluirPresenca:
    """Delega ao repositório a transação que também finaliza o job/lease."""

    def __init__(self, repositorio: RepositorioConclusaoPresenca) -> None:
        self._repositorio = repositorio

    def executar(
        self, job: JobFacial, decisao: ResultadoFacial, *, agora: dt.datetime
    ) -> ResultadoPresencaPersistida:
        if (
            job.lease is None
            or job.tipo.value != "presenca"
            or not all(
                (
                    decisao.identidade_ok,
                    decisao.desafio_ok,
                    decisao.antispoofing_ok,
                    decisao.qualidade_ok,
                )
            )
        ):
            raise ValueError("A decisão não autoriza persistir presença.")
        if agora.tzinfo is None or agora.utcoffset() is None:
            raise ValueError("O instante de conclusão deve incluir fuso horário.")
        resultado = self._repositorio.concluir_presenca(
            job, decisao, agora=agora.astimezone(dt.UTC)
        )
        if resultado is None:
            raise PermissionError("A tentativa deixou de estar autorizada.")
        return resultado
