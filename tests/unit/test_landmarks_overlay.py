"""Geometria do overlay sem OpenCV, câmera ou modelo real."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from src.domain.services.facial_landmarks import PontoFacial, ResultadoLandmarks
from src.presentation.cli.landmarks_overlay import desenhar_landmarks


class Cv2DesenhoFalso:
    LINE_8 = 8

    def __init__(self) -> None:
        self.linhas: list[
            tuple[tuple[int, int], tuple[int, int], tuple[int, int, int]]
        ] = []
        self.pontos: list[tuple[tuple[int, int], int, tuple[int, int, int]]] = []

    def line(
        self,
        _frame: Any,
        inicio: tuple[int, int],
        fim: tuple[int, int],
        cor: tuple[int, int, int],
        _espessura: int,
        _tipo_linha: int,
    ) -> None:
        self.linhas.append((inicio, fim, cor))

    def circle(
        self,
        _frame: Any,
        centro: tuple[int, int],
        raio: int,
        cor: tuple[int, int, int],
        _espessura: int,
        _tipo_linha: int,
    ) -> None:
        self.pontos.append((centro, raio, cor))


def test_mapeia_coordenadas_normalizadas_para_dimensoes_reais_do_frame() -> None:
    cv2 = Cv2DesenhoFalso()
    frame = np.zeros((181, 321, 3), dtype=np.uint8)
    resultado = ResultadoLandmarks(
        rostos=(
            (
                PontoFacial(0.0, 0.0, 0.0),
                PontoFacial(1.0, 1.0, 0.0),
                PontoFacial(0.5, 0.5, 0.0),
            ),
        ),
        conexoes=((0, 1), (1, 2)),
    )

    desenhar_landmarks(frame, resultado, cv2)

    assert [ponto[0] for ponto in cv2.pontos] == [(0, 0), (320, 180), (160, 90)]
    assert [linha[:2] for linha in cv2.linhas] == [
        ((0, 0), (320, 180)),
        ((320, 180), (160, 90)),
    ]
    assert all(ponto[1] == 1 for ponto in cv2.pontos)
    assert all(linha[2] == (255, 255, 0) for linha in cv2.linhas)


def test_pula_coordenadas_invalidas_e_conexoes_sem_pontas_validas() -> None:
    cv2 = Cv2DesenhoFalso()
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    resultado = ResultadoLandmarks(
        rostos=(
            (
                PontoFacial(0.0, 0.0, 0.0),
                PontoFacial(1.0, 1.0, 0.0),
                PontoFacial(float("nan"), 0.5, 0.0),
                PontoFacial(0.5, 0.5, 0.0),
                PontoFacial(-0.1, 0.0, 0.0),
                PontoFacial(0.2, 1.1, 0.0),
                PontoFacial(float("inf"), 0.0, 0.0),
            ),
        ),
        conexoes=((0, 1), (0, 2), (1, 99), (3, 3), (4, 5), (6, 0)),
    )

    desenhar_landmarks(frame, resultado, cv2)

    assert [ponto[0] for ponto in cv2.pontos] == [(0, 0), (199, 99), (100, 50)]
    assert [linha[:2] for linha in cv2.linhas] == [
        ((0, 0), (199, 99)),
        ((100, 50), (100, 50)),
    ]


@pytest.mark.parametrize("quantidade", [0, 2])
def test_nao_desenha_malha_sem_exatamente_um_rosto(quantidade: int) -> None:
    cv2 = Cv2DesenhoFalso()
    frame = np.zeros((20, 40, 3), dtype=np.uint8)
    face = (PontoFacial(0.5, 0.5, 0.0),)
    resultado = ResultadoLandmarks(
        rostos=tuple(face for _ in range(quantidade)), conexoes=((0, 0),)
    )

    desenhar_landmarks(frame, resultado, cv2)

    assert cv2.pontos == []
    assert cv2.linhas == []
