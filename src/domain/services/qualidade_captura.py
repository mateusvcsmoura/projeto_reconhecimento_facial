"""Avaliacao deterministica de dimensao, iluminacao e nitidez da captura."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real

import numpy as np

from src.domain.errors import (
    IluminacaoExcessiva,
    IluminacaoInsuficiente,
    RostoMuitoPequeno,
    RostoSemNitidez,
)


@dataclass(frozen=True, slots=True)
class ParametrosQualidade:
    """Heuristicas optativas; os valores nao foram calibrados com rostos."""

    min_face_px: int = 80
    min_brightness: float = 40.0
    max_brightness: float = 215.0
    min_sharpness: float = 100.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.min_face_px, bool)
            or not isinstance(self.min_face_px, Integral)
            or self.min_face_px < 3
        ):
            raise ValueError("min_face_px deve ser inteiro e maior ou igual a 3.")

        for nome, valor in (
            ("min_brightness", self.min_brightness),
            ("max_brightness", self.max_brightness),
        ):
            if (
                isinstance(valor, bool)
                or not isinstance(valor, Real)
                or not isfinite(float(valor))
                or not 0.0 <= valor <= 255.0
            ):
                raise ValueError(f"{nome} deve ser finito e estar entre 0 e 255.")

        if self.max_brightness <= self.min_brightness:
            raise ValueError("max_brightness deve ser maior que min_brightness.")

        if (
            isinstance(self.min_sharpness, bool)
            or not isinstance(self.min_sharpness, Real)
            or not isfinite(float(self.min_sharpness))
            or self.min_sharpness < 0.0
        ):
            raise ValueError("min_sharpness deve ser finito e nao negativo.")


@dataclass(frozen=True, slots=True)
class MedidasQualidade:
    largura_face: int
    altura_face: int
    luminosidade: float
    nitidez: float


def avaliar_qualidade(
    recorte_bgr: np.ndarray,
    largura_face: int,
    altura_face: int,
    parametros: ParametrosQualidade,
) -> MedidasQualidade:
    """Devolve as medidas ou levanta a recusa de qualidade correspondente.

    ``recorte_bgr`` deve ser uma imagem BGR ``uint8`` sem redimensionamento.
    As dimensoes da face devem vir da area original devolvida pelo detector.
    A funcao nao altera o array recebido.
    """
    if not isinstance(recorte_bgr, np.ndarray):
        raise ValueError("recorte_bgr deve ser um array NumPy.")
    if (
        recorte_bgr.dtype != np.uint8
        or recorte_bgr.ndim != 3
        or recorte_bgr.shape[2] != 3
        or recorte_bgr.shape[0] < 3
        or recorte_bgr.shape[1] < 3
    ):
        raise ValueError("recorte_bgr deve ser BGR uint8 com pelo menos 3x3 pixels.")
    if (
        isinstance(largura_face, bool)
        or isinstance(altura_face, bool)
        or not isinstance(largura_face, Integral)
        or not isinstance(altura_face, Integral)
        or largura_face <= 0
        or altura_face <= 0
    ):
        raise ValueError("largura_face e altura_face devem ser inteiros positivos.")
    if not isinstance(parametros, ParametrosQualidade):
        raise ValueError("parametros deve ser ParametrosQualidade.")

    largura = int(largura_face)
    altura = int(altura_face)
    if min(largura, altura) < parametros.min_face_px:
        raise RostoMuitoPequeno()

    bgr = recorte_bgr.astype(np.float64, copy=False)
    cinza = 0.114 * bgr[:, :, 0] + 0.587 * bgr[:, :, 1] + 0.299 * bgr[:, :, 2]
    luminosidade = float(np.mean(cinza))
    if luminosidade < parametros.min_brightness:
        raise IluminacaoInsuficiente()
    if luminosidade > parametros.max_brightness:
        raise IluminacaoExcessiva()

    laplaciano = (
        cinza[:-2, 1:-1]
        + cinza[2:, 1:-1]
        + cinza[1:-1, :-2]
        + cinza[1:-1, 2:]
        - 4.0 * cinza[1:-1, 1:-1]
    )
    nitidez = float(np.var(laplaciano, ddof=0))
    if nitidez < parametros.min_sharpness:
        raise RostoSemNitidez()

    return MedidasQualidade(
        largura_face=largura,
        altura_face=altura,
        luminosidade=luminosidade,
        nitidez=nitidez,
    )
