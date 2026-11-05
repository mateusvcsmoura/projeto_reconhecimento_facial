"""Contrato da fonte de imagem.

Existe para que o resto do sistema seja testavel sem webcam e para que a
fonte possa ser trocada -- arquivo, stream de rede -- sem tocar na
orquestracao.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol


class CameraProvider(Protocol):
    """Context manager: o recurso e sempre liberado, inclusive em excecao."""

    def __enter__(self) -> CameraProvider: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def ler_frame(self) -> Any:
        """Devolve o proximo frame.

        Levanta FalhaNaLeituraDaCamera quando a camera para de responder.
        """
        ...
