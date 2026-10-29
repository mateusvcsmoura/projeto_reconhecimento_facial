"""Interpreta a orientação de cabeça no backend a partir de Face Landmarker.

O escore geométrico é uma heurística técnica, não uma estimativa biométrica ou
prova isolada de vida. O challenge exige também identidade, qualidade e
anti-spoofing calculados pelo worker.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Protocol

from src.domain.services.desafio_captura import OrientacaoPose
from src.domain.services.facial_landmarks import ResultadoLandmarks


class DetectorLandmarks(Protocol):
    def detectar(self, frame: Any, timestamp_ms: int) -> ResultadoLandmarks: ...

    def fechar(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ResultadoPose:
    quantidade_rostos: int
    orientacao: OrientacaoPose


class DesafioMovimentoAdapter:
    """Converte landmarks normalizados em frente/esquerda/direita/indefinida."""

    # Limites iniciais de engenharia; devem ser medidos com ensaios autorizados.
    # O guia do navegador (static/landmarks.mjs) replica esta geometria com
    # folga: ao mudar um, ajuste o outro.
    FRENTE_MAXIMO = 0.08
    VIRADA_MINIMA = 0.12
    VIRADA_MAXIMA = 0.50
    INDICE_OLHO_ESQUERDO = 33
    INDICE_OLHO_DIREITO = 263
    INDICE_NARIZ = 1

    def __init__(self, detector: DetectorLandmarks) -> None:
        self._detector = detector
        self._ultimo_timestamp = 0
        self._fechado = False

    def analisar(self, frame: Any) -> ResultadoPose:
        if self._fechado:
            raise RuntimeError("O detector de pose está fechado.")
        timestamp = max(time.monotonic_ns() // 1_000_000, self._ultimo_timestamp + 1)
        self._ultimo_timestamp = timestamp
        resultado = self._detector.detectar(frame, timestamp)
        rostos = resultado.rostos
        if len(rostos) == 0:
            return ResultadoPose(0, OrientacaoPose.AUSENTE)
        if len(rostos) != 1:
            return ResultadoPose(len(rostos), OrientacaoPose.MULTIPLOS)
        pontos = rostos[0]
        maior_indice = max(
            self.INDICE_OLHO_ESQUERDO,
            self.INDICE_OLHO_DIREITO,
            self.INDICE_NARIZ,
        )
        if len(pontos) <= maior_indice:
            return ResultadoPose(1, OrientacaoPose.INDETERMINADA)
        olho_esquerdo = pontos[self.INDICE_OLHO_ESQUERDO]
        olho_direito = pontos[self.INDICE_OLHO_DIREITO]
        nariz = pontos[self.INDICE_NARIZ]
        coordenadas = (
            olho_esquerdo.x,
            olho_direito.x,
            nariz.x,
            olho_esquerdo.y,
            olho_direito.y,
            nariz.y,
        )
        if not all(math.isfinite(float(valor)) for valor in coordenadas):
            return ResultadoPose(1, OrientacaoPose.INDETERMINADA)
        distancia_olhos = abs(olho_direito.x - olho_esquerdo.x)
        if distancia_olhos < 0.05:
            return ResultadoPose(1, OrientacaoPose.INDETERMINADA)
        centro_olhos = (olho_esquerdo.x + olho_direito.x) / 2
        deslocamento = (nariz.x - centro_olhos) / distancia_olhos
        magnitude = abs(deslocamento)
        if magnitude <= self.FRENTE_MAXIMO:
            orientacao = OrientacaoPose.FRENTE
        elif self.VIRADA_MINIMA <= magnitude <= self.VIRADA_MAXIMA:
            # O frame chega cru (sem espelhamento): a esquerda da pessoa fica à
            # direita da imagem. A orientação segue a perspectiva da pessoa, a
            # mesma das instruções exibidas na prévia espelhada.
            orientacao = (
                OrientacaoPose.ESQUERDA if deslocamento > 0 else OrientacaoPose.DIREITA
            )
        else:
            orientacao = OrientacaoPose.INDETERMINADA
        return ResultadoPose(1, orientacao)

    def fechar(self) -> None:
        if self._fechado:
            return
        self._fechado = True
        self._detector.fechar()
