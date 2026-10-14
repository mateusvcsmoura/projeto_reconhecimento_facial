"""Provider opcional que envia frames a um worker MediaPipe local."""

from __future__ import annotations

import importlib
import queue
import subprocess
import threading
from contextlib import suppress
from pathlib import Path
from typing import Any

from src.domain.services.facial_landmarks import PontoFacial, ResultadoLandmarks
from src.infrastructure.face_recognition.mediapipe_landmarks_protocol import (
    escrever_mensagem,
    ler_mensagem,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKER_MODULE = "src.infrastructure.face_recognition.mediapipe_landmarks_worker"


class MediaPipeLandmarks:
    """Adaptador CPU persistente durante a janela de cadastro."""

    LARGURA_MAXIMA = 640
    STARTUP_TIMEOUT_SECONDS = 20.0
    INFERENCE_TIMEOUT_SECONDS = 5.0
    SHUTDOWN_TIMEOUT_SECONDS = 3.0

    def __init__(
        self,
        caminho_modelo: str | Path,
        python_executable: str | Path | None = None,
        *,
        cv2_module: Any | None = None,
        numpy_module: Any | None = None,
    ) -> None:
        modelo = Path(caminho_modelo)
        if not modelo.is_absolute():
            modelo = PROJECT_ROOT / modelo
        if not modelo.is_file():
            raise FileNotFoundError(f"Modelo de landmarks não encontrado: {modelo}")

        executavel = Path(
            python_executable
            or (PROJECT_ROOT / ".venv-landmarks" / "Scripts" / "python.exe")
        )
        if not executavel.is_absolute():
            executavel = PROJECT_ROOT / executavel
        if not executavel.is_file():
            raise FileNotFoundError(
                f"Interpretador auxiliar de landmarks não encontrado: {executavel}"
            )

        self._cv2 = cv2_module or importlib.import_module("cv2")
        self._np = numpy_module or importlib.import_module("numpy")
        self._modelo = modelo
        self._executavel = executavel
        self._respostas: queue.Queue[Any] = queue.Queue()
        self._processo: subprocess.Popen[bytes] | None = None
        self._thread_leitora: threading.Thread | None = None
        self._thread_inferencia: threading.Thread | None = None
        self._conexoes: tuple[tuple[int, int], ...] = ()
        self._fechado = False
        self._iniciar_worker()

    def _iniciar_worker(self) -> None:
        argumentos = [
            str(self._executavel),
            "-u",
            "-m",
            WORKER_MODULE,
            str(self._modelo),
        ]
        self._processo = subprocess.Popen(
            argumentos,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        processo = self._processo
        if processo.stdout is None:
            self._encerrar_worker(forcar=True)
            self._fechado = True
            raise RuntimeError("Worker MediaPipe iniciou sem canal de saída")

        self._thread_leitora = threading.Thread(
            target=self._ler_respostas,
            args=(processo.stdout,),
            name="mediapipe-landmarks-reader",
            daemon=True,
        )
        self._thread_leitora.start()
        try:
            resposta = self._aguardar_resposta(
                self.STARTUP_TIMEOUT_SECONDS, "inicialização"
            )
            self._conexoes = self._validar_conexoes(resposta.get("conexoes"))
        except Exception:
            self._encerrar_worker(forcar=True)
            self._fechado = True
            raise

    def _ler_respostas(self, saida: Any) -> None:
        try:
            while True:
                mensagem = ler_mensagem(saida)
                if mensagem is None:
                    self._respostas.put(None)
                    return
                cabecalho, payload = mensagem
                if payload:
                    raise ValueError("Worker enviou payload inesperado")
                self._respostas.put(cabecalho)
        except Exception as exc:
            self._respostas.put(exc)

    def _aguardar_resposta(self, timeout: float | None, etapa: str) -> dict[str, Any]:
        try:
            resposta = (
                self._respostas.get()
                if timeout is None
                else self._respostas.get(timeout=timeout)
            )
        except queue.Empty as exc:
            self._encerrar_worker(forcar=True)
            raise TimeoutError(
                f"Tempo esgotado aguardando {etapa} do worker MediaPipe"
            ) from exc
        if isinstance(resposta, Exception):
            self._encerrar_worker(forcar=True)
            raise RuntimeError(
                f"Falha de comunicação com o worker MediaPipe ({etapa})"
            ) from resposta
        if not isinstance(resposta, dict):
            self._encerrar_worker(forcar=True)
            raise RuntimeError(f"Worker MediaPipe encerrou durante {etapa}")
        if resposta.get("ok") is not True:
            self._encerrar_worker(forcar=True)
            raise RuntimeError(f"Worker MediaPipe falhou durante {etapa}")
        return resposta

    def _executar_inferencia(
        self,
        cabecalho: dict[str, Any],
        pixels: bytes,
        conclusao: queue.Queue[Any],
    ) -> None:
        """Executa a troca bloqueante fora da thread de captura."""
        processo = self._processo
        try:
            if processo is None or processo.stdin is None:
                raise RuntimeError("Worker MediaPipe iniciou sem canal de entrada")
            escrever_mensagem(processo.stdin, cabecalho, pixels)
            conclusao.put(self._aguardar_resposta(None, "inferência"))
        except Exception as exc:
            conclusao.put(exc)

    @staticmethod
    def _validar_conexoes(valor: Any) -> tuple[tuple[int, int], ...]:
        if not isinstance(valor, list):
            raise RuntimeError("Worker MediaPipe retornou conexões inválidas")
        pares: set[tuple[int, int]] = set()
        for par in valor:
            if (
                not isinstance(par, list)
                or len(par) != 2
                or any(
                    isinstance(indice, bool) or not isinstance(indice, int)
                    for indice in par
                )
            ):
                raise RuntimeError("Worker MediaPipe retornou conexões inválidas")
            pares.add((par[0], par[1]))
        return tuple(sorted(pares))

    @staticmethod
    def _validar_rostos(valor: Any) -> tuple[tuple[PontoFacial, ...], ...]:
        if not isinstance(valor, list):
            raise RuntimeError("Worker MediaPipe retornou landmarks inválidos")
        rostos: list[tuple[PontoFacial, ...]] = []
        try:
            for rosto in valor:
                if not isinstance(rosto, list):
                    raise ValueError("formato de rosto inválido")
                pontos: list[PontoFacial] = []
                for ponto in rosto:
                    if not isinstance(ponto, list) or len(ponto) != 3:
                        raise ValueError("formato de ponto inválido")
                    pontos.append(
                        PontoFacial(float(ponto[0]), float(ponto[1]), float(ponto[2]))
                    )
                rostos.append(tuple(pontos))
        except (TypeError, ValueError, IndexError) as exc:
            raise RuntimeError("Worker MediaPipe retornou landmarks inválidos") from exc
        return tuple(rostos)

    def detectar(self, frame: Any, timestamp_ms: int) -> ResultadoLandmarks:
        """Detecta na cópia RGB reduzida sem alterar o frame do cadastro."""
        if self._fechado or self._processo is None:
            raise RuntimeError("Worker MediaPipe não está disponível")
        if not isinstance(timestamp_ms, int) or timestamp_ms < 0:
            raise ValueError("timestamp_ms deve ser um inteiro não negativo")
        if (
            getattr(frame, "ndim", None) != 3
            or frame.shape[2] != 3
            or frame.shape[0] <= 0
            or frame.shape[1] <= 0
            or frame.dtype != self._np.uint8
        ):
            raise ValueError("frame deve ter formato HxWx3, BGR uint8 e não vazio")

        altura, largura = frame.shape[:2]
        if largura > self.LARGURA_MAXIMA:
            nova_altura = max(1, round(altura * self.LARGURA_MAXIMA / largura))
            frame_processado = self._cv2.resize(
                frame,
                (self.LARGURA_MAXIMA, nova_altura),
                self._cv2.INTER_AREA,
            )
        else:
            frame_processado = frame
        rgb = self._cv2.cvtColor(frame_processado, self._cv2.COLOR_BGR2RGB)
        rgb = self._np.ascontiguousarray(rgb).copy()
        cabecalho = {
            "acao": "detectar",
            "altura": int(rgb.shape[0]),
            "largura": int(rgb.shape[1]),
            "timestamp_ms": timestamp_ms,
        }

        conclusao: queue.Queue[Any] = queue.Queue(maxsize=1)
        escritor = threading.Thread(
            target=self._executar_inferencia,
            args=(cabecalho, rgb.tobytes(order="C"), conclusao),
            name="mediapipe-landmarks-inference",
            daemon=True,
        )
        self._thread_inferencia = escritor
        escritor.start()
        try:
            resposta = conclusao.get(timeout=self.INFERENCE_TIMEOUT_SECONDS)
        except queue.Empty as exc:
            self._encerrar_worker(forcar=True)
            self._juntar_thread_inferencia()
            raise TimeoutError(
                "Tempo esgotado na troca com o worker MediaPipe"
            ) from exc
        if isinstance(resposta, Exception):
            self._encerrar_worker(forcar=True)
            self._juntar_thread_inferencia()
            raise RuntimeError("Falha na troca com o Worker MediaPipe") from resposta
        self._juntar_thread_inferencia()
        try:
            rostos = self._validar_rostos(resposta.get("rostos"))
        except RuntimeError:
            self._encerrar_worker(forcar=True)
            raise
        return ResultadoLandmarks(rostos=rostos, conexoes=self._conexoes)

    def _encerrar_worker(self, *, forcar: bool) -> None:
        processo = self._processo
        self._processo = None
        if processo is None:
            return

        if forcar and processo.poll() is None:
            with suppress(OSError):
                processo.terminate()
        elif processo.stdin is not None:
            with suppress(OSError, ValueError):
                processo.stdin.close()

        try:
            processo.wait(timeout=self.SHUTDOWN_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            try:
                processo.terminate()
                processo.wait(timeout=self.SHUTDOWN_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                processo.kill()
                processo.wait(timeout=self.SHUTDOWN_TIMEOUT_SECONDS)
        except OSError:
            with suppress(OSError):
                processo.kill()

        for canal in (processo.stdin, processo.stdout):
            if canal is not None:
                with suppress(OSError, ValueError):
                    canal.close()
        if self._thread_leitora is not None:
            self._thread_leitora.join(timeout=1.0)
            self._thread_leitora = None
        self._juntar_thread_inferencia()

    def _juntar_thread_inferencia(self) -> None:
        thread = self._thread_inferencia
        if thread is None or thread is threading.current_thread():
            return
        thread.join(timeout=1.0)
        if not thread.is_alive():
            self._thread_inferencia = None

    def fechar(self) -> None:
        """Fecha o processo auxiliar e libera recursos, de forma idempotente."""
        if self._fechado:
            return
        self._fechado = True
        self._encerrar_worker(forcar=False)
