"""Mede o custo do worker com jobs sintéticos, sem inferência nem dados reais."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import tempfile
import time
from collections.abc import Sequence
from ctypes import wintypes
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    FilaCheia,
    JobFacial,
    ManifestoTemporario,
    TipoJobFacial,
)
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ResultadoWorker,
    WorkerFacial,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)

_LIMITE_FILA = 10
_NIVEIS_CARGA = ((1, "1"), (2, "2"), (5, "5"), (10, "10"), (11, "excesso"))
_CAPTURAS_SINTETICAS = (
    b"frame-sintetico-1",
    b"frame-sintetico-2",
    b"frame-sintetico-3",
)


class _FilaSintetica:
    """Fila em memória limitada, usada somente pelo benchmark fake."""

    def __init__(self, limite: int) -> None:
        self._limite = limite
        self._pendentes: list[JobFacial] = []
        self._ativos: dict[UUID, JobFacial] = {}
        self.resultados: dict[UUID, tuple[bool, str]] = {}

    def adicionar(self, job: JobFacial) -> None:
        if len(self._pendentes) >= self._limite:
            raise FilaCheia()
        self._pendentes.append(job)
        self._ativos[job.id] = job

    def reivindicar(self) -> JobFacial | None:
        if not self._pendentes:
            return None
        job = self._pendentes.pop(0)
        agora = datetime.now(UTC)
        em_processamento = replace(
            job,
            estado=EstadoJobFacial.PROCESSANDO,
            lease="lease-sintetico",
            lease_expira_em=agora + timedelta(minutes=2),
            atualizada_em=agora,
        )
        self._ativos[job.id] = em_processamento
        return em_processamento

    def heartbeat(self, _job: JobFacial) -> bool:
        return True

    def finalizar(self, job: JobFacial, *, sucesso: bool, codigo: str) -> bool:
        self.resultados[job.id] = (sucesso, codigo)
        self._ativos.pop(job.id, None)
        return True

    def aguardar_proxima_etapa(self, _job: JobFacial) -> bool:
        return False

    def invalidar_apos_execucao(self, job: JobFacial) -> bool:
        self._ativos.pop(job.id, None)
        return True

    def recuperar_apos_reinicio(self) -> set[UUID]:
        return set()

    def ids_com_temporarios(self) -> set[UUID]:
        return set(self._ativos)


class _ProcessadorSintetico:
    def __init__(
        self, atraso_frio_ms: float, atraso_quente_ms: float, falha_a_cada: int
    ) -> None:
        self._atraso_frio = atraso_frio_ms / 1000
        self._atraso_quente = atraso_quente_ms / 1000
        self._falha_a_cada = falha_a_cada
        self._chamadas = 0
        self.latencias_ms: list[float] = []

    def preaquecer(self) -> None:
        if self._atraso_frio:
            time.sleep(self._atraso_frio)

    def processar(
        self, _job: JobFacial, capturas: tuple[bytes, ...]
    ) -> ResultadoWorker:
        inicio = time.perf_counter()
        self._chamadas += 1
        try:
            if len(capturas) != 3 or any(not captura for captura in capturas):
                return ResultadoWorker(False, CodigoResultadoWorker.FALHA_TECNICA)
            if self._atraso_quente:
                time.sleep(self._atraso_quente)
            if self._falha_a_cada and self._chamadas % self._falha_a_cada == 0:
                raise RuntimeError("falha sintética solicitada")
            return ResultadoWorker(True, CodigoResultadoWorker.CONCLUIDA)
        finally:
            self.latencias_ms.append((time.perf_counter() - inicio) * 1000)


def _job_sintetico(agora: datetime) -> JobFacial:
    job_id = uuid4()
    manifesto = ManifestoTemporario(
        job_id=job_id,
        capturas=tuple(
            ArquivoTemporario(ordinal, f"captura-{ordinal}.bin", len(conteudo))
            for ordinal, conteudo in enumerate(_CAPTURAS_SINTETICAS, start=1)
        ),
    )
    return JobFacial(
        id=job_id,
        dono_id="benchmark-sintetico",
        tipo=TipoJobFacial.CADASTRO,
        estado=EstadoJobFacial.ENFILEIRADA,
        criada_em=agora,
        prazo=agora + timedelta(minutes=5),
        prazo_execucao=agora + timedelta(minutes=15),
        atualizada_em=agora,
        manifesto=manifesto,
        lease=None,
        lease_expira_em=None,
        resultado_codigo=None,
        credencial_hash="0" * 64,
    )


def _percentil(valores: Sequence[float], percentil: float) -> float | None:
    if not valores:
        return None
    ordenados = sorted(valores)
    indice = (len(ordenados) - 1) * percentil
    inferior = int(indice)
    superior = min(inferior + 1, len(ordenados) - 1)
    fracao = indice - inferior
    return round(ordenados[inferior] * (1 - fracao) + ordenados[superior] * fracao, 3)


def _medir_nivel(
    nivel: int,
    rotulo: str,
    *,
    atraso_frio_ms: float,
    atraso_quente_ms: float,
    falha_a_cada: int,
    chegada_por_segundo: float,
) -> dict[str, Any]:
    fila = _FilaSintetica(_LIMITE_FILA)
    processador = _ProcessadorSintetico(atraso_frio_ms, atraso_quente_ms, falha_a_cada)
    total_tentativas = nivel
    agora = datetime.now(UTC)

    with tempfile.TemporaryDirectory(prefix="facediff-benchmark-") as pasta:
        armazenamento = TemporaryCaptureStorage(
            Path(pasta), max_bytes_per_capture=1024, quota_bytes=3072
        )
        inicio_admissao = time.perf_counter()
        aceitos = 0
        recusados = 0
        for indice in range(nivel):
            if chegada_por_segundo > 0 and indice:
                time.sleep(1 / chegada_por_segundo)
            job = _job_sintetico(agora)
            try:
                fila.adicionar(job)
            except FilaCheia:
                recusados += 1
                continue
            aceitos += 1
            for ordinal, conteudo in enumerate(_CAPTURAS_SINTETICAS, start=1):
                armazenamento.salvar_captura(job.id, ordinal, conteudo)
        duracao_admissao = time.perf_counter() - inicio_admissao

        worker = WorkerFacial(
            fila,
            armazenamento,  # type: ignore[arg-type]
            processadores={TipoJobFacial.CADASTRO: processador},
            intervalo_heartbeat_segundos=3600,
        )
        inicio_frio = time.perf_counter()
        worker.inicializar()
        worker.preaquecer()
        latencia_fria_ms = (time.perf_counter() - inicio_frio) * 1000
        inicio_processamento = time.perf_counter()
        latencias_worker_ms: list[float] = []
        while True:
            inicio_job = time.perf_counter()
            executado = worker.executar_um()
            if not executado:
                break
            latencias_worker_ms.append((time.perf_counter() - inicio_job) * 1000)
        duracao_processamento = time.perf_counter() - inicio_processamento
        worker.fechar()

    processados = len(fila.resultados)
    falhas = sum(not sucesso for sucesso, _ in fila.resultados.values())
    latencias = processador.latencias_ms
    taxa_medida = total_tentativas / duracao_admissao if duracao_admissao else None
    throughput = processados / duracao_processamento if duracao_processamento else None
    return {
        "rotulo": rotulo,
        "tentativas": total_tentativas,
        "aceitos": aceitos,
        "recusados": recusados,
        "processados": processados,
        "falhas": falhas,
        "pico_fila": aceitos,
        "taxa_chegada_configurada_por_s": chegada_por_segundo,
        "taxa_chegada_medida_por_s": round(taxa_medida, 3) if taxa_medida else None,
        "latencia_fria_ms": round(latencia_fria_ms, 3),
        "latencia_quente_ms": {
            "p50": _percentil(latencias, 0.50),
            "p95": _percentil(latencias, 0.95),
        },
        "latencia_worker_ms": {
            "p50": _percentil(latencias_worker_ms, 0.50),
            "p95": _percentil(latencias_worker_ms, 0.95),
        },
        "duracao_admissao_ms": round(duracao_admissao * 1000, 3),
        "duracao_processamento_ms": round(duracao_processamento * 1000, 3),
        "throughput_fake_jobs_por_s": round(throughput, 3) if throughput else None,
    }


def _memoria_host() -> dict[str, int | None]:
    caminho = Path("/proc/meminfo")
    if caminho.is_file():
        valores: dict[str, int] = {}
        for linha in caminho.read_text(encoding="ascii").splitlines():
            partes = linha.split()
            if len(partes) >= 2 and partes[0] in {"MemTotal:", "MemAvailable:"}:
                valores[partes[0]] = int(partes[1]) * 1024
        return {
            "ram_host_total_bytes": valores.get("MemTotal:"),
            "ram_host_disponivel_bytes": valores.get("MemAvailable:"),
        }
    if os.name == "nt":

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        memoria = _MemoryStatusEx()
        memoria.dwLength = ctypes.sizeof(memoria)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        global_memory_status = kernel32.GlobalMemoryStatusEx
        global_memory_status.argtypes = [ctypes.POINTER(_MemoryStatusEx)]
        global_memory_status.restype = wintypes.BOOL
        if global_memory_status(ctypes.byref(memoria)):
            return {
                "ram_host_total_bytes": int(memoria.ullTotalPhys),
                "ram_host_disponivel_bytes": int(memoria.ullAvailPhys),
            }
    return {"ram_host_total_bytes": None, "ram_host_disponivel_bytes": None}


def _rss_processo() -> int | None:
    status = Path("/proc/self/status")
    if status.is_file():
        for linha in status.read_text(encoding="ascii").splitlines():
            if linha.startswith("VmRSS:"):
                return int(linha.split()[1]) * 1024
    if os.name == "nt":

        class _ProcessMemoryCountersEx(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]

        counters = _ProcessMemoryCountersEx()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        get_process_memory_info = psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_ProcessMemoryCountersEx),
            wintypes.DWORD,
        ]
        get_process_memory_info.restype = wintypes.BOOL
        sucesso = get_process_memory_info(
            get_current_process(), ctypes.byref(counters), counters.cb
        )
        if sucesso:
            return int(counters.WorkingSetSize)
    return None


def _pss_processo() -> int | None:
    rollup = Path("/proc/self/smaps_rollup")
    if not rollup.is_file():
        return None
    for linha in rollup.read_text(encoding="ascii").splitlines():
        if linha.startswith("Pss:"):
            return int(linha.split()[1]) * 1024
    return None


def criar_relatorio(
    *,
    atraso_frio_ms: float = 0.0,
    atraso_quente_ms: float = 0.0,
    falha_a_cada: int = 0,
    chegada_por_segundo: float = 0.0,
) -> dict[str, Any]:
    if min(atraso_frio_ms, atraso_quente_ms, chegada_por_segundo) < 0:
        raise ValueError("Atrasos e taxa de chegada não podem ser negativos.")
    if falha_a_cada < 0:
        raise ValueError("A frequência de falha falsa não pode ser negativa.")

    memoria = _memoria_host()
    rss_inicio = _rss_processo()
    pss_inicio = _pss_processo()
    cpu_inicio = time.process_time()
    relogio_inicio = time.perf_counter()
    resultados = [
        _medir_nivel(
            nivel,
            rotulo,
            atraso_frio_ms=atraso_frio_ms,
            atraso_quente_ms=atraso_quente_ms,
            falha_a_cada=falha_a_cada,
            chegada_por_segundo=chegada_por_segundo,
        )
        for nivel, rotulo in _NIVEIS_CARGA
    ]
    duracao = time.perf_counter() - relogio_inicio
    cpu = time.process_time() - cpu_inicio
    return {
        "versao_schema": 1,
        "gerado_em_utc": datetime.now(UTC).isoformat(),
        "carga": {"tipo": "fake", "inferencia_real": False},
        "ambiente": {
            "sistema": platform.system(),
            "versao": platform.release(),
            "arquitetura": platform.machine(),
            "python": platform.python_version(),
            "cpu_logicas": os.cpu_count(),
        },
        "limites": {
            "fila_maxima_fake": _LIMITE_FILA,
            "atraso_frio_fake_ms": atraso_frio_ms,
            "atraso_quente_fake_ms": atraso_quente_ms,
            "falha_falsa_a_cada": falha_a_cada,
            "nao_representa_capacidade_produtiva": True,
        },
        "recursos": {
            **memoria,
            "rss_inicio_bytes": rss_inicio,
            "rss_fim_bytes": _rss_processo(),
            "pss_inicio_bytes": pss_inicio,
            "pss_fim_bytes": _pss_processo(),
            "cpu_processo_percentual": round(cpu / duracao * 100, 3)
            if duracao
            else None,
        },
        "resultados": resultados,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atraso-frio-ms", type=float, default=0.0)
    parser.add_argument("--atraso-quente-ms", type=float, default=0.0)
    parser.add_argument("--falha-falsa-a-cada", type=int, default=0)
    parser.add_argument("--chegada-por-segundo", type=float, default=0.0)
    args = parser.parse_args(argv)
    try:
        relatorio = criar_relatorio(
            atraso_frio_ms=args.atraso_frio_ms,
            atraso_quente_ms=args.atraso_quente_ms,
            falha_a_cada=args.falha_falsa_a_cada,
            chegada_por_segundo=args.chegada_por_segundo,
        )
    except ValueError as erro:
        parser.error(str(erro))
    print(json.dumps(relatorio, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
