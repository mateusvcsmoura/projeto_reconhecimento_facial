"""Laço de execução serial para trabalhos faciais conhecidos."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from src.application.services.fila_facial import (
    JobFacial,
    TipoJobFacial,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)

logger = logging.getLogger(__name__)


class CodigoResultadoWorker(StrEnum):
    CONCLUIDA = "concluida"
    RECUSA_BIOMETRICA = "recusa_biometrica"
    FALHA_TECNICA = "falha_tecnica"
    ARQUIVO_AUSENTE = "arquivo_ausente"
    MODELO_INDISPONIVEL = "modelo_indisponivel"
    TIPO_NAO_HABILITADO = "tipo_nao_habilitado"


@dataclass(frozen=True)
class ResultadoWorker:
    sucesso: bool
    codigo: CodigoResultadoWorker


class ProcessadorJobFacial(Protocol):
    def processar(
        self, job: JobFacial, capturas: tuple[bytes, ...]
    ) -> ResultadoWorker: ...


class FilaWorker(Protocol):
    def reivindicar(self) -> JobFacial | None: ...

    def heartbeat(self, job: JobFacial) -> bool: ...

    def finalizar(self, job: JobFacial, *, sucesso: bool, codigo: str) -> bool: ...

    def invalidar_apos_execucao(self, job: JobFacial) -> bool: ...

    def recuperar_apos_reinicio(self) -> set[UUID]: ...

    def ids_com_temporarios(self) -> set[UUID]: ...


class WorkerFacial:
    """Executa um job por vez e nunca libera o ativo antes do retorno do handler."""

    def __init__(
        self,
        fila: FilaWorker,
        armazenamento: TemporaryCaptureStorage,
        *,
        processadores: Mapping[TipoJobFacial, ProcessadorJobFacial],
        intervalo_heartbeat_segundos: float = 20.0,
    ) -> None:
        if intervalo_heartbeat_segundos <= 0:
            raise ValueError("O intervalo de heartbeat deve ser positivo.")
        if any(not isinstance(tipo, TipoJobFacial) for tipo in processadores):
            raise ValueError("O worker só aceita tipos faciais conhecidos.")
        self._fila = fila
        self._armazenamento = armazenamento
        self._processadores = dict(processadores)
        self._intervalo_heartbeat = intervalo_heartbeat_segundos
        self._lock_local = threading.Lock()
        self._inicializado = False

    def inicializar(self) -> None:
        """Falha jobs interrompidos e elimina diretórios sem job persistido."""
        interrompidos = self._fila.recuperar_apos_reinicio()
        ids_ativos = self._fila.ids_com_temporarios()
        ids_ativos.difference_update(interrompidos)
        for job_id in interrompidos:
            self._remover_temporarios(job_id)
        self._armazenamento.limpar_orfaos(ids_ativos)
        self._armazenamento.validar_quota_disponivel()
        self._inicializado = True

    def reconciliar_temporarios(self) -> int:
        """Apaga arquivos de jobs cancelados/expirados e diretórios órfãos."""
        return self._armazenamento.limpar_orfaos(self._fila.ids_com_temporarios())

    def executar_um(self) -> bool:
        if not self._inicializado:
            raise RuntimeError("O worker precisa ser inicializado antes do polling.")
        if not self._lock_local.acquire(blocking=False):
            return False
        try:
            job = self._fila.reivindicar()
            if job is None:
                return False
            self._executar_job(job)
            return True
        finally:
            self._lock_local.release()

    def _executar_job(self, job: JobFacial) -> None:
        parar_heartbeat = threading.Event()
        heartbeat_perdido = threading.Event()
        thread_heartbeat = threading.Thread(
            target=self._manter_lease,
            args=(job, parar_heartbeat, heartbeat_perdido),
            name=f"heartbeat-{job.id}",
            daemon=True,
        )
        thread_heartbeat.start()
        finalizado = False
        resultado = ResultadoWorker(False, CodigoResultadoWorker.FALHA_TECNICA)
        try:
            if job.manifesto is None:
                resultado = ResultadoWorker(
                    False, CodigoResultadoWorker.ARQUIVO_AUSENTE
                )
            elif (
                job.tipo is TipoJobFacial.CADASTRO and len(job.manifesto.capturas) != 3
            ):
                resultado = ResultadoWorker(False, CodigoResultadoWorker.FALHA_TECNICA)
            else:
                processador = self._processadores.get(job.tipo)
                if processador is None:
                    resultado = ResultadoWorker(
                        False, CodigoResultadoWorker.TIPO_NAO_HABILITADO
                    )
                else:
                    capturas = tuple(
                        self._armazenamento.ler_captura(job.id, captura.nome)
                        for captura in sorted(
                            job.manifesto.capturas, key=lambda item: item.ordinal
                        )
                    )
                    resultado = processador.processar(job, capturas)
                    if not isinstance(resultado, ResultadoWorker):
                        resultado = ResultadoWorker(
                            False, CodigoResultadoWorker.FALHA_TECNICA
                        )
            if heartbeat_perdido.is_set():
                resultado = ResultadoWorker(False, CodigoResultadoWorker.FALHA_TECNICA)
            finalizado = self._fila.finalizar(
                job,
                sucesso=resultado.sucesso and not heartbeat_perdido.is_set(),
                codigo=resultado.codigo.value,
            )
            if not finalizado:
                self._fila.invalidar_apos_execucao(job)
        except FileNotFoundError:
            finalizado = self._fila.finalizar(
                job,
                sucesso=False,
                codigo=CodigoResultadoWorker.ARQUIVO_AUSENTE.value,
            )
            if not finalizado:
                self._fila.invalidar_apos_execucao(job)
        except Exception:
            logger.error("Job facial falhou; detalhes técnicos foram suprimidos.")
            finalizado = self._fila.finalizar(
                job,
                sucesso=False,
                codigo=CodigoResultadoWorker.FALHA_TECNICA.value,
            )
            if not finalizado:
                self._fila.invalidar_apos_execucao(job)
        finally:
            parar_heartbeat.set()
            thread_heartbeat.join()
            self._remover_temporarios(job.id)

    def _manter_lease(
        self,
        job: JobFacial,
        parar: threading.Event,
        perdido: threading.Event,
    ) -> None:
        while not parar.wait(self._intervalo_heartbeat):
            try:
                if not self._fila.heartbeat(job):
                    perdido.set()
                    return
            except Exception:
                perdido.set()
                return

    def _remover_temporarios(self, job_id: UUID) -> None:
        try:
            self._armazenamento.remover_job(job_id)
        except OSError:
            logger.error("Falha ao remover temporários do job %s.", job_id)


def preparar_worker(worker: WorkerFacial, aquecer_modelos: Callable[[], None]) -> None:
    """Recupera jobs interrompidos antes de qualquer falha no aquecimento ML."""
    worker.inicializar()
    aquecer_modelos()
