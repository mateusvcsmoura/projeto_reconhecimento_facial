"""Camera via OpenCV.

Um dos dois unicos modulos que importam cv2 (o outro e o viewer da CLI).

O prototipo abria e liberava a camera em duas funcoes diferentes, com
`release()` no fim do corpo: qualquer excecao no laco deixava o
dispositivo preso ate reiniciar o processo (problema A17). Aqui o recurso
e liberado por context manager, sempre.
"""

from __future__ import annotations

import logging
from types import TracebackType
from typing import Any

import cv2

from src.domain.errors import CameraIndisponivel, FalhaNaLeituraDaCamera

logger = logging.getLogger(__name__)


class OpenCVCamera:
    def __init__(self, indice: int = 0) -> None:
        self._indice = indice
        self._captura: cv2.VideoCapture | None = None

    def __enter__(self) -> OpenCVCamera:
        captura = cv2.VideoCapture(self._indice)
        if not captura.isOpened():
            captura.release()
            raise CameraIndisponivel(self._indice)

        self._captura = captura
        logger.debug("Camera %s aberta", self._indice)
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
