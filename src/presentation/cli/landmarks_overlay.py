"""Desenho efêmero dos pontos faciais sobre uma cópia do frame."""

from __future__ import annotations

import math
from typing import Any

from src.domain.services.facial_landmarks import ResultadoLandmarks

COR_CIANO_BGR = (255, 255, 0)


def desenhar_landmarks(
    frame: Any,
    resultado: ResultadoLandmarks,
    cv2: Any,
) -> None:
    """Desenha conexões e pontos quando exatamente um rosto foi localizado.

    Coordenadas inválidas e conexões com índices fora da face são ignoradas,
    sem impedir que o restante do overlay seja exibido.
    """
    if len(resultado.rostos) != 1:
        return
    altura, largura = frame.shape[:2]
    if altura <= 0 or largura <= 0:
        return

    pontos = resultado.rostos[0]
    coordenadas: list[tuple[int, int] | None] = []
    for ponto in pontos:
        x, y = float(ponto.x), float(ponto.y)
        if not (math.isfinite(x) and math.isfinite(y)) or not (
            0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        ):
            coordenadas.append(None)
            continue
        coordenadas.append((round(x * (largura - 1)), round(y * (altura - 1))))

    for inicio, fim in resultado.conexoes:
        if not (0 <= inicio < len(coordenadas) and 0 <= fim < len(coordenadas)):
            continue
        ponto_inicio = coordenadas[inicio]
        ponto_fim = coordenadas[fim]
        if ponto_inicio is None or ponto_fim is None:
            continue
        cv2.line(
            frame,
            ponto_inicio,
            ponto_fim,
            COR_CIANO_BGR,
            1,
            cv2.LINE_8,
        )

    for coordenada in coordenadas:
        if coordenada is None:
            continue
        cv2.circle(
            frame,
            coordenada,
            1,
            COR_CIANO_BGR,
            -1,
            cv2.LINE_8,
        )
