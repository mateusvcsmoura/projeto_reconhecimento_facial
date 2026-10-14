"""Janela de vídeo da CLI e fronteira de desenho da prévia.

O módulo não toma decisões biométricas: desenha sobre cópia, recebe provider
visual opcional e devolve a tecla pressionada.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from types import TracebackType
from typing import Any

import cv2

from src.domain.services.facial_landmarks import LandmarksProvider
from src.presentation.cli.landmarks_overlay import desenhar_landmarks

logger = logging.getLogger(__name__)

_FONTE = cv2.FONT_HERSHEY_SIMPLEX


class JanelaDeVideo:
    """Context manager: a janela e sempre fechada, inclusive em excecao."""

    def __init__(
        self,
        titulo: str,
        largura: int = 960,
        altura: int = 540,
        *,
        criar_landmarks: Callable[[], LandmarksProvider] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._criar_landmarks = criar_landmarks
        self._monotonic_ns = monotonic_ns
        self._provider_landmarks: LandmarksProvider | None = None
        self._ultimo_timestamp_ms = -1
        self._landmarks_indisponiveis = False
        self._alertou_landmarks = False
        self._titulo = titulo
        self._largura = largura
        self._altura = altura

    def _desativar_landmarks(self) -> None:
        provider = self._provider_landmarks
        self._provider_landmarks = None
        self._landmarks_indisponiveis = True
        if provider is not None:
            try:
                provider.fechar()
            except Exception:
                logger.warning("falha ao fechar provider de landmarks", exc_info=True)
        if not self._alertou_landmarks:
            logger.warning("landmarks indisponiveis: continuando sem sobreposicao")
            self._alertou_landmarks = True

    def __enter__(self) -> JanelaDeVideo:
        self._provider_landmarks = None
        self._ultimo_timestamp_ms = -1
        self._landmarks_indisponiveis = False
        self._alertou_landmarks = False
        # WINDOW_NORMAL torna a janela redimensionavel E faz a imagem
        # acompanhar o redimensionamento. Com o padrao (WINDOW_AUTOSIZE),
        # maximizar a janela so aumenta a moldura: o video continua no
        # tamanho nativo, encolhido num canto.
        cv2.namedWindow(self._titulo, cv2.WINDOW_NORMAL)
        try:
            cv2.resizeWindow(self._titulo, self._largura, self._altura)
        except Exception:
            cv2.destroyWindow(self._titulo)
            cv2.waitKey(1)
            raise
        if self._criar_landmarks is not None:
            try:
                self._provider_landmarks = self._criar_landmarks()
            except Exception:
                self._desativar_landmarks()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        provider = self._provider_landmarks
        self._provider_landmarks = None
        if provider is not None:
            try:
                provider.fechar()
            except Exception:
                logger.warning("falha ao fechar provider de landmarks", exc_info=True)
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
        linhas_exibidas = list(linhas)
        if self._landmarks_indisponiveis:
            linhas_exibidas.append(("Pontos faciais indisponiveis", (0, 255, 255)))
        elif self._provider_landmarks is not None:
            timestamp_ms = max(
                self._ultimo_timestamp_ms + 1,
                self._monotonic_ns() // 1_000_000,
            )
            self._ultimo_timestamp_ms = timestamp_ms
            try:
                resultado = self._provider_landmarks.detectar(frame, timestamp_ms)
                if len(resultado.rostos) == 1:
                    desenhar_landmarks(frame_com_overlay, resultado, cv2)
                    linhas_exibidas.append(("Pontos faciais ativos", (255, 255, 0)))
                elif not resultado.rostos:
                    linhas_exibidas.append(
                        ("Posicione o rosto na camera", (0, 255, 255))
                    )
                else:
                    linhas_exibidas.append(
                        ("Mantenha apenas uma pessoa na camera", (0, 255, 255))
                    )
            except Exception:
                self._desativar_landmarks()
                linhas_exibidas.append(("Pontos faciais indisponiveis", (0, 255, 255)))

        for indice, (texto, cor) in enumerate(linhas_exibidas):
            y = 40 + indice * 35
            cv2.putText(frame_com_overlay, texto, (20, y), _FONTE, 0.7, cor, 2)

        cv2.imshow(self._titulo, frame_com_overlay)
        return cv2.waitKey(1) & 0xFF
