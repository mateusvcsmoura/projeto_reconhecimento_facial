from __future__ import annotations

import datetime as dt
import logging
import threading
import uuid
from dataclasses import replace
from pathlib import Path

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    JobFacial,
    ManifestoTemporario,
    TipoJobFacial,
)
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ResultadoWorker,
    WorkerFacial,
    preparar_worker,
)
from src.domain.services.face_recognition import ResultadoFacial
from src.infrastructure.face_recognition.processador_presenca_web import (
    ProcessadorPresencaWeb,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)
from src.infrastructure.workers.singleton_process_lock import SingletonProcessLock

UTC = dt.UTC
AGORA = dt.datetime(2026, 10, 18, 12, tzinfo=UTC)


def _job(job_id: uuid.UUID, *, estado: EstadoJobFacial) -> JobFacial:
    return JobFacial(
        id=job_id,
        dono_id="conta:1",
        tipo=TipoJobFacial.CADASTRO,
        estado=estado,
        criada_em=AGORA,
        prazo=AGORA + dt.timedelta(minutes=5),
        prazo_execucao=AGORA + dt.timedelta(minutes=15),
        atualizada_em=AGORA,
        manifesto=ManifestoTemporario(
            job_id,
            tuple(ArquivoTemporario(i, f"captura-{i}.bin", 4) for i in range(1, 4)),
        ),
        lease=None,
        lease_expira_em=None,
        resultado_codigo=None,
        credencial_hash="a" * 64,
    )


class FilaFake:
    def __init__(self, jobs: list[JobFacial]) -> None:
        self.jobs = jobs
        self.finalizados: list[tuple[uuid.UUID, bool, str]] = []
        self.etapas_aguardadas: list[tuple[uuid.UUID, str]] = []
        self.invalidacoes: list[uuid.UUID] = []
        self.recuperados: set[uuid.UUID] = set()
        self.lease_valido = True
        self._cursor = 0

    def reivindicar(self) -> JobFacial | None:
        while self._cursor < len(self.jobs):
            job = self.jobs[self._cursor]
            self._cursor += 1
            if job.estado is EstadoJobFacial.ENFILEIRADA:
                return replace(
                    job,
                    estado=EstadoJobFacial.PROCESSANDO,
                    lease="opaque-test-lease",
                    lease_expira_em=AGORA + dt.timedelta(minutes=2),
                )
        return None

    def heartbeat(self, _job: JobFacial) -> bool:
        return self.lease_valido

    def finalizar(self, job: JobFacial, *, sucesso: bool, codigo: str) -> bool:
        self.finalizados.append((job.id, sucesso, codigo))
        return self.lease_valido

    def aguardar_proxima_etapa(self, job: JobFacial) -> bool:
        self.etapas_aguardadas.append((job.id, "aguardando_etapa"))
        return self.lease_valido

    def invalidar_apos_execucao(self, job: JobFacial) -> bool:
        self.invalidacoes.append(job.id)
        return True

    def recuperar_apos_reinicio(self) -> set[uuid.UUID]:
        return set(self.recuperados)

    def ids_com_temporarios(self) -> set[uuid.UUID]:
        return {
            job.id
            for job in self.jobs
            if job.estado in (EstadoJobFacial.RECEBIDA, EstadoJobFacial.ENFILEIRADA)
        }


class ProcessorFake:
    def __init__(self) -> None:
        self.capturas_recebidas: list[tuple[bytes, ...]] = []
        self.entrada: threading.Event | None = None
        self.liberar: threading.Event | None = None
        self.erro: Exception | None = None
        self.resultado = ResultadoWorker(True, CodigoResultadoWorker.CONCLUIDA)

    def processar(
        self, _job: JobFacial, capturas: tuple[bytes, ...]
    ) -> ResultadoWorker:
        if self.entrada is not None:
            self.entrada.set()
        if self.liberar is not None:
            self.liberar.wait(timeout=2)
        if self.erro is not None:
            raise self.erro
        self.capturas_recebidas.append(capturas)
        return self.resultado


def _storage(tmp_path: Path, job_id: uuid.UUID) -> TemporaryCaptureStorage:
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=16,
        max_captures=3,
    )
    for ordinal, valor in enumerate((b"one!", b"two!", b"three"), start=1):
        storage.salvar_captura(job_id, ordinal, valor)
    return storage


def test_worker_processa_capturas_em_ordem_e_remove_temporarios(
    tmp_path: Path,
) -> None:
    job_id = uuid.uuid4()
    storage = _storage(tmp_path, job_id)
    processor = ProcessorFake()
    queue = FilaFake([_job(job_id, estado=EstadoJobFacial.ENFILEIRADA)])
    worker = WorkerFacial(
        queue,
        storage,
        processadores={TipoJobFacial.CADASTRO: processor},
    )
    worker.inicializar()

    assert worker.executar_um()

    assert processor.capturas_recebidas == [(b"one!", b"two!", b"three")]
    assert queue.finalizados == [(job_id, True, "concluida")]
    assert not (storage.raiz / str(job_id)).exists()


def test_worker_mantem_slot_ate_executor_terminar(tmp_path: Path) -> None:
    job_id = uuid.uuid4()
    storage = _storage(tmp_path, job_id)
    processor = ProcessorFake()
    processor.entrada = threading.Event()
    processor.liberar = threading.Event()
    queue = FilaFake([_job(job_id, estado=EstadoJobFacial.ENFILEIRADA)])
    worker = WorkerFacial(
        queue,
        storage,
        processadores={TipoJobFacial.CADASTRO: processor},
    )
    worker.inicializar()

    thread = threading.Thread(target=worker.executar_um)
    thread.start()
    assert processor.entrada.wait(timeout=1)
    assert worker.executar_um() is False
    assert queue.finalizados == []

    processor.liberar.set()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert len(queue.finalizados) == 1


def test_worker_libera_slot_e_preserva_temporarios_entre_etapas(
    tmp_path: Path,
) -> None:
    job_id = uuid.uuid4()
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=16,
        max_captures=3,
    )
    storage.salvar_captura(job_id, 1, b"frame")
    processor = ProcessorFake()
    processor.resultado = ResultadoWorker(
        False,
        CodigoResultadoWorker.RECUSA_BIOMETRICA,
        aguardando_etapa=True,
    )
    job = replace(
        _job(job_id, estado=EstadoJobFacial.ENFILEIRADA),
        tipo=TipoJobFacial.PRESENCA,
        manifesto=ManifestoTemporario(
            job_id, (ArquivoTemporario(1, "captura-1.bin", 5),)
        ),
    )
    queue = FilaFake([job])
    worker = WorkerFacial(
        queue,
        storage,
        processadores={TipoJobFacial.PRESENCA: processor},
    )
    worker.inicializar()

    assert worker.executar_um()

    assert queue.etapas_aguardadas == [(job_id, "aguardando_etapa")]
    assert queue.finalizados == []
    assert (storage.raiz / str(job_id) / "captura-1.bin").is_file()


def test_worker_nao_finaliza_lease_apos_commit_transacional_de_presenca(
    tmp_path: Path,
) -> None:
    job_id = uuid.uuid4()
    storage = _storage(tmp_path, job_id)
    processor = ProcessorFake()
    processor.resultado = ResultadoWorker(
        True,
        CodigoResultadoWorker.CONCLUIDA,
        finalizacao_persistida=True,
    )
    job = replace(
        _job(job_id, estado=EstadoJobFacial.ENFILEIRADA),
        tipo=TipoJobFacial.PRESENCA,
    )
    queue = FilaFake([job])
    worker = WorkerFacial(
        queue,
        storage,
        processadores={TipoJobFacial.PRESENCA: processor},
    )
    worker.inicializar()

    assert worker.executar_um()

    assert queue.finalizados == []
    assert queue.invalidacoes == []
    assert not (storage.raiz / str(job_id)).exists()


def test_processador_presenca_persiste_somente_apos_verificacao_positiva() -> None:
    facial = ResultadoFacial(
        identidade_ok=True,
        desafio_ok=True,
        antispoofing_ok=True,
        qualidade_ok=True,
        motivo_tecnico=None,
        versao_referencia=2,
        politica="mediana-3",
    )

    class Verificador:
        def processar(self, _job, _capturas):
            return ResultadoWorker(
                True, CodigoResultadoWorker.CONCLUIDA, resultado_facial=facial
            )

    class Conclusao:
        def __init__(self) -> None:
            self.chamadas = []

        def executar(self, job, resultado, *, agora):
            self.chamadas.append((job, resultado, agora))

    job = _job(uuid.uuid4(), estado=EstadoJobFacial.PROCESSANDO)
    conclusao = Conclusao()
    processador = ProcessadorPresencaWeb(
        Verificador(), conclusao, relogio=lambda: AGORA
    )

    resultado = processador.processar(job, (b"captura",))

    assert resultado.sucesso
    assert resultado.finalizacao_persistida
    assert conclusao.chamadas == [(job, facial, AGORA)]


def test_processador_presenca_nao_persiste_recusa_do_verificador() -> None:
    recusado = ResultadoWorker(False, CodigoResultadoWorker.RECUSA_BIOMETRICA)

    class Verificador:
        def processar(self, _job, _capturas):
            return recusado

    class Conclusao:
        def executar(self, *_args, **_kwargs):
            raise AssertionError("uma recusa não deve gravar presença")

    processador = ProcessadorPresencaWeb(
        Verificador(), Conclusao(), relogio=lambda: AGORA
    )

    assert (
        processador.processar(
            _job(uuid.uuid4(), estado=EstadoJobFacial.PROCESSANDO), (b"captura",)
        )
        is recusado
    )


def test_processador_presenca_nao_confirma_sucesso_sem_decisao_facial() -> None:
    sem_decisao = ResultadoWorker(True, CodigoResultadoWorker.CONCLUIDA)

    class Verificador:
        def processar(self, _job, _capturas):
            return sem_decisao

    class Conclusao:
        def executar(self, *_args, **_kwargs):
            raise AssertionError("não há decisão facial para persistir")

    processador = ProcessadorPresencaWeb(
        Verificador(), Conclusao(), relogio=lambda: AGORA
    )

    resultado = processador.processar(
        _job(uuid.uuid4(), estado=EstadoJobFacial.PROCESSANDO), (b"captura",)
    )

    assert not resultado.sucesso
    assert resultado.codigo is CodigoResultadoWorker.FALHA_TECNICA
    assert not resultado.finalizacao_persistida


def test_processador_presenca_encaminha_ciclo_de_vida_opcional() -> None:
    eventos: list[str] = []

    class Verificador:
        def processar(self, _job, _capturas):
            return ResultadoWorker(False, CodigoResultadoWorker.RECUSA_BIOMETRICA)

        def preaquecer(self):
            eventos.append("preaquecer")

        def fechar(self):
            eventos.append("fechar")

    processador = ProcessadorPresencaWeb(Verificador(), object(), relogio=lambda: AGORA)

    processador.preaquecer()
    processador.fechar()

    assert eventos == ["preaquecer", "fechar"]


def test_processador_presenca_converte_falha_transacional_em_falha_tecnica() -> None:
    facial = ResultadoFacial(
        identidade_ok=True,
        desafio_ok=True,
        antispoofing_ok=True,
        qualidade_ok=True,
        motivo_tecnico=None,
        versao_referencia=2,
        politica="mediana-3",
    )

    class Verificador:
        def processar(self, _job, _capturas):
            return ResultadoWorker(
                True, CodigoResultadoWorker.CONCLUIDA, resultado_facial=facial
            )

    class Conclusao:
        def executar(self, *_args, **_kwargs):
            raise RuntimeError("falha transacional")

    processador = ProcessadorPresencaWeb(
        Verificador(), Conclusao(), relogio=lambda: AGORA
    )

    resultado = processador.processar(
        _job(uuid.uuid4(), estado=EstadoJobFacial.PROCESSANDO), (b"captura",)
    )

    assert not resultado.sucesso
    assert resultado.codigo is CodigoResultadoWorker.FALHA_TECNICA
    assert resultado.resultado_facial is facial
    assert not resultado.finalizacao_persistida


def test_resultado_tardio_nao_e_aceito_e_falha_sanitizada(
    tmp_path: Path, caplog: logging.LogCaptureFixture
) -> None:
    job_id = uuid.uuid4()
    storage = _storage(tmp_path, job_id)
    processor = ProcessorFake()
    processor.erro = RuntimeError("frame-data-secret-path")
    queue = FilaFake([_job(job_id, estado=EstadoJobFacial.ENFILEIRADA)])
    queue.lease_valido = False
    worker = WorkerFacial(
        queue,
        storage,
        processadores={TipoJobFacial.CADASTRO: processor},
    )
    worker.inicializar()

    with caplog.at_level(logging.ERROR):
        assert worker.executar_um()

    assert queue.invalidacoes == [job_id]
    assert "frame-data-secret-path" not in caplog.text
    assert not (storage.raiz / str(job_id)).exists()


def test_worker_reiniciado_remove_job_ativo_interrompido(tmp_path: Path) -> None:
    job_id = uuid.uuid4()
    storage = _storage(tmp_path, job_id)
    queue = FilaFake([])
    queue.recuperados = {job_id}
    worker = WorkerFacial(queue, storage, processadores={})

    worker.inicializar()

    assert not (storage.raiz / str(job_id)).exists()


def test_recuperacao_dos_jobs_precede_aquecimento_dos_modelos() -> None:
    eventos: list[str] = []

    class WorkerFake:
        def inicializar(self) -> None:
            eventos.append("recuperar_jobs")

    def aquecer_modelos() -> None:
        eventos.append("aquecer_modelos")

    preparar_worker(WorkerFake(), aquecer_modelos)

    assert eventos == ["recuperar_jobs", "aquecer_modelos"]


def test_arquivo_ausente_falha_tecnicamente_e_limpa_o_job(
    tmp_path: Path,
) -> None:
    job_id = uuid.uuid4()
    storage = TemporaryCaptureStorage(
        tmp_path / "capturas",
        max_bytes_per_capture=16,
        max_captures=3,
    )
    queue = FilaFake([_job(job_id, estado=EstadoJobFacial.ENFILEIRADA)])
    processor = ProcessorFake()
    worker = WorkerFacial(
        queue,
        storage,
        processadores={TipoJobFacial.CADASTRO: processor},
    )
    worker.inicializar()

    assert worker.executar_um()

    assert queue.finalizados == [(job_id, False, "arquivo_ausente")]
    assert processor.capturas_recebidas == []


def test_janitor_remove_job_cancelado_e_preserva_jobs_aguardando(
    tmp_path: Path,
) -> None:
    cancelado = uuid.uuid4()
    aguardando = uuid.uuid4()
    storage = _storage(tmp_path, cancelado)
    for ordinal, valor in enumerate((b"one!", b"two!", b"three"), start=1):
        storage.salvar_captura(aguardando, ordinal, valor)
    fila = FilaFake([_job(aguardando, estado=EstadoJobFacial.ENFILEIRADA)])
    worker = WorkerFacial(fila, storage, processadores={})

    removidos = worker.reconciliar_temporarios()

    assert removidos == 1
    assert not (storage.raiz / str(cancelado)).exists()
    assert (storage.raiz / str(aguardando)).is_dir()


def test_lock_local_impede_segundo_worker_no_mesmo_diretorio(
    tmp_path: Path,
) -> None:
    caminho = tmp_path / "capturas" / ".worker.lock"

    with (
        SingletonProcessLock(caminho) as primeiro,
        SingletonProcessLock(caminho) as segundo,
    ):
        assert primeiro.adquirido
        assert not segundo.adquirido

    with SingletonProcessLock(caminho) as depois:
        assert depois.adquirido
