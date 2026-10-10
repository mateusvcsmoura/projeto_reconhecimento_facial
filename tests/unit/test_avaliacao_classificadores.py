"""Métricas e incerteza em pares artificiais, sem dados de rostos."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.avaliacao_classificadores import (
    avaliar_escores,
    avaliar_no_teste,
    salvar_resultado,
)
from scripts.calibrar_limiar import Pares, bootstrap_por_identidade, intervalo_95
from scripts.classificadores_binarios import ModeloSelecionado
from scripts.experimento_classificacao_binaria import ParesEtapa1


def _pares_teste() -> ParesEtapa1:
    identidade_a = np.array([10] * 4 + [20] * 4 + [10] * 4, dtype=np.int32)
    identidade_b = np.array([10] * 4 + [21] * 4 + [30] * 4, dtype=np.int32)
    return ParesEtapa1(
        conjunto="teste",
        imagem_a=np.arange(0, 24, 2),
        imagem_b=np.arange(1, 24, 2),
        identidade_a=identidade_a,
        identidade_b=identidade_b,
        distancia=np.array(
            [0.1, 0.2, 0.25, 0.35, 0.6, 0.7, 0.8, 0.9, 0.6, 0.7, 0.8, 0.9]
        ),
        rotulo=(identidade_a == identidade_b).astype(np.int8),
    )


def test_metricas_confusao_e_auc_respeitam_orientacao_do_score() -> None:
    rotulos = np.array([1, 1, 0, 0], dtype=np.int8)
    escores = np.array([0.9, 0.4, 0.3, 0.2])

    metricas = avaliar_escores(rotulos, escores, limiar_score=0.5)

    assert (metricas["tp"], metricas["fn"], metricas["fp"], metricas["tn"]) == (
        1,
        1,
        0,
        2,
    )
    assert metricas["far"] == pytest.approx(0.0)
    assert metricas["frr"] == pytest.approx(0.5)
    assert metricas["acuracia"] == pytest.approx(0.75)
    assert metricas["precisao"] == pytest.approx(1.0)
    assert metricas["recall"] == pytest.approx(0.5)
    assert metricas["f1"] == pytest.approx(2 / 3)
    assert metricas["auc"] == pytest.approx(1.0)


def test_auc_logistica_univariada_espelha_distancia() -> None:
    from scripts.classificadores_binarios import (
        caracteristicas_da_distancia,
        treinar_e_selecionar_modelos,
    )

    distancia_treino = np.array([0.1, 0.15, 0.2, 0.25, 0.65, 0.7, 0.75, 0.8])
    rotulos_treino = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.int8)
    distancia_validacao = np.array([0.1, 0.3, 0.4, 0.8, 0.2, 0.5, 0.6, 0.9])
    rotulos_validacao = np.array([1, 1, 0, 0, 1, 0, 0, 0], dtype=np.int8)
    modelos = treinar_e_selecionar_modelos(
        caracteristicas_da_distancia(distancia_treino),
        rotulos_treino,
        caracteristicas_da_distancia(distancia_validacao),
        rotulos_validacao,
        far_maximo=0.5,
    )
    scores = modelos["M2"].estimador.predict_proba(
        caracteristicas_da_distancia(distancia_validacao)
    )[:, 1]

    auc_modelo = avaliar_escores(rotulos_validacao, scores, 0.5)["auc"]
    auc_distancia = avaliar_escores(
        rotulos_validacao, -distancia_validacao, -0.5
    )["auc"]
    assert auc_modelo == pytest.approx(auc_distancia)


def test_metricas_sem_denominador_sao_nulas() -> None:
    metricas = avaliar_escores(
        np.array([1, 1]), np.array([0.8, 0.9]), limiar_score=0.5
    )

    assert metricas["far"] is None
    assert metricas["frr"] == pytest.approx(0.0)
    assert metricas["auc"] is None
    assert metricas["eer"] is None


def test_brier_existe_so_com_probabilidades() -> None:
    rotulos = np.array([1, 0], dtype=np.int8)
    escores = np.array([0.9, -0.2])

    assert avaliar_escores(rotulos, escores, 0.0)["brier"] is None
    metricas = avaliar_escores(
        rotulos, escores, 0.0, probabilidades=np.array([0.8, 0.25])
    )
    assert metricas["brier"] == pytest.approx(((0.8 - 1) ** 2 + 0.25**2) / 2)


def test_bootstrap_por_identidade_e_reprodutivel() -> None:
    primeiro = avaliar_no_teste(_pares_teste(), {}, seed=17, replicas=50)
    segundo = avaliar_no_teste(_pares_teste(), {}, seed=17, replicas=50)

    assert primeiro.metodos["M0"].ic_far == segundo.metodos["M0"].ic_far
    assert primeiro.metodos["M0"].ic_frr == segundo.metodos["M0"].ic_frr
    assert primeiro.replicas_bootstrap == 50


def test_bootstrap_do_classificador_usa_seus_escores_e_limiar() -> None:
    class EstimadorFalso:
        classes_ = np.array([0, 1])

        def predict_proba(self, X: np.ndarray) -> np.ndarray:
            probabilidade = 0.2 + 0.6 * X[:, 0]
            return np.column_stack((1.0 - probabilidade, probabilidade))

    pares = _pares_teste()
    estimador = EstimadorFalso()
    modelo = ModeloSelecionado(
        nome="M2",
        estimador=estimador,
        parametros={},
        limiar_score=0.5,
        far_treino=0.0,
        frr_treino=0.0,
        far_validacao=0.0,
        frr_validacao=0.0,
        tempo_treino_s=0.0,
    )

    resultado = avaliar_no_teste(pares, {"M2": modelo}, seed=19, replicas=100)

    probabilidades = estimador.predict_proba(pares.distancia.reshape(-1, 1))[:, 1]
    pares_bootstrap = Pares(
        conjunto="teste",
        imagem_a=pares.imagem_a,
        imagem_b=pares.imagem_b,
        identidade_a=pares.identidade_a,
        identidade_b=pares.identidade_b,
        distancia=-probabilidades,
        rotulo=pares.rotulo,
        impostores_possiveis=int(np.count_nonzero(pares.rotulo == 0)),
    )
    far, frr = bootstrap_por_identidade(
        pares_bootstrap, {"M2": -modelo.limiar_score}, 100, 19
    )["M2"]

    assert resultado.metodos["M2"].ic_far == intervalo_95(far)
    assert resultado.metodos["M2"].ic_frr == intervalo_95(frr)


def test_zero_fp_aplica_regra_dos_tres_por_par_de_identidades() -> None:
    resultado = avaliar_no_teste(_pares_teste(), {}, seed=42, replicas=50)
    m0 = resultado.metodos["M0"]

    assert m0.metricas["fp"] == 0
    assert m0.pares_de_identidades_impostoras == 2
    assert m0.metricas["far_maximo_regra_do_tres"] == pytest.approx(1.5)


def test_far_nao_e_demonstrado_quando_limite_superior_cruza_teto() -> None:
    n_cluster_pequeno = 100
    n_cluster_grande = 1900
    identidade_a = np.array(
        [10] * 4 + [20] * n_cluster_pequeno + [30] * n_cluster_grande,
        dtype=np.int32,
    )
    identidade_b = np.array(
        [10] * 4 + [21] * n_cluster_pequeno + [31] * n_cluster_grande,
        dtype=np.int32,
    )
    distancias = np.array(
        [0.1, 0.2, 0.25, 0.35]
        + [0.1]
        + [0.8] * (n_cluster_pequeno - 1)
        + [0.8] * n_cluster_grande,
        dtype=np.float64,
    )
    pares = ParesEtapa1(
        conjunto="teste",
        imagem_a=np.arange(distancias.size, dtype=np.int32) * 2,
        imagem_b=np.arange(distancias.size, dtype=np.int32) * 2 + 1,
        identidade_a=identidade_a,
        identidade_b=identidade_b,
        distancia=distancias,
        rotulo=(identidade_a == identidade_b).astype(np.int8),
    )
    resultado = avaliar_no_teste(pares, {}, seed=42, replicas=1000)
    m0 = resultado.metodos["M0"]

    assert m0.metricas["far"] == pytest.approx(1 / 2000)
    assert m0.ic_far.superior > 0.001
    assert m0.atende_teto_far is False


def test_metricas_probabilisticas_incluem_calibracao_e_diagnostico_gnb() -> None:
    rotulos = np.array([1, 0, 1, 0], dtype=np.int8)
    scores = np.array([0.9, 0.2, 0.7, 0.4])
    resultado = avaliar_escores(rotulos, scores, 0.5, probabilidades=scores)

    assert resultado["brier"] is not None
    assert resultado["quantis_probabilidade"] is not None
    assert resultado["calibracao"] is not None


def test_salvar_resultado_nao_persiste_identificadores_de_pares(
    tmp_path: Path,
) -> None:
    resultado = avaliar_no_teste(_pares_teste(), {}, seed=42, replicas=20)
    arquivo = salvar_resultado(resultado, tmp_path / "resultado.json")
    dados = json.loads(arquivo.read_text(encoding="utf-8"))
    serializado = arquivo.read_text(encoding="utf-8")

    assert "imagem_a" not in serializado
    assert "identidade_a" not in serializado
    assert dados["conjunto"] == "teste"
    assert "M0" in dados["metodos"]
