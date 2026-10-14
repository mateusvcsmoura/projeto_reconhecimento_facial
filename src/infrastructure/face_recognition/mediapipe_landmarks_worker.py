"""Worker MediaPipe. O runtime biométrico permanece fora do processo principal."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from src.infrastructure.face_recognition.mediapipe_landmarks_protocol import (
    MAX_PAYLOAD_BYTES,
    escrever_mensagem,
    ler_mensagem,
)


@dataclass(frozen=True)
class _Runtime:
    landmarker: Any
    imagem: Any
    formato_srgb: Any
    conexoes: tuple[tuple[int, int], ...]


def _criar_runtime(caminho_modelo: Path) -> _Runtime:
    mp = importlib.import_module("mediapipe")
    base_options_module = importlib.import_module(
        "mediapipe.tasks.python.core.base_options"
    )
    face_landmarker_module = importlib.import_module(
        "mediapipe.tasks.python.vision.face_landmarker"
    )
    running_mode_module = importlib.import_module(
        "mediapipe.tasks.python.vision.core.vision_task_running_mode"
    )
    BaseOptions = base_options_module.BaseOptions
    FaceLandmarker = face_landmarker_module.FaceLandmarker
    FaceLandmarkerOptions = face_landmarker_module.FaceLandmarkerOptions
    FaceLandmarksConnections = face_landmarker_module.FaceLandmarksConnections
    VisionTaskRunningMode = running_mode_module.VisionTaskRunningMode

    opcoes = FaceLandmarkerOptions(
        base_options=BaseOptions(
            model_asset_path=str(caminho_modelo),
            delegate=BaseOptions.Delegate.CPU,
        ),
        running_mode=VisionTaskRunningMode.VIDEO,
        num_faces=2,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
    )
    landmarker = FaceLandmarker.create_from_options(opcoes)
    nomes = (
        "FACE_LANDMARKS_FACE_OVAL",
        "FACE_LANDMARKS_LEFT_EYE",
        "FACE_LANDMARKS_RIGHT_EYE",
        "FACE_LANDMARKS_LEFT_EYEBROW",
        "FACE_LANDMARKS_RIGHT_EYEBROW",
        "FACE_LANDMARKS_LIPS",
    )
    pares: set[tuple[int, int]] = set()
    for nome in nomes:
        for conexao in getattr(FaceLandmarksConnections, nome, ()):
            origem = getattr(conexao, "start", None)
            destino = getattr(conexao, "end", None)
            if origem is None or destino is None:
                try:
                    origem, destino = conexao
                except (TypeError, ValueError):
                    continue
            pares.add((int(origem), int(destino)))
    return _Runtime(
        landmarker=landmarker,
        imagem=mp.Image,
        formato_srgb=mp.ImageFormat.SRGB,
        conexoes=tuple(sorted(pares)),
    )


def _serializar_rostos(resultado: Any) -> list[list[list[float]]]:
    return [
        [[float(ponto.x), float(ponto.y), float(ponto.z)] for ponto in pontos]
        for pontos in (getattr(resultado, "face_landmarks", None) or ())
    ]


def servir(
    caminho_modelo: Path,
    entrada: BinaryIO,
    saida: BinaryIO,
    *,
    criar_runtime: Callable[[Path], _Runtime] = _criar_runtime,
) -> int:
    """Processa frames somente enquanto o processo pai mantiver o pipe aberto."""
    try:
        runtime = criar_runtime(caminho_modelo)
    except Exception:
        with suppress(BrokenPipeError, OSError):
            escrever_mensagem(saida, {"ok": False, "erro": "startup_failed"})
        return 1

    codigo_saida = 0
    try:
        escrever_mensagem(
            saida,
            {
                "ok": True,
                "conexoes": [list(par) for par in runtime.conexoes],
            },
        )
        while True:
            mensagem = ler_mensagem(entrada)
            if mensagem is None:
                break
            cabecalho, payload = mensagem
            altura = cabecalho.get("altura")
            largura = cabecalho.get("largura")
            timestamp_ms = cabecalho.get("timestamp_ms")
            if (
                cabecalho.get("acao") != "detectar"
                or isinstance(altura, bool)
                or not isinstance(altura, int)
                or altura <= 0
                or isinstance(largura, bool)
                or not isinstance(largura, int)
                or not 0 < largura <= 640
                or isinstance(timestamp_ms, bool)
                or not isinstance(timestamp_ms, int)
                or timestamp_ms < 0
                or altura * largura * 3 != len(payload)
                or len(payload) > MAX_PAYLOAD_BYTES
            ):
                escrever_mensagem(saida, {"ok": False, "erro": "invalid_frame"})
                codigo_saida = 1
                break

            rgb = np.frombuffer(payload, dtype=np.uint8).reshape((altura, largura, 3))
            imagem = runtime.imagem(image_format=runtime.formato_srgb, data=rgb)
            try:
                resultado = runtime.landmarker.detect_for_video(imagem, timestamp_ms)
            except Exception:
                escrever_mensagem(saida, {"ok": False, "erro": "inference_failed"})
                codigo_saida = 1
                break
            escrever_mensagem(
                saida,
                {"ok": True, "rostos": _serializar_rostos(resultado)},
            )
    except (EOFError, OSError, ValueError):
        codigo_saida = 1
    finally:
        try:
            runtime.landmarker.close()
        except Exception:
            codigo_saida = 1
    return codigo_saida


def main() -> int:
    if len(sys.argv) != 2:
        return 2
    return servir(Path(sys.argv[1]), sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
