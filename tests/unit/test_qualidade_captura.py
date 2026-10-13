"""Politica de qualidade da captura, validada com recortes sinteticos."""

from __future__ import annotations

import numpy as np
import pytest

from src.domain.errors import (
    IluminacaoExcessiva,
    IluminacaoInsuficiente,
    RostoMuitoPequeno,
    RostoSemNitidez,
)
from src.domain.services.qualidade_captura import (
    ParametrosQualidade,
    avaliar_qualidade,
)


def _patch_constante(valor: int, tamanho: int = 8) -> np.ndarray:
    return np.full((tamanho, tamanho, 3), valor, dtype=np.uint8)


def _xadrez(tamanho: int = 8) -> np.ndarray:
    padrao = np.indices((tamanho, tamanho)).sum(axis=0) % 2 * 255
    return np.repeat(padrao[:, :, None], 3, axis=2).astype(np.uint8)


def test_plano_com_luz_intermediaria_e_recusado_por_falta_de_nitidez() -> None:
    with pytest.raises(RostoSemNitidez):
        avaliar_qualidade(_patch_constante(120), 80, 80, ParametrosQualidade())


def test_padrao_xadrez_nitido_e_aceito() -> None:
    medidas = avaliar_qualidade(_xadrez(), 80, 80, ParametrosQualidade())

    assert medidas.largura_face == 80
    assert medidas.altura_face == 80
    assert medidas.luminosidade == pytest.approx(127.5)
    assert medidas.nitidez >= 100.0


def test_tamanho_da_face_e_verificado_antes_da_iluminacao() -> None:
    with pytest.raises(RostoMuitoPequeno):
        avaliar_qualidade(_patch_constante(0), 79, 200, ParametrosQualidade())


@pytest.mark.parametrize("brilho", [40, 215])
def test_limites_fechados_de_brilho_sao_aceitos(brilho: int) -> None:
    parametros = ParametrosQualidade(min_sharpness=0)

    medidas = avaliar_qualidade(_patch_constante(brilho), 80, 80, parametros)

    assert medidas.luminosidade == brilho
    assert medidas.nitidez == 0.0


def test_largura_e_altura_minimas_sao_aceitas() -> None:
    avaliar_qualidade(_xadrez(), 80, 80, ParametrosQualidade())


def test_nitidez_exatamente_no_limite_e_aceita() -> None:
    recorte = np.zeros((4, 4, 3), dtype=np.uint8)
    recorte[1, 1] = 255
    recorte[2, 2] = 255
    # Laplaciano interno independente: [-1020, 510, 510, -1020],
    # cuja variancia populacional e 585225.
    parametros = ParametrosQualidade(
        min_face_px=80,
        min_brightness=0,
        max_brightness=255,
        min_sharpness=585225,
    )

    medidas = avaliar_qualidade(recorte, 80, 80, parametros)

    assert medidas.nitidez == 585225.0


@pytest.mark.parametrize(
    ("recorte", "parametros", "erro"),
    [
        (
            _patch_constante(39),
            ParametrosQualidade(min_sharpness=0),
            IluminacaoInsuficiente,
        ),
        (
            _patch_constante(216),
            ParametrosQualidade(min_sharpness=0),
            IluminacaoExcessiva,
        ),
        (_patch_constante(120), ParametrosQualidade(), RostoSemNitidez),
    ],
)
def test_recusa_segue_ordem_de_tamanho_luz_e_nitidez(
    recorte: np.ndarray,
    parametros: ParametrosQualidade,
    erro: type[Exception],
) -> None:
    with pytest.raises(erro):
        avaliar_qualidade(recorte, 80, 80, parametros)


def test_canais_bgr_usam_luminancia_padronizada() -> None:
    recorte = np.empty((4, 4, 3), dtype=np.uint8)
    recorte[:] = (10, 20, 30)
    parametros = ParametrosQualidade(
        min_face_px=80,
        min_brightness=0,
        max_brightness=255,
        min_sharpness=0,
    )

    medidas = avaliar_qualidade(recorte, 80, 80, parametros)

    assert medidas.luminosidade == pytest.approx(21.85)


def test_avaliacao_nao_modifica_o_recorte() -> None:
    recorte = _xadrez()
    original = recorte.copy()

    avaliar_qualidade(recorte, 80, 80, ParametrosQualidade())

    np.testing.assert_array_equal(recorte, original)


@pytest.mark.parametrize(
    "recorte",
    [
        np.empty((0, 4, 3), dtype=np.uint8),
        np.zeros((2, 4, 3), dtype=np.uint8),
        np.zeros((4, 2, 3), dtype=np.uint8),
        np.zeros((4, 4), dtype=np.uint8),
        np.zeros((4, 4, 1), dtype=np.uint8),
        np.zeros((4, 4, 4), dtype=np.uint8),
        np.zeros((4, 4, 3), dtype=np.float32),
    ],
)
def test_recortes_invalidos_sao_rejeitados(recorte: np.ndarray) -> None:
    with pytest.raises(ValueError):
        avaliar_qualidade(recorte, 80, 80, ParametrosQualidade())


@pytest.mark.parametrize(
    ("largura", "altura"),
    [(0, 80), (-1, 80), (80, 0), (80, -1), (True, 80), (80, False), (80.5, 80)],
)
def test_dimensoes_faciais_invalidas_sao_rejeitadas(
    largura: int | float | bool, altura: int | bool
) -> None:
    with pytest.raises(ValueError):
        avaliar_qualidade(_xadrez(), largura, altura, ParametrosQualidade())  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_face_px": 2},
        {"min_face_px": True},
        {"min_face_px": 80.5},
        {"min_brightness": -0.1},
        {"min_brightness": 256},
        {"min_brightness": float("nan")},
        {"min_brightness": float("inf")},
        {"max_brightness": -1},
        {"max_brightness": 256},
        {"max_brightness": float("nan")},
        {"max_brightness": float("inf")},
        {"min_sharpness": -0.1},
        {"min_sharpness": float("nan")},
        {"min_sharpness": float("inf")},
        {"min_brightness": 215, "max_brightness": 215},
        {"min_brightness": 216, "max_brightness": 215},
    ],
)
def test_parametros_invalidos_falham_na_construcao(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ParametrosQualidade(**kwargs)  # type: ignore[arg-type]
