"""Contrato do adaptador MediaPipe com processo auxiliar local."""

from __future__ import annotations

import importlib
import json
import queue
import struct
import subprocess
import sys
import threading
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.domain.services.facial_landmarks import PontoFacial

CAMINHO = "src.infrastructure.face_recognition.mediapipe_landmarks"
CONEXOES = ((0, 1), (2, 3))
FIM = object()


def _mensagem(valor: dict[str, Any]) -> bytes:
    conteudo = json.dumps(valor, separators=(",", ":")).encode("utf-8")
    return struct.pack("<I", len(conteudo)) + conteudo


class SaidaFalsa:
    def __init__(self) -> None:
        self._fila: queue.Queue[bytes | object] = queue.Queue()
        self._buffer = bytearray()

    def enviar(self, conteudo: bytes) -> None:
        self._fila.put(conteudo)

    def finalizar(self) -> None:
        self._fila.put(FIM)

    def read(self, tamanho: int) -> bytes:
        while len(self._buffer) < tamanho:
            parte = self._fila.get()
            if parte is FIM:
                resultado = bytes(self._buffer)
                self._buffer.clear()
                return resultado
            assert isinstance(parte, bytes)
            self._buffer.extend(parte)
        resultado = bytes(self._buffer[:tamanho])
        del self._buffer[:tamanho]
        return resultado

    def close(self) -> None:
        self.finalizar()


class EntradaFalsa:
    def __init__(self, processo: ProcessoFalso) -> None:
        self._processo = processo
        self.closed = False

    def write(self, conteudo: bytes) -> int:
        if self._processo.bloquear_escrita:
            self._processo.escrita_iniciada.set()
            self._processo.liberar_escrita.wait(timeout=1.0)
            if self._processo.terminado:
                raise BrokenPipeError("processo auxiliar encerrado")
        tamanho = struct.unpack("<I", conteudo[:4])[0]
        cabecalho = json.loads(conteudo[4 : 4 + tamanho])
        pixels = conteudo[4 + tamanho :]
        esperado = cabecalho["altura"] * cabecalho["largura"] * 3
        assert len(pixels) == esperado
        self._processo.pedidos.append((cabecalho, pixels))
        if not self._processo.sem_resposta:
            resposta = (
                self._processo.respostas.pop(0)
                if self._processo.respostas
                else {"ok": True, "rostos": []}
            )
            self._processo.stdout.enviar(_mensagem(resposta))
        return len(conteudo)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self._processo.encerrar()


class ProcessoFalso:
    def __init__(
        self,
        *,
        inicial: dict[str, Any] | None = None,
        respostas: list[dict[str, Any]] | None = None,
        sem_inicial: bool = False,
        sem_resposta: bool = False,
        bloquear_escrita: bool = False,
    ) -> None:
        self.stdout = SaidaFalsa()
        self.respostas = list(respostas or [])
        self.sem_resposta = sem_resposta
        self.bloquear_escrita = bloquear_escrita
        self.escrita_iniciada = threading.Event()
        self.liberar_escrita = threading.Event()
        self.terminado_event = threading.Event()
        self.pedidos: list[tuple[dict[str, Any], bytes]] = []
        self.stdin = EntradaFalsa(self)
        self.terminado = False
        self.esperas = 0
        if not sem_inicial:
            self.stdout.enviar(
                _mensagem(inicial or {"ok": True, "conexoes": [[0, 1], [2, 3]]})
            )

    def encerrar(self) -> None:
        self.stdout.finalizar()

    def poll(self) -> int | None:
        return -1 if self.terminado or self.stdin.closed else None

    def wait(self, timeout: float | None = None) -> int:
        self.esperas += 1
        if not self.terminado and not self.stdin.closed:
            raise subprocess.TimeoutExpired("worker", timeout)
        return 0 if self.stdin.closed else -1

    def terminate(self) -> None:
        self.terminado = True
        self.terminado_event.set()
        self.liberar_escrita.set()
        self.encerrar()

    def kill(self) -> None:
        self.terminate()


class Cv2Falso:
    COLOR_BGR2RGB = 1
    INTER_AREA = 2

    def __init__(self) -> None:
        self.redimensionamentos: list[tuple[tuple[int, ...], tuple[int, int], int]] = []

    def resize(
        self, frame: np.ndarray, tamanho: tuple[int, int], interpolacao: int
    ) -> np.ndarray:
        self.redimensionamentos.append((frame.shape, tamanho, interpolacao))
        escala = frame.shape[1] // tamanho[0]
        return frame[::escala, ::escala]

    def cvtColor(self, frame: np.ndarray, codigo: int) -> np.ndarray:
        assert codigo == self.COLOR_BGR2RGB
        return frame[..., ::-1]


def _preparar_provider(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    processo: ProcessoFalso | None = None,
) -> tuple[Any, ProcessoFalso, list[tuple[list[str], dict[str, Any]]], Path, Path]:
    modulo = importlib.import_module(CAMINHO)
    cv2_falso = Cv2Falso()
    modulo_cv2 = types.ModuleType("cv2")
    modulo_cv2.COLOR_BGR2RGB = cv2_falso.COLOR_BGR2RGB  # type: ignore[attr-defined]
    modulo_cv2.INTER_AREA = cv2_falso.INTER_AREA  # type: ignore[attr-defined]
    modulo_cv2.resize = cv2_falso.resize  # type: ignore[attr-defined]
    modulo_cv2.cvtColor = cv2_falso.cvtColor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "cv2", modulo_cv2)

    arquivo_modelo = tmp_path / "face_landmarker.task"
    arquivo_modelo.write_bytes(b"modelo local")
    executavel = tmp_path / "python.exe"
    executavel.write_bytes(b"python auxiliar")
    filho = processo or ProcessoFalso()
    chamadas: list[tuple[list[str], dict[str, Any]]] = []

    def iniciar(args: list[str], **kwargs: Any) -> ProcessoFalso:
        chamadas.append((args, kwargs))
        return filho

    monkeypatch.setattr(subprocess, "Popen", iniciar)
    monkeypatch.setattr(modulo.MediaPipeLandmarks, "INFERENCE_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(modulo.MediaPipeLandmarks, "STARTUP_TIMEOUT_SECONDS", 0.2)
    provider = modulo.MediaPipeLandmarks(
        arquivo_modelo,
        python_executable=executavel,
        cv2_module=cv2_falso,
        numpy_module=np,
    )
    return provider, filho, chamadas, arquivo_modelo, executavel


def test_provider_envia_rgb_por_pipe_local_e_preserva_frame(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processo = ProcessoFalso(
        respostas=[
            {
                "ok": True,
                "rostos": [[[0.25, 0.75, -0.1]]],
            }
        ]
    )
    provider, processo, chamadas, modelo, executavel = _preparar_provider(
        monkeypatch, tmp_path, processo
    )
    frame = np.zeros((960, 1280, 3), dtype=np.uint8)
    frame[0, 0] = (1, 2, 3)
    original = frame.copy()

    resultado = provider.detectar(frame, 1234)

    assert resultado.rostos == ((PontoFacial(0.25, 0.75, -0.1),),)
    assert resultado.conexoes == CONEXOES
    cabecalho, pixels = processo.pedidos[0]
    assert cabecalho == {
        "acao": "detectar",
        "altura": 480,
        "largura": 640,
        "timestamp_ms": 1234,
        "payload_bytes": 640 * 480 * 3,
    }
    assert tuple(pixels[:3]) == (3, 2, 1)
    assert chamadas[0][0][:2] == [str(executavel), "-u"]
    assert str(modelo) in chamadas[0][0]
    assert chamadas[0][1]["stdin"] == subprocess.PIPE
    assert chamadas[0][1]["stdout"] == subprocess.PIPE
    assert chamadas[0][1]["stderr"] == subprocess.DEVNULL
    np.testing.assert_array_equal(frame, original)

    provider.fechar()
    provider.fechar()
    assert processo.stdin.closed
    assert processo.terminado is False


def test_provider_rejeita_frame_invalido_sem_enviar_ao_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    provider, processo, _, _, _ = _preparar_provider(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="HxWx3"):
        provider.detectar(np.zeros((8, 8), dtype=np.uint8), 1)
    with pytest.raises(ValueError, match="timestamp_ms"):
        provider.detectar(np.zeros((8, 8, 3), dtype=np.uint8), -1)

    assert processo.pedidos == []
    provider.fechar()


def test_worker_devolve_zero_um_ou_dois_rostos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    respostas = [
        {"ok": True, "rostos": []},
        {"ok": True, "rostos": [[[0.5, 0.5, 0.0]]]},
        {"ok": True, "rostos": [[[0.1, 0.2, 0.0]], [[0.8, 0.7, -0.1]]]},
    ]
    provider, processo, _, _, _ = _preparar_provider(
        monkeypatch, tmp_path, ProcessoFalso(respostas=respostas)
    )

    resultados = [
        provider.detectar(np.zeros((8, 8, 3), dtype=np.uint8), timestamp)
        for timestamp in (10, 20, 30)
    ]

    assert [len(resultado.rostos) for resultado in resultados] == [0, 1, 2]
    assert resultados[1].rostos == ((PontoFacial(0.5, 0.5, 0.0),),)
    assert resultados[2].rostos[1] == (PontoFacial(0.8, 0.7, -0.1),)
    provider.fechar()
    assert processo.stdin.closed


def test_worker_auxiliar_ausente_falha_antes_de_iniciar_processo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modulo = importlib.import_module(CAMINHO)
    modelo = tmp_path / "face_landmarker.task"
    modelo.write_bytes(b"modelo local")

    def impedir_inicio(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("não deve iniciar sem o interpretador auxiliar")

    monkeypatch.setattr(subprocess, "Popen", impedir_inicio)

    with pytest.raises(FileNotFoundError, match="Interpretador auxiliar"):
        modulo.MediaPipeLandmarks(
            modelo,
            python_executable=tmp_path / "ausente.exe",
            cv2_module=Cv2Falso(),
            numpy_module=np,
        )


def test_falha_ao_inicializar_runtime_encera_processo_auxiliar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processo = ProcessoFalso(inicial={"ok": False, "erro": "startup_failed"})

    with pytest.raises(RuntimeError, match="Worker MediaPipe falhou"):
        _preparar_provider(monkeypatch, tmp_path, processo)

    assert processo.terminado


def test_timeout_na_inicializacao_encerra_processo_auxiliar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processo = ProcessoFalso(sem_inicial=True)

    with pytest.raises(TimeoutError, match="inicialização"):
        _preparar_provider(monkeypatch, tmp_path, processo)

    assert processo.terminado


def test_falha_de_inferencia_encera_worker_para_permitir_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processo = ProcessoFalso(respostas=[{"ok": False, "erro": "inference_failed"}])
    provider, processo, _, _, _ = _preparar_provider(monkeypatch, tmp_path, processo)

    with pytest.raises(RuntimeError, match="Worker"):
        provider.detectar(np.zeros((8, 8, 3), dtype=np.uint8), 10)

    assert processo.terminado
    provider.fechar()


def test_timeout_encerra_worker_em_vez_de_bloquear_cadastro(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processo = ProcessoFalso(sem_resposta=True)
    provider, processo, _, _, _ = _preparar_provider(monkeypatch, tmp_path, processo)

    with pytest.raises((RuntimeError, TimeoutError), match=r"(?i)worker|tempo"):
        provider.detectar(np.zeros((8, 8, 3), dtype=np.uint8), 10)

    assert processo.terminado


def test_timeout_cobre_escrita_travada_no_pipe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    processo = ProcessoFalso(bloquear_escrita=True)
    provider, processo, _, _, _ = _preparar_provider(monkeypatch, tmp_path, processo)

    with ThreadPoolExecutor(max_workers=1) as executor:
        inferencia = executor.submit(
            provider.detectar, np.zeros((8, 8, 3), dtype=np.uint8), 10
        )
        assert processo.escrita_iniciada.wait(timeout=0.5)
        encerrou_a_tempo = processo.terminado_event.wait(timeout=0.5)
        if not encerrou_a_tempo:
            processo.terminate()
        assert encerrou_a_tempo
        with pytest.raises((RuntimeError, TimeoutError)):
            inferencia.result(timeout=0.5)
        assert provider._thread_inferencia is None


def test_modelo_ausente_nao_abre_processo_nem_importa_mediapipe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modulo = importlib.import_module(CAMINHO)

    importador_original = modulo.importlib.import_module

    def importar_sem_runtime(nome: str, *args: Any, **kwargs: Any) -> Any:
        if nome == "cv2" or nome.startswith("mediapipe"):
            raise AssertionError("runtime nao pode carregar sem modelo")
        return importador_original(nome, *args, **kwargs)

    monkeypatch.setattr(modulo.importlib, "import_module", importar_sem_runtime)

    with pytest.raises(FileNotFoundError, match="Modelo de landmarks"):
        modulo.MediaPipeLandmarks(tmp_path / "ausente.task")
