"""Operacoes experimentais de clustering sobre embeddings faciais.

Os seletores recebem apenas matrizes de embeddings: rótulos de identidade nao
participam de DBSCAN, K-Means nem da escolha de hiperparametros.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import product
from typing import Literal

import numpy as np
from sklearn.cluster import DBSCAN, KMeans  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    adjusted_rand_score,
    calinski_harabasz_score,
    completeness_score,
    davies_bouldin_score,
    homogeneity_score,
    normalized_mutual_info_score,
    silhouette_score,
    v_measure_score,
)
from sklearn.neighbors import NearestNeighbors  # type: ignore[import-untyped]

Algoritmo = Literal["dbscan", "kmeans"]

GRADE_EPS_DBSCAN = (0.10, 0.20, 0.35, 0.50, 0.75)
GRADE_MIN_SAMPLES_DBSCAN = (2, 3, 5)
GRADE_K_KMEANS = (2, 3, 5, 8, 13)
COBERTURA_MINIMA_DBSCAN = 0.5
LIMIAR_ESTABILIDADE = 0.5


@dataclass(frozen=True, slots=True)
class DiagnosticosAgrupamento:
    quantidade_amostras: int
    quantidade_clusters: int
    quantidade_ruido: int
    percentual_ruido: float
    cobertura: float
    tamanhos_clusters: dict[int, int]
    quantidade_singletons: int
    quantidade_clusters_pequenos: int
    status: str
    silhouette_cosseno: float | None
    davies_bouldin_euclidiano: float | None
    calinski_harabasz_euclidiano: float | None
    memoria_embeddings_bytes: int
    tempo_ajuste_ms: float


@dataclass(frozen=True, slots=True)
class ResultadoAgrupamento:
    algoritmo: Algoritmo
    configuracao: dict[str, float | int]
    rotulos: np.ndarray
    diagnosticos: DiagnosticosAgrupamento


@dataclass(frozen=True, slots=True)
class CandidatoAgrupamento:
    configuracao: dict[str, float | int]
    diagnosticos: DiagnosticosAgrupamento
    elegivel: bool


@dataclass(frozen=True, slots=True)
class SelecaoHiperparametros:
    algoritmo: Algoritmo
    configuracao_selecionada: dict[str, float | int] | None
    candidatos: tuple[CandidatoAgrupamento, ...]
    criterio: str
    motivo_indisponibilidade: str | None


@dataclass(frozen=True, slots=True)
class DiagnosticoEstabilidade:
    ari_medio: float | None
    ari_desvio_padrao: float | None
    repeticoes_validas: int
    fracao_amostrada: float
    status: str


def normalizar_embeddings(embeddings: np.ndarray) -> np.ndarray:
    """Valida matriz finita e L2-normaliza cada embedding da linha."""
    matriz = np.asarray(embeddings, dtype=np.float64)
    if matriz.ndim != 2 or matriz.shape[0] == 0 or matriz.shape[1] < 2:
        raise ValueError(
            "Embeddings devem formar uma matriz nao vazia com >=2 dimensoes."
        )
    if not np.isfinite(matriz).all():
        raise ValueError("Embeddings devem conter apenas valores finitos.")
    normas = np.linalg.norm(matriz, axis=1)
    if not np.isfinite(normas).all() or np.any(normas <= 0.0):
        raise ValueError("Embeddings nao podem ter norma zero ou nao finita.")
    return np.ascontiguousarray(matriz / normas[:, np.newaxis])


def _validar_rotulos(rotulos: np.ndarray, quantidade: int) -> np.ndarray:
    valores = np.asarray(rotulos)
    if valores.ndim != 1 or valores.size != quantidade:
        raise ValueError("Cada embedding deve ter exatamente um rotulo de cluster.")
    if not np.issubdtype(valores.dtype, np.integer):
        if not np.isfinite(valores.astype(np.float64)).all():
            raise ValueError("Rotulos de cluster devem ser finitos.")
        if not np.equal(valores, np.floor(valores)).all():
            raise ValueError("Rotulos de cluster devem ser inteiros.")
    return valores.astype(np.int64, copy=False)


def _metricas_internas(
    matriz: np.ndarray, rotulos: np.ndarray, ruido: int
) -> tuple[float | None, float | None, float | None]:
    mascara = rotulos != ruido
    pontos = matriz[mascara]
    grupos = rotulos[mascara]
    quantidade_grupos = np.unique(grupos).size
    if quantidade_grupos < 2 or quantidade_grupos >= pontos.shape[0]:
        return None, None, None
    try:
        silhouette = float(silhouette_score(pontos, grupos, metric="cosine"))
        davies = float(davies_bouldin_score(pontos, grupos))
        calinski = float(calinski_harabasz_score(pontos, grupos))
    except (ValueError, FloatingPointError):
        return None, None, None
    return silhouette, davies, calinski


def diagnosticar_agrupamento(
    embeddings: np.ndarray,
    rotulos: np.ndarray,
    *,
    tempo_ajuste_ms: float = 0.0,
    min_samples: int = 1,
    ruido: int = -1,
) -> DiagnosticosAgrupamento:
    matriz = normalizar_embeddings(embeddings)
    grupos = _validar_rotulos(rotulos, matriz.shape[0])
    mascara = grupos != ruido
    tamanhos = Counter(int(rotulo) for rotulo in grupos[mascara])
    quantidade_clusters = len(tamanhos)
    quantidade_ruido = int(np.count_nonzero(~mascara))
    quantidade = matriz.shape[0]
    percentual_ruido = quantidade_ruido / quantidade
    cobertura = 1.0 - percentual_ruido
    singletons = sum(tamanho == 1 for tamanho in tamanhos.values())
    pequenos = sum(tamanho < min_samples for tamanho in tamanhos.values())
    limite_fragmentacao = max(10, math.ceil(math.sqrt(quantidade)))
    if quantidade_clusters == 0:
        status = "sem_clusters"
    elif quantidade_clusters == 1:
        status = "cluster_unico"
    elif percentual_ruido > 0.5:
        status = "ruido_alto"
    elif quantidade_clusters > limite_fragmentacao:
        status = "muitos_clusters_pequenos"
    else:
        status = "clusters_encontrados"
    silhouette, davies, calinski = _metricas_internas(matriz, grupos, ruido)
    return DiagnosticosAgrupamento(
        quantidade_amostras=quantidade,
        quantidade_clusters=quantidade_clusters,
        quantidade_ruido=quantidade_ruido,
        percentual_ruido=percentual_ruido,
        cobertura=cobertura,
        tamanhos_clusters=dict(sorted(tamanhos.items())),
        quantidade_singletons=singletons,
        quantidade_clusters_pequenos=pequenos,
        status=status,
        silhouette_cosseno=silhouette,
        davies_bouldin_euclidiano=davies,
        calinski_harabasz_euclidiano=calinski,
        memoria_embeddings_bytes=int(matriz.nbytes),
        tempo_ajuste_ms=float(tempo_ajuste_ms),
    )


def executar_dbscan(
    embeddings: np.ndarray,
    *,
    eps: float,
    min_samples: int,
) -> ResultadoAgrupamento:
    matriz = normalizar_embeddings(embeddings)
    if not math.isfinite(eps) or not 0.0 < eps <= 2.0:
        raise ValueError("eps deve ser finito e pertencer a (0, 2].")
    if min_samples < 1:
        raise ValueError("min_samples deve ser >= 1.")
    estimador = DBSCAN(eps=eps, min_samples=min_samples, metric="cosine")
    inicio = time.perf_counter()
    rotulos = estimador.fit_predict(matriz)
    tempo = (time.perf_counter() - inicio) * 1000.0
    config: dict[str, float | int] = {"eps": float(eps), "min_samples": min_samples}
    return ResultadoAgrupamento(
        "dbscan",
        config,
        np.asarray(rotulos, dtype=np.int64),
        diagnosticar_agrupamento(
            matriz, rotulos, tempo_ajuste_ms=tempo, min_samples=min_samples
        ),
    )


def executar_kmeans(
    embeddings: np.ndarray,
    *,
    n_clusters: int,
    seed: int = 42,
) -> ResultadoAgrupamento:
    matriz = normalizar_embeddings(embeddings)
    if not 2 <= n_clusters < matriz.shape[0]:
        raise ValueError("K-Means exige 2 <= n_clusters < numero de amostras.")
    if seed < 0:
        raise ValueError("A seed deve ser um inteiro nao negativo.")
    estimador = KMeans(n_clusters=n_clusters, n_init=10, random_state=seed)
    inicio = time.perf_counter()
    rotulos = estimador.fit_predict(matriz)
    tempo = (time.perf_counter() - inicio) * 1000.0
    config: dict[str, float | int] = {
        "n_clusters": n_clusters,
        "n_init": 10,
        "seed": seed,
    }
    return ResultadoAgrupamento(
        "kmeans",
        config,
        np.asarray(rotulos, dtype=np.int64),
        diagnosticar_agrupamento(matriz, rotulos, tempo_ajuste_ms=tempo),
    )


def selecionar_por_grade(
    embeddings: np.ndarray,
    configuracoes: Sequence[dict[str, float | int]],
    *,
    algoritmo: Algoritmo,
    seed: int = 42,
    cobertura_minima: float = COBERTURA_MINIMA_DBSCAN,
) -> SelecaoHiperparametros:
    """Escolhe por silhouette interna; a interface deliberadamente nao recebe y."""
    matriz = normalizar_embeddings(embeddings)
    if not configuracoes:
        raise ValueError("A grade de configuracoes nao pode estar vazia.")
    if not 0.0 <= cobertura_minima <= 1.0:
        raise ValueError("cobertura_minima deve estar em [0, 1].")
    candidatos: list[CandidatoAgrupamento] = []
    resultados: list[ResultadoAgrupamento] = []
    for config in configuracoes:
        if algoritmo == "dbscan":
            if set(config) != {"eps", "min_samples"}:
                raise ValueError("Configuracao DBSCAN exige eps e min_samples.")
            resultado = executar_dbscan(
                matriz, eps=float(config["eps"]), min_samples=int(config["min_samples"])
            )
            cobertura_obrigatoria = cobertura_minima
        else:
            if "n_clusters" not in config or len(config) > 1:
                raise ValueError("Configuracao K-Means exige somente n_clusters.")
            resultado = executar_kmeans(
                matriz, n_clusters=int(config["n_clusters"]), seed=seed
            )
            cobertura_obrigatoria = 1.0
        silhouette = resultado.diagnosticos.silhouette_cosseno
        elegivel = (
            resultado.diagnosticos.quantidade_clusters >= 2
            and resultado.diagnosticos.cobertura >= cobertura_obrigatoria
            and silhouette is not None
            and math.isfinite(silhouette)
        )
        candidatos.append(
            CandidatoAgrupamento(
                resultado.configuracao, resultado.diagnosticos, elegivel
            )
        )
        resultados.append(resultado)

    elegiveis = [
        (candidato, resultado)
        for candidato, resultado in zip(candidatos, resultados, strict=True)
        if candidato.elegivel
    ]
    if not elegiveis:
        return SelecaoHiperparametros(
            algoritmo,
            None,
            tuple(candidatos),
            "silhouette_cosseno_com_cobertura_minima",
            "nenhuma configuracao atende a validade interna e cobertura definida",
        )

    def chave(
        par: tuple[CandidatoAgrupamento, ResultadoAgrupamento],
    ) -> tuple[float, float, float, int, tuple[tuple[str, float | int], ...]]:
        candidato = par[0]
        diagnosticos = candidato.diagnosticos
        silhouette = diagnosticos.silhouette_cosseno
        assert silhouette is not None
        fragmentacao = diagnosticos.quantidade_clusters_pequenos
        ordem = tuple(sorted(candidato.configuracao.items()))
        return (
            -silhouette,
            -diagnosticos.cobertura,
            diagnosticos.percentual_ruido,
            fragmentacao,
            ordem,
        )

    escolhido = min(elegiveis, key=chave)[0]
    return SelecaoHiperparametros(
        algoritmo,
        dict(escolhido.configuracao),
        tuple(candidatos),
        "silhouette_cosseno_com_cobertura_minima",
        None,
    )


def selecionar_dbscan(
    embeddings: np.ndarray,
    *,
    eps_candidatos: Sequence[float] = GRADE_EPS_DBSCAN,
    min_samples_candidatos: Sequence[int] = GRADE_MIN_SAMPLES_DBSCAN,
    cobertura_minima: float = COBERTURA_MINIMA_DBSCAN,
) -> SelecaoHiperparametros:
    configuracoes = [
        {"eps": float(eps), "min_samples": int(min_samples)}
        for eps, min_samples in product(eps_candidatos, min_samples_candidatos)
    ]
    return selecionar_por_grade(
        embeddings,
        configuracoes,
        algoritmo="dbscan",
        cobertura_minima=cobertura_minima,
    )


def selecionar_kmeans(
    embeddings: np.ndarray,
    *,
    k_candidatos: Sequence[int] = GRADE_K_KMEANS,
    seed: int = 42,
) -> SelecaoHiperparametros:
    quantidade = normalizar_embeddings(embeddings).shape[0]
    configuracoes: list[dict[str, float | int]] = [
        {"n_clusters": int(k)} for k in k_candidatos if 2 <= k < quantidade
    ]
    if not configuracoes:
        return SelecaoHiperparametros(
            "kmeans",
            None,
            (),
            "silhouette_cosseno",
            "nenhum n_clusters da grade e menor que a quantidade de amostras",
        )
    return selecionar_por_grade(
        embeddings, configuracoes, algoritmo="kmeans", seed=seed
    )


def calcular_metricas_externas(
    rotulos_identidade: np.ndarray,
    rotulos_cluster: np.ndarray,
    *,
    ruido: int = -1,
) -> dict[str, float | int | None]:
    """Metricas cobertas excluem ruido; ARI secundario mostra ruido como grupo."""
    verdade = np.asarray(rotulos_identidade)
    clusters = np.asarray(rotulos_cluster)
    if verdade.ndim != 1 or clusters.ndim != 1 or verdade.size != clusters.size:
        raise ValueError("Rotulos verdadeiros e de cluster devem estar alinhados.")
    if verdade.size == 0:
        raise ValueError("Metricas externas exigem ao menos uma amostra.")
    if not np.isfinite(clusters.astype(np.float64)).all():
        raise ValueError("Rotulos de cluster devem ser finitos.")
    mascara = clusters != ruido
    quantidade = int(verdade.size)
    cobertura = float(np.count_nonzero(mascara) / quantidade)
    resultado: dict[str, float | int | None] = {
        "quantidade_amostras": quantidade,
        "quantidade_pontos_cobertos": int(np.count_nonzero(mascara)),
        "cobertura": cobertura,
        "ari_sem_ruido": None,
        "nmi_sem_ruido": None,
        "homogeneity_sem_ruido": None,
        "completeness_sem_ruido": None,
        "v_measure_sem_ruido": None,
        "ari_com_ruido_como_cluster": None,
    }
    if np.any(mascara):
        y_coberto = verdade[mascara]
        c_coberto = clusters[mascara]
        resultado.update(
            {
                "ari_sem_ruido": float(adjusted_rand_score(y_coberto, c_coberto)),
                "nmi_sem_ruido": float(
                    normalized_mutual_info_score(y_coberto, c_coberto)
                ),
                "homogeneity_sem_ruido": float(homogeneity_score(y_coberto, c_coberto)),
                "completeness_sem_ruido": float(
                    completeness_score(y_coberto, c_coberto)
                ),
                "v_measure_sem_ruido": float(v_measure_score(y_coberto, c_coberto)),
            }
        )
    resultado["ari_com_ruido_como_cluster"] = float(
        adjusted_rand_score(verdade, clusters)
    )
    return resultado


def diagnosticar_estabilidade(
    embeddings: np.ndarray,
    configuracao: dict[str, float | int],
    *,
    algoritmo: Algoritmo,
    seed: int = 42,
    repeticoes: int = 5,
    fracao_amostrada: float = 0.8,
) -> DiagnosticoEstabilidade:
    matriz = normalizar_embeddings(embeddings)
    if repeticoes < 1 or not 0.5 <= fracao_amostrada < 1.0:
        raise ValueError("Repeticoes/fracao de estabilidade invalidas.")
    base = (
        executar_dbscan(
            matriz,
            eps=float(configuracao["eps"]),
            min_samples=int(configuracao["min_samples"]),
        )
        if algoritmo == "dbscan"
        else executar_kmeans(
            matriz, n_clusters=int(configuracao["n_clusters"]), seed=seed
        )
    )
    quantidade = matriz.shape[0]
    tamanho = min(quantidade - 1, max(3, math.ceil(quantidade * fracao_amostrada)))
    if quantidade < 4 or tamanho < 3:
        return DiagnosticoEstabilidade(
            None, None, 0, fracao_amostrada, "amostra_pequena"
        )
    rng = np.random.default_rng(seed)
    valores: list[float] = []
    for indice_repeticao in range(repeticoes):
        indices = np.sort(rng.choice(quantidade, size=tamanho, replace=False))
        subconjunto = matriz[indices]
        try:
            repetido = (
                executar_dbscan(
                    subconjunto,
                    eps=float(configuracao["eps"]),
                    min_samples=int(configuracao["min_samples"]),
                )
                if algoritmo == "dbscan"
                else executar_kmeans(
                    subconjunto,
                    n_clusters=int(configuracao["n_clusters"]),
                    seed=seed + indice_repeticao + 1,
                )
            )
        except ValueError:
            continue
        base_rotulos = base.rotulos[indices]
        repetido_rotulos = repetido.rotulos
        if algoritmo == "dbscan":
            cobertos = (base_rotulos != -1) & (repetido_rotulos != -1)
            base_rotulos = base_rotulos[cobertos]
            repetido_rotulos = repetido_rotulos[cobertos]
        if (
            base_rotulos.size >= 2
            and np.unique(base_rotulos).size >= 2
            and np.unique(repetido_rotulos).size >= 2
        ):
            valores.append(float(adjusted_rand_score(base_rotulos, repetido_rotulos)))
    if not valores:
        return DiagnosticoEstabilidade(None, None, 0, fracao_amostrada, "indisponivel")
    media = float(np.mean(valores))
    desvio = float(np.std(valores, ddof=1)) if len(valores) > 1 else 0.0
    status = "instavel" if media < LIMIAR_ESTABILIDADE else "estabilidade_observada"
    return DiagnosticoEstabilidade(
        media, desvio, len(valores), fracao_amostrada, status
    )


def valores_k_vizinhos(embeddings: np.ndarray, *, k: int = 5) -> np.ndarray:
    """Distancias cosseno ao k-esimo vizinho sem guardar matriz n x n."""
    matriz = normalizar_embeddings(embeddings)
    if not 1 <= k < matriz.shape[0]:
        raise ValueError("k deve estar em [1, quantidade_de_amostras - 1].")
    vizinhos = NearestNeighbors(n_neighbors=k + 1, metric="cosine", algorithm="brute")
    vizinhos.fit(matriz)
    distancias, _ = vizinhos.kneighbors(matriz)
    resultado = np.sort(distancias[:, -1].astype(np.float64, copy=False))
    return resultado


def contar_embeddings_duplicados(
    embeddings: np.ndarray, *, distancia_cosseno_maxima: float = 1e-6
) -> dict[str, int | float]:
    """Conta linhas exatas extras e amostras com vizinho muito proximo.

    A segunda contagem e por amostra, nao por par, e serve como alerta de
    quase-duplicatas; nao e uma verificacao perceptual de imagens.
    """
    matriz = normalizar_embeddings(embeddings)
    if not math.isfinite(distancia_cosseno_maxima) or distancia_cosseno_maxima < 0.0:
        raise ValueError("distancia_cosseno_maxima deve ser finita e nao negativa.")
    _, contagens = np.unique(matriz, axis=0, return_counts=True)
    duplicados_exatos = int(np.sum(contagens - 1))
    vizinhos = NearestNeighbors(n_neighbors=2, metric="cosine", algorithm="brute")
    vizinhos.fit(matriz)
    distancias, _ = vizinhos.kneighbors(matriz)
    mais_proximos = distancias[:, -1]
    return {
        "linhas_duplicadas_exatas_excedentes": duplicados_exatos,
        "amostras_com_vizinho_proximo": int(
            np.count_nonzero(mais_proximos <= distancia_cosseno_maxima)
        ),
        "limite_distancia_cosseno": float(distancia_cosseno_maxima),
    }
