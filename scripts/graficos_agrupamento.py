"""Visualizacoes anonimas para execucoes autorizadas da Etapa 4."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from sklearn.decomposition import PCA  # type: ignore[import-untyped]

from scripts.agrupamento_embeddings import (
    ResultadoAgrupamento,
    calcular_metricas_externas,
    valores_k_vizinhos,
)


def _salvar(figura: plt.Figure, diretorio: Path, nome: str) -> Path:
    destino = diretorio / nome
    figura.tight_layout()
    figura.savefig(destino, dpi=160, bbox_inches="tight")
    plt.close(figura)
    return destino


def _pca(
    matriz: np.ndarray, rotulos: np.ndarray, titulo: str, legenda: str
) -> plt.Figure:
    pontos = PCA(n_components=2, random_state=42).fit_transform(matriz)
    figura, eixo = plt.subplots(figsize=(8, 6))
    dispersao = eixo.scatter(
        pontos[:, 0],
        pontos[:, 1],
        c=rotulos,
        cmap="tab20",
        s=24,
        alpha=0.8,
    )
    figura.colorbar(dispersao, ax=eixo, label=legenda)
    eixo.set(
        title=titulo, xlabel="Componente principal 1", ylabel="Componente principal 2"
    )
    return figura


def gerar(
    diretorio: Path,
    embeddings_teste: np.ndarray,
    identidades_teste_codificadas: np.ndarray,
    resultados_teste: dict[str, ResultadoAgrupamento],
    candidatos_dbscan: Sequence[tuple[float, float | None]],
    embeddings_desenvolvimento: np.ndarray,
) -> list[Path]:
    """Gera figuras somente quando o executor ja ultrapassou o gate autorizado."""
    if not resultados_teste:
        return []
    matriz = np.asarray(embeddings_teste, dtype=np.float64)
    identidades = np.asarray(identidades_teste_codificadas)
    if matriz.ndim != 2 or identidades.ndim != 1 or matriz.shape[0] != identidades.size:
        raise ValueError("Embeddings e identidades da particao teste devem alinhar.")
    if matriz.shape[0] < 2:
        return []
    diretorio.mkdir(parents=True, exist_ok=True)
    arquivos: list[Path] = []

    for nome, resultado in resultados_teste.items():
        rotulos_sem_ruido = np.where(resultado.rotulos == -1, -1, resultado.rotulos)
        arquivos.append(
            _salvar(
                _pca(
                    matriz,
                    rotulos_sem_ruido,
                    f"PCA por cluster — teste autorizado ({nome})",
                    "Cluster (-1 = ruído)",
                ),
                diretorio,
                f"pca-clusters-{nome}.png",
            )
        )

    identidade_idx = np.unique(identidades, return_inverse=True)[1]
    arquivos.append(
        _salvar(
            _pca(
                matriz,
                identidade_idx,
                "PCA por identidade verdadeira — avaliação do teste",
                "Identidade codificada, sem identificador pessoal",
            ),
            diretorio,
            "pca-identidades-avaliacao.png",
        )
    )

    figura, eixo = plt.subplots(figsize=(8, 5))
    for nome, resultado in resultados_teste.items():
        tamanhos = sorted(resultado.diagnosticos.tamanhos_clusters.values())
        eixo.plot(range(1, len(tamanhos) + 1), tamanhos, marker="o", label=nome)
    eixo.set(
        title="Distribuição dos tamanhos de cluster — teste",
        xlabel="Cluster ordenado por tamanho",
        ylabel="Amostras",
    )
    eixo.legend()
    arquivos.append(_salvar(figura, diretorio, "tamanhos-clusters.png"))

    if candidatos_dbscan:
        figura, eixos = plt.subplots(1, 2, figsize=(12, 5))
        indices = np.arange(len(candidatos_dbscan))
        eixos[0].bar(
            indices,
            [item[0] for item in candidatos_dbscan],
            color="#5470c6",
        )
        eixos[0].set(
            title="Ruído por configuração — desenvolvimento", ylabel="Proporção"
        )
        eixos[1].bar(
            indices,
            [
                np.nan if silhouette is None else silhouette
                for _ruido, silhouette in candidatos_dbscan
            ],
            color="#91cc75",
        )
        eixos[1].set(
            title="Silhouette por configuração — desenvolvimento", ylabel="Silhouette"
        )
        rotulos = [str(i + 1) for i in range(len(candidatos_dbscan))]
        for eixo in eixos:
            eixo.set_xlabel("Configuração (ordem da grade)")
            eixo.set_xticks(indices, rotulos, rotation=45)
        arquivos.append(_salvar(figura, diretorio, "diagnosticos-dbscan-grade.png"))

    figura, eixos = plt.subplots(1, 2, figsize=(12, 5))
    nomes = list(resultados_teste)
    eixos[0].bar(
        nomes,
        [resultados_teste[nome].diagnosticos.percentual_ruido for nome in nomes],
        color="#ee6666",
    )
    eixos[0].set(title="Percentual de ruído — teste", ylabel="Proporção")
    eixos[1].bar(
        nomes,
        [
            np.nan
            if resultados_teste[nome].diagnosticos.silhouette_cosseno is None
            else resultados_teste[nome].diagnosticos.silhouette_cosseno
            for nome in nomes
        ],
        color="#fac858",
    )
    eixos[1].set(title="Silhouette cosseno — teste", ylabel="Silhouette")
    arquivos.append(_salvar(figura, diretorio, "comparacao-dbscan-kmeans.png"))

    metricas = {
        nome: calcular_metricas_externas(identidades, resultado.rotulos)
        for nome, resultado in resultados_teste.items()
    }
    figura, eixo = plt.subplots(figsize=(8, 5))
    posicoes = np.arange(len(nomes))
    largura = 0.36
    for deslocamento, chave, rotulo, cor in (
        (-largura / 2, "ari_sem_ruido", "ARI (sem ruído)", "#5470c6"),
        (largura / 2, "nmi_sem_ruido", "NMI (sem ruído)", "#91cc75"),
    ):
        valores = []
        for nome in nomes:
            valor = metricas[nome][chave]
            valores.append(np.nan if valor is None else float(valor))
        eixo.bar(
            posicoes + deslocamento, valores, width=largura, label=rotulo, color=cor
        )
    eixo.set(
        title="Métricas externas por algoritmo — teste",
        ylabel="Pontuação",
        xticks=posicoes,
        xticklabels=nomes,
    )
    eixo.legend()
    arquivos.append(_salvar(figura, diretorio, "ari-nmi-comparacao.png"))

    quantidade = np.asarray(embeddings_desenvolvimento).shape[0]
    if quantidade >= 3:
        k = min(5, quantidade - 1)
        distancias = valores_k_vizinhos(embeddings_desenvolvimento, k=k)
        figura, eixo = plt.subplots(figsize=(8, 5))
        eixo.plot(np.arange(1, len(distancias) + 1), distancias)
        eixo.set(
            title=f"Distância cosseno ao {k}º vizinho — desenvolvimento",
            xlabel="Amostras ordenadas",
            ylabel="Distância cosseno",
        )
        arquivos.append(_salvar(figura, diretorio, "distancia-k-vizinhos.png"))
    return arquivos
