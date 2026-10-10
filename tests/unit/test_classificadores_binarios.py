"""Testes sintéticos dos classificadores experimentais 1:1."""

from __future__ import annotations

import numpy as np
import pytest

from scripts.classificadores_binarios import (
    caracteristicas_da_distancia,
    selecionar_limiar_por_far,
    treinar_e_selecionar_modelos,
)


def test_caracteristicas_da_distancia_gera_coluna_float64() -> None:
    resultado = caracteristicas_da_distancia(np.array([0.1, 0.4, 0.7]))

    assert resultado.shape == (3, 1)
    assert resultado.dtype == np.float64
    np.testing.assert_allclose(resultado[:, 0], [0.1, 0.4, 0.7])


@pytest.mark.parametrize(
    "distancias",
    [
        np.array([[0.1, 0.2]]),
        np.array([0.1, np.nan]),
        np.array([0.1, np.inf]),
        np.array([], dtype=np.float64),
    ],
)
def test_caracteristicas_rejeitam_valores_nao_finitos_ou_shape(
    distancias: np.ndarray,
) -> None:
    with pytest.raises(ValueError):
        caracteristicas_da_distancia(distancias)


def test_limiar_score_respeita_far_maximo_e_empates() -> None:
    rotulos = np.array([1, 1, 1, 0, 0, 0, 0], dtype=np.int8)
    escores = np.array([0.8, 0.7, 0.6, 0.9, 0.5, 0.5, 0.1])

    primeira = selecionar_limiar_por_far(rotulos, escores, far_maximo=0.25)
    segunda = selecionar_limiar_por_far(rotulos, escores, far_maximo=0.25)

    assert primeira == segunda
    assert primeira is not None
    limiar, far, frr = primeira
    assert limiar == pytest.approx(0.6)
    assert far == pytest.approx(0.25)
    assert frr == pytest.approx(0.0)


def test_limiar_prioriza_far_menor_quando_frr_empata() -> None:
    rotulos = np.array([1, 0, 0], dtype=np.int8)
    escores = np.array([0.9, 0.8, 0.1])

    resultado = selecionar_limiar_por_far(rotulos, escores, far_maximo=0.5)

    assert resultado == pytest.approx((0.9, 0.0, 0.0))


def test_limiar_varre_grande_vetor_de_scores_unicos() -> None:
    scores = np.linspace(0.0, 1.0, 100_000, endpoint=False)
    rotulos = (scores >= 0.9).astype(np.int8)

    resultado = selecionar_limiar_por_far(rotulos, scores, far_maximo=0.0)

    assert resultado is not None
    limiar, far, frr = resultado
    assert limiar == pytest.approx(0.9)
    assert far == pytest.approx(0.0)
    assert frr == pytest.approx(0.0)


def test_treina_m2_m3_m4_com_grade_definida() -> None:
    rng = np.random.default_rng(42)
    distancias_treino = np.concatenate(
        [rng.uniform(0.05, 0.25, 80), rng.uniform(0.65, 0.95, 80)]
    )
    rotulos_treino = np.concatenate(
        [np.ones(80, dtype=np.int8), np.zeros(80, dtype=np.int8)]
    )
    distancias_validacao = np.concatenate(
        [rng.uniform(0.05, 0.25, 24), rng.uniform(0.65, 0.95, 24)]
    )
    rotulos_validacao = np.concatenate(
        [np.ones(24, dtype=np.int8), np.zeros(24, dtype=np.int8)]
    )

    modelos = treinar_e_selecionar_modelos(
        caracteristicas_da_distancia(distancias_treino),
        rotulos_treino,
        caracteristicas_da_distancia(distancias_validacao),
        rotulos_validacao,
        far_maximo=0.001,
        seed=42,
    )

    assert set(modelos) == {"M2", "M3", "M4"}
    assert modelos["M2"].parametros["C"] in {0.1, 1.0, 10.0}
    assert modelos["M2"].parametros["class_weight"] in {None, "balanced"}
    assert modelos["M3"].parametros == {"var_smoothing": 1e-9}
    assert modelos["M4"].parametros["criterion"] == "gini"
    assert modelos["M4"].parametros["max_depth"] in {1, 2, 3}
    for modelo in modelos.values():
        assert modelo.limiar_score is not None
        assert modelo.far_validacao is not None
        assert modelo.far_validacao <= 0.001
        assert modelo.tempo_treino_s >= 0.0
        assert modelo.estimador.n_features_in_ == 1


def test_classes_ausentes_e_sem_limiar_sao_recusadas() -> None:
    X = np.array([[0.1], [0.2], [0.3], [0.8]])
    y_uma_classe = np.array([1, 1, 1, 1])

    with pytest.raises(ValueError, match="duas classes"):
        treinar_e_selecionar_modelos(X, y_uma_classe, X, y_uma_classe)

    y_treino = np.array([1, 1, 0, 0])
    X_validacao = np.array([[0.8], [0.9], [0.1], [0.2]])
    y_validacao = np.array([1, 1, 0, 0])
    assert (
        treinar_e_selecionar_modelos(
            X, y_treino, X_validacao, y_validacao, far_maximo=0.0
        )
        == {}
    )


def test_selecao_e_preditiva_reprodutivel_com_seed_fixa() -> None:
    distancias_treino = np.array(
        [0.1, 0.15, 0.2, 0.25, 0.65, 0.7, 0.75, 0.8]
    )
    rotulos_treino = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.int8)
    distancias_validacao = np.array(
        [0.12, 0.17, 0.22, 0.27, 0.62, 0.68, 0.73, 0.79]
    )
    rotulos_validacao = rotulos_treino.copy()
    X_treino = caracteristicas_da_distancia(distancias_treino)
    X_validacao = caracteristicas_da_distancia(distancias_validacao)

    primeiro = treinar_e_selecionar_modelos(
        X_treino,
        rotulos_treino,
        X_validacao,
        rotulos_validacao,
        seed=123,
    )
    segundo = treinar_e_selecionar_modelos(
        X_treino,
        rotulos_treino,
        X_validacao,
        rotulos_validacao,
        seed=123,
    )

    assert set(primeiro) == set(segundo)
    for nome in primeiro:
        assert primeiro[nome].parametros == segundo[nome].parametros
        assert primeiro[nome].limiar_score == segundo[nome].limiar_score
        np.testing.assert_allclose(
            primeiro[nome].estimador.predict_proba(X_validacao),
            segundo[nome].estimador.predict_proba(X_validacao),
        )


def test_limiar_recusa_classes_ausentes_ou_entrada_invalida() -> None:
    with pytest.raises(ValueError, match="duas classes"):
        selecionar_limiar_por_far(np.array([1, 1]), np.array([0.8, 0.9]))
    with pytest.raises(ValueError):
        selecionar_limiar_por_far(
            np.array([1, 0]), np.array([0.8, np.nan]), far_maximo=0.001
        )
