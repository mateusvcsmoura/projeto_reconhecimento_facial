"""Composition root do worker facial, separado do runtime HTTP."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.application.services.fila_facial import FilaFacial, TipoJobFacial
from src.application.services.worker_facial import (
    ProcessadorJobFacial,
    WorkerFacial,
    preparar_worker,
)
from src.application.use_cases.anexar_referencias_web import AnexarReferencias
from src.application.use_cases.verificar_presenca_web import ConcluirPresenca
from src.config.web_settings import WebSettings, get_web_settings
from src.domain.services.desafio_captura import DesafioCaptura
from src.domain.services.qualidade_captura import ParametrosQualidade
from src.infrastructure.face_recognition.deepface_adapter import DeepFaceAdapter
from src.infrastructure.face_recognition.desafio_movimento_adapter import (
    DesafioMovimentoAdapter,
)
from src.infrastructure.face_recognition.mediapipe_landmarks import MediaPipeLandmarks
from src.infrastructure.face_recognition.processador_cadastro_web import (
    ProcessadorCadastroWeb,
)
from src.infrastructure.face_recognition.processador_desafio_verificacao import (
    AdaptadorPoseSobDemanda,
    ProcessadorDesafioVerificacao,
)
from src.infrastructure.face_recognition.processador_presenca_web import (
    ProcessadorPresencaWeb,
)
from src.infrastructure.repositories.postgres_desafio_repository import (
    PostgresDesafioRepository,
)
from src.infrastructure.repositories.postgres_job_repository import (
    PostgresJobRepository,
)
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    PostgresPresencaWebRepository,
)
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    PostgresSolicitacaoRepository,
)
from src.infrastructure.storage.private_reference_storage import (
    PrivateReferenceStorageLocal,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)
from src.infrastructure.workers.maintenance_gate import ManutencaoWeb
from src.infrastructure.workers.singleton_process_lock import SingletonProcessLock

logger = logging.getLogger(__name__)


def construir_worker(
    settings: WebSettings,
    *,
    processadores: Mapping[TipoJobFacial, ProcessadorJobFacial] | None = None,
) -> tuple[WorkerFacial, DeepFaceAdapter, Engine, PostgresJobRepository]:
    """Constrói worker e engine sem carregar modelos até a fase de aquecimento."""
    if settings.capture_temp_dir is None:
        raise RuntimeError("WEB_CAPTURE_TEMP_DIR é obrigatório no processo worker.")
    if (
        processadores is None
        and settings.reference_storage_dir is not None
        and settings.mediapipe_model_path is None
    ):
        raise RuntimeError(
            "WEB_MEDIAPIPE_MODEL_PATH é obrigatório para processar cadastros web."
        )
    armazenamento = TemporaryCaptureStorage(
        settings.capture_temp_dir,
        max_bytes_per_capture=settings.capture_max_bytes_per_capture,
        max_captures=settings.capture_max_frames,
        quota_bytes=settings.capture_storage_quota_bytes,
        require_memory_fs=settings.environment == "production",
    )
    engine = create_engine(
        settings.database_url.get_secret_value(), future=True, pool_pre_ping=True
    )
    session_factory: sessionmaker[Session] = sessionmaker(
        bind=engine, expire_on_commit=False, future=True
    )
    jobs_repository = PostgresJobRepository(session_factory)
    fila = FilaFacial(
        jobs_repository,
        segredo=settings.secret_key.get_secret_value().encode(),
        relogio=lambda: datetime.now(UTC),
        limite_aguardando=settings.job_queue_waiting_limit,
        quota_temporaria_bytes=settings.capture_storage_quota_bytes,
        max_bytes_por_captura=settings.capture_max_bytes_per_capture,
        max_capturas=settings.capture_max_frames,
        prazo_maximo_reserva=timedelta(seconds=settings.job_reservation_seconds),
        prazo_maximo_execucao=timedelta(seconds=settings.job_deadline_seconds),
        duracao_lease=timedelta(seconds=settings.job_lease_seconds),
    )
    adapter = DeepFaceAdapter(
        modelo="Facenet512",
        detector="opencv",
        anti_spoofing=True,
        qualidade=ParametrosQualidade(),
        strict_resultado_antispoofing=True,
        sanitizar_erros=True,
    )
    processadores_configurados = processadores
    if processadores_configurados is None:
        processadores_configurados = {}
        solicitacoes_repository = PostgresSolicitacaoRepository(engine)
        pose = None
        if settings.mediapipe_model_path is not None:
            modelo_landmarks = settings.mediapipe_model_path
            python_landmarks = settings.mediapipe_python_executable
            assert python_landmarks is not None
            pose = AdaptadorPoseSobDemanda(
                lambda: DesafioMovimentoAdapter(
                    MediaPipeLandmarks(
                        modelo_landmarks,
                        python_landmarks,
                    )
                )
            )
        if settings.reference_storage_dir is not None:
            assert pose is not None
            private_storage = PrivateReferenceStorageLocal(
                settings.reference_storage_dir
            )
            processadores_configurados[TipoJobFacial.CADASTRO] = ProcessadorCadastroWeb(
                adapter,
                solicitacoes_repository,
                AnexarReferencias(solicitacoes_repository, private_storage),
                pose,
                relogio=lambda: datetime.now(UTC),
            )
        if pose is not None:
            desafio_repository = PostgresDesafioRepository(session_factory)
            referencias_repository = solicitacoes_repository
            desafio = DesafioCaptura(
                desafio_repository,
                segredo=settings.secret_key.get_secret_value().encode(),
            )
            verificador = ProcessadorDesafioVerificacao(
                desafio_repository,
                referencias_repository,
                desafio,
                adapter,
                pose,
                relogio=lambda: datetime.now(UTC),
            )
            presenca_repository = PostgresPresencaWebRepository(
                session_factory, timezone_name=settings.app_timezone
            )
            processadores_configurados[TipoJobFacial.PRESENCA] = ProcessadorPresencaWeb(
                verificador,
                ConcluirPresenca(presenca_repository),
                relogio=lambda: datetime.now(UTC),
            )
    worker = WorkerFacial(
        fila,
        armazenamento,
        processadores=processadores_configurados,
        intervalo_heartbeat_segundos=max(1.0, settings.job_lease_seconds / 3),
    )
    return worker, adapter, engine, jobs_repository


def executar_worker(
    settings: WebSettings | None = None,
    *,
    processadores: Mapping[TipoJobFacial, ProcessadorJobFacial] | None = None,
) -> None:
    configuracao = settings or get_web_settings()
    if configuracao.purpose_end_at is not None and datetime.now(
        UTC
    ) >= configuracao.purpose_end_at.astimezone(UTC):
        logger.info("Worker web encerrado pelo fim autorizado da finalidade.")
        return
    worker, adapter, engine, repository = construir_worker(
        configuracao, processadores=processadores
    )
    assert configuracao.capture_temp_dir is not None
    lock_path = Path(configuracao.capture_temp_dir).expanduser() / ".worker.lock"
    maintenance_gate = (
        ManutencaoWeb(configuracao.maintenance_dir)
        if configuracao.maintenance_dir is not None
        else None
    )
    ready_marker: Path | None = None
    try:
        with SingletonProcessLock(lock_path) as lock:
            if not lock.adquirido:
                raise RuntimeError("Já existe um worker facial ativo nesta máquina.")
            if maintenance_gate is not None:
                ready_marker = maintenance_gate.raiz / ".worker-ready"
                ready_marker.unlink(missing_ok=True)
            with repository.worker_unico() as lock_database:
                if not lock_database:
                    raise RuntimeError(
                        "Já existe um worker facial ativo no PostgreSQL."
                    )

                def aquecer() -> None:
                    adapter.preaquecer_para_web()
                    worker.preaquecer()

                if maintenance_gate is None:
                    preparar_worker(worker, aquecer)
                else:
                    while True:
                        with maintenance_gate.mutacao_worker() as permitido:
                            if permitido:
                                preparar_worker(worker, aquecer)
                                break
                        time.sleep(0.1)
                if ready_marker is not None:
                    _marcar_worker_pronto(ready_marker)
                logger.info("Worker facial inicializado.")
                proxima_limpeza = time.monotonic() + 30
                while True:
                    if maintenance_gate is None:
                        trabalhou = worker.executar_um()
                    else:
                        with maintenance_gate.mutacao_worker() as permitido:
                            trabalhou = worker.executar_um() if permitido else False
                    if not trabalhou:
                        time.sleep(0.5)
                    if time.monotonic() >= proxima_limpeza:
                        worker.reconciliar_temporarios()
                        proxima_limpeza = time.monotonic() + 30
    finally:
        if ready_marker is not None:
            ready_marker.unlink(missing_ok=True)
        worker.fechar()
        engine.dispose()


def _marcar_worker_pronto(caminho: Path) -> None:
    descritor = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descritor, "w", encoding="ascii") as marcador:
            marcador.write("ready\n")
    except Exception:
        caminho.unlink(missing_ok=True)
        raise


def main() -> None:
    executar_worker()


if __name__ == "__main__":
    main()
