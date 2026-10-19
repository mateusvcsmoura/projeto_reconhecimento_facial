"""Adapta o resultado 1:1 para a unica transacao que grava presenca web."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.application.services.fila_facial import JobFacial
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ProcessadorJobFacial,
    ResultadoWorker,
)
from src.application.use_cases.verificar_presenca_web import ConcluirPresenca


class ProcessadorPresencaWeb:
    def __init__(
        self,
        verificador: ProcessadorJobFacial,
        conclusao: ConcluirPresenca,
        *,
        relogio: Callable[[], datetime],
    ) -> None:
        self._verificador = verificador
        self._conclusao = conclusao
        self._relogio = relogio

    def processar(self, job: JobFacial, capturas: tuple[bytes, ...]) -> ResultadoWorker:
        resultado = self._verificador.processar(job, capturas)
        if not resultado.sucesso:
            return resultado
        if resultado.resultado_facial is None:
            return ResultadoWorker(False, CodigoResultadoWorker.FALHA_TECNICA)
        try:
            self._conclusao.executar(
                job, resultado.resultado_facial, agora=self._relogio()
            )
        except Exception:
            return ResultadoWorker(
                False,
                CodigoResultadoWorker.FALHA_TECNICA,
                resultado_facial=resultado.resultado_facial,
            )
        return ResultadoWorker(
            True,
            resultado.codigo,
            resultado_facial=resultado.resultado_facial,
            finalizacao_persistida=True,
        )

    def fechar(self) -> None:
        fechar = getattr(self._verificador, "fechar", None)
        if callable(fechar):
            fechar()

    def preaquecer(self) -> None:
        aquecer = getattr(self._verificador, "preaquecer", None)
        if callable(aquecer):
            aquecer()
