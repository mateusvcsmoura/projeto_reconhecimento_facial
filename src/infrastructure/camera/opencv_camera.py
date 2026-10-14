"""Camera via OpenCV.

A câmera, o viewer e o provider visual opcional são as fronteiras de OpenCV.

O prototipo abria e liberava a camera em duas funcoes diferentes, com
`release()` no fim do corpo: qualquer excecao no laco deixava o
dispositivo preso ate reiniciar o processo (problema A17). Aqui o recurso
e liberado por context manager, sempre.
"""

from __future__ import annotations

import logging
import sys
from types import TracebackType
from typing import Any

import cv2

from src.domain.errors import CameraIndisponivel, FalhaNaLeituraDaCamera

logger = logging.getLogger(__name__)


def _resolver_backend(nome: str) -> int:
    """Traduz o nome vindo da configuracao no identificador do OpenCV.

    No Windows, "auto" escolhe DirectShow. O padrao do OpenCV e o Media
    Foundation, que nesta plataforma leva cerca de 10 s para abrir a camera
    e mais 18 s para aceitar uma mudanca de resolucao -- contra menos de 1 s
    do DirectShow (medido, nao suposto).
    """
    if nome == "auto":
        return cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY

    return {
        "dshow": cv2.CAP_DSHOW,
        "msmf": cv2.CAP_MSMF,
        "any": cv2.CAP_ANY,
    }[nome]


class OpenCVCamera:
    def __init__(
        self,
        indice: int = 0,
        largura: int = 1280,
        altura: int = 720,
        backend: str = "auto",
    ) -> None:
        self._indice = indice
        self._largura = largura
        self._altura = altura
        self._backend = backend
        self._captura: cv2.VideoCapture | None = None

    def __enter__(self) -> OpenCVCamera:
        captura = cv2.VideoCapture(self._indice, _resolver_backend(self._backend))
        if not captura.isOpened():
            captura.release()
            raise CameraIndisponivel(self._indice)

        # Pedido, nao ordem: a camera entrega a resolucao suportada mais
        # proxima. Vale pedir porque o padrao do OpenCV costuma ser 640x480,
        # e um recorte de rosto pequeno degrada tanto o embedding quanto o
        # anti-spoofing.
        captura.set(cv2.CAP_PROP_FRAME_WIDTH, self._largura)
        captura.set(cv2.CAP_PROP_FRAME_HEIGHT, self._altura)

        obtida = (
            int(captura.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(captura.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
        if obtida != (self._largura, self._altura):
            logger.warning(
                "Camera entregou %sx%s (pedido: %sx%s)",
                obtida[0],
                obtida[1],
                self._largura,
                self._altura,
            )
        else:
            logger.info("Camera %s aberta em %sx%s", self._indice, *obtida)

        self._captura = captura
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._captura is not None:
            self._captura.release()
            self._captura = None
            logger.debug("Camera %s liberada", self._indice)

    def ler_frame(self) -> Any:
        if self._captura is None:
            raise FalhaNaLeituraDaCamera("A camera nao foi aberta.")

        ok, frame = self._captura.read()
        if not ok:
            raise FalhaNaLeituraDaCamera(
                f"A camera {self._indice} parou de entregar frames."
            )
        return frame
