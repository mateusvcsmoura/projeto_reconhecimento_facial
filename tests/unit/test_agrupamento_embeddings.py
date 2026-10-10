from __future__ import annotations

import inspect

import numpy as np
import pytest

from scripts.agrupamento_embeddings import (
    calcular_metricas_externas,
    contar_embeddings_duplicados,
    diagnosticar_agrupamento,
    executar_dbscan,
    executar_kmeans,
    normalizar_embeddings,
    selecionar_dbscan,
    selecionar_kmeans,
    selecionar_por_grade,
    valores_k_vizinhos,
)


def _dados_em_dois_grupos() -> np.ndarray:
    return normalizar_embeddings(
        np.array(
            [
                [1.0, 0.01, 0.0],
                [1.0, -0.01, 0.0],
                [0.99, 0.02, 0.0],
                [0.01, 1.0, 0.0],
                [-0.01, 1.0, 0.0],
                [0.02, 0.99, 0.0],
            ]
        )
    )


def test_normalizacao_l2_valida_forma_valores_e_norma() -> None:
    resultado = normalizar_embeddings(np.array([[3.0, 4.0], [0.0, 2.0]]))

    np.testing.assert_allclose(np.linalg.norm(resultado, axis=1), 1.0)
    np.testing.assert_allclose(resultado[0], [0.6, 0.8])


@pytest.mark.parametrize(
    "entrada",
    [
        np.empty((0, 3)),
        np.array([1.0, 2.0]),
        np.array([[0.0, 0.0]]),
        np.array([[1.0, np.nan]]),
        np.array([[1.0, np.inf]]),
        np.ones((3, 1)),
    ],
)
def test_normalizacao_rejeita_matrizes_invalidas(entrada: np.ndarray) -> None:
    with pytest.raises(ValueError):
        normalizar_embeddings(entrada)


def test_dbscan_coseno_encontra_dois_grupos_e_ruido() -> None:
    dados = np.vstack([_dados_em_dois_grupos(), [[0.0, 0.0, 1.0]]])

    resultado = executar_dbscan(dados, eps=0.03, min_samples=2)

    assert resultado.diagnosticos.quantidade_clusters == 2
    assert resultado.diagnosticos.quantidade_ruido == 1
    assert resultado.diagnosticos.cobertura == pytest.approx(6 / 7)
    assert resultado.rotulos[-1] == -1


def test_dbscan_registra_sem_cluster_cluster_unico_e_fragmentacao() -> None:
    dados = _dados_em_dois_grupos()
    nenhum = executar_dbscan(dados, eps=0.001, min_samples=4)
    unico = executar_dbscan(dados, eps=2.0, min_samples=2)

    assert nenhum.diagnosticos.quantidade_clusters == 0
    assert nenhum.diagnosticos.silhouette_cosseno is None
    assert nenhum.diagnosticos.status == "sem_clusters"
    assert unico.diagnosticos.quantidade_clusters == 1
    assert unico.diagnosticos.status == "cluster_unico"


def test_kmeans_e_reprodutivel_e_usa_grade_sem_rotulos() -> None:
    dados = _dados_em_dois_grupos()
    primeiro = executar_kmeans(dados, n_clusters=2, seed=17)
    segundo = executar_kmeans(dados, n_clusters=2, seed=17)

    np.testing.assert_array_equal(primeiro.rotulos, segundo.rotulos)
    assert primeiro.diagnosticos.quantidade_clusters == 2
    assert primeiro.diagnosticos.quantidade_ruido == 0
    assert "y_true" not in inspect.signature(selecionar_por_grade).parameters


def test_seletores_usam_somente_metricas_internas() -> None:
    dados = _dados_em_dois_grupos()

    dbscan = selecionar_dbscan(
        dados, eps_candidatos=(0.03, 0.2), min_samples_candidatos=(2,)
    )
    kmeans = selecionar_kmeans(dados, k_candidatos=(2, 3), seed=11)

    assert dbscan.configuracao_selecionada == {"eps": 0.03, "min_samples": 2}
    assert dbscan.criterio == "silhouette_cosseno_com_cobertura_minima"
    assert kmeans.configuracao_selecionada is not None
    assert kmeans.configuracao_selecionada["n_clusters"] == 2
    assert "y_true" not in inspect.signature(selecionar_dbscan).parameters
    assert "y_true" not in inspect.signature(selecionar_kmeans).parameters


def test_seletor_dbscan_marca_indisponivel_se_nao_houver_candidato_valido() -> None:
    resultado = selecionar_dbscan(
        _dados_em_dois_grupos(),
        eps_candidatos=(0.001,),
        min_samples_candidatos=(5,),
    )

    assert resultado.configuracao_selecionada is None
    assert resultado.motivo_indisponibilidade is not None


def test_metricas_externas_reportam_cobertura_e_tratamento_de_ruido() -> None:
    rotulos_reais = np.array([0, 0, 1, 1, 2])
    clusters = np.array([5, 5, 7, 7, -1])

    metricas = calcular_metricas_externas(rotulos_reais, clusters)

    assert metricas["cobertura"] == pytest.approx(0.8)
    assert metricas["ari_sem_ruido"] == pytest.approx(1.0)
    assert metricas["ari_com_ruido_como_cluster"] is not None
    assert metricas["nmi_sem_ruido"] == pytest.approx(1.0)


def test_metricas_externas_sem_pontos_cobertos_sao_indisponiveis() -> None:
    metricas = calcular_metricas_externas(np.array([0, 1]), np.array([-1, -1]))

    assert metricas["cobertura"] == 0.0
    assert metricas["ari_sem_ruido"] is None
    assert metricas["nmi_sem_ruido"] is None


def test_metricas_internas_sao_omitidas_para_um_cluster_ou_um_ponto() -> None:
    dados = _dados_em_dois_grupos()
    um_cluster = diagnosticar_agrupamento(dados, np.zeros(6, dtype=int))
    ponto_isolado = diagnosticar_agrupamento(dados, np.array([0, -1, -1, 1, -1, -1]))

    assert um_cluster.silhouette_cosseno is None
    assert um_cluster.davies_bouldin_euclidiano is None
    assert ponto_isolado.silhouette_cosseno is None


def test_valores_k_vizinhos_nao_materializam_matriz_quadratica() -> None:
    valores = valores_k_vizinhos(_dados_em_dois_grupos(), k=2)

    assert valores.shape == (6,)
    assert np.isfinite(valores).all()
    assert np.all(np.diff(valores) >= 0)


def test_conta_duplicatas_exatas_e_vizinhos_proximos_sem_pares_quadraticos() -> None:
    dados = normalizar_embeddings(
        np.array(
            [
                [1.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.99999999, 0.0001, 0.0],
                [0.0, 1.0, 0.0],
            ]
        )
    )

    resumo = contar_embeddings_duplicados(dados, distancia_cosseno_maxima=1e-5)

    assert resumo["linhas_duplicadas_exatas_excedentes"] == 1
    assert resumo["amostras_com_vizinho_proximo"] >= 2
