"""Janela de video da CLI.

Junto com o modulo de camera, um dos dois unicos lugares que importam cv2.
Nao decide nada: desenha o que recebe e devolve a tecla pressionada.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import cv2

_FONTE = cv2.FONT_HERSHEY_SIMPLEX


class JanelaDeVideo:
    """Context manager: a janela e sempre fechada, inclusive em excecao."""

    def __init__(self, titulo: str, largura: int = 960, altura: int = 540) -> None:
        self._titulo = titulo
        self._largura = largura
        self._altura = altura

    def __enter__(self) -> JanelaDeVideo:
        # WINDOW_NORMAL torna a janela redimensionavel E faz a imagem
        # acompanhar o redimensionamento. Com o padrao (WINDOW_AUTOSIZE),
        # maximizar a janela so aumenta a moldura: o video continua no
        # tamanho nativo, encolhido num canto.
        cv2.namedWindow(self._titulo, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(self._titulo, self._largura, self._altura)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        cv2.destroyWindow(self._titulo)
        # No Windows a janela so some depois de alguns ciclos de evento.
        cv2.waitKey(1)

    def mostrar(
        self,
        frame: Any,
        linhas: list[tuple[str, tuple[int, int, int]]],
    ) -> int:
        """Desenha sobre uma copia e devolve a tecla pressionada."""
        frame_com_overlay = frame.copy()
        for indice, (texto, cor) in enumerate(linhas):
            y = 40 + indice * 35
            cv2.putText(frame_com_overlay, texto, (20, y), _FONTE, 0.7, cor, 2)

        cv2.imshow(self._titulo, frame_com_overlay)
        return cv2.waitKey(1) & 0xFF
