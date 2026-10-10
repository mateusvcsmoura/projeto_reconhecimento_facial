"""Visualizações para resultados agregados já avaliados no conjunto de teste."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from sklearn.tree import plot_tree  # type: ignore[import-untyped]

from scripts.avaliacao_classificadores import ResultadoEtapa2

_ARQUIVOS = (
    "matrizes_confusao.svg",
    "curvas_roc.svg",
    "far_versus_frr.svg",
    "comparacao_metricas.svg",
    "distribuicao_distancias.svg",
    "calibracao_regressao_logistica.svg",
    "arvore_decisao.svg",
    "tempo_inferencia.svg",
)


def _matrizes_confusao(resultado: ResultadoEtapa2, destino: Path) -> Path:
    quantidade = len(resultado.metodos)
    colunas = min(3, max(1, quantidade))
    linhas = int(np.ceil(quantidade / colunas))
    figura, eixos = plt.subplots(
        linhas, colunas, figsize=(4.2 * colunas, 3.5 * linhas), squeeze=False
    )
    for eixo, (nome, metodo) in zip(
        eixos.flat, resultado.metodos.items(), strict=False
    ):
        m = metodo.metricas
        matriz = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]], dtype=np.int64)
        eixo.imshow(matriz, cmap="Blues")
        for linha in range(2):
            for coluna in range(2):
                eixo.text(
                    coluna,
                    linha,
                    str(matriz[linha, coluna]),
                    ha="center",
                    va="center",
                )
        eixo.set_xticks([0, 1], labels=["Diferente", "Mesma"])
        eixo.set_yticks([0, 1], labels=["Diferente", "Mesma"])
        eixo.set_xlabel("Classe prevista")
        eixo.set_ylabel("Classe real")
        eixo.set_title(f"Teste — matriz de confusão {nome}")
    for eixo in eixos.flat[quantidade:]:
        eixo.set_visible(False)
    figura.suptitle("Etapa 2 · verificação 1:1 · conjunto de teste")
    figura.tight_layout(rect=(0, 0, 1, 0.94))
    caminho = destino / _ARQUIVOS[0]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _curvas_roc(resultado: ResultadoEtapa2, destino: Path) -> Path:
    figura, eixo = plt.subplots(figsize=(7.5, 5.5))
    for nome, metodo in resultado.metodos.items():
        auc = metodo.metricas["auc"]
        legenda = f"{nome} (AUC={auc:.3f})" if auc is not None else f"{nome} (AUC n/d)"
        if metodo.fpr.size:
            eixo.plot(metodo.fpr, metodo.tpr, label=legenda)
        else:
            eixo.plot([], [], label=legenda)
    eixo.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Aleatório")
    eixo.set_xlim(0, 1)
    eixo.set_ylim(0, 1.01)
    eixo.set_xlabel("FAR")
    eixo.set_ylabel("TAR (1 − FRR)")
    eixo.set_title("Teste — curvas ROC dos classificadores 1:1")
    eixo.legend(loc="lower right")
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[1]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _far_versus_frr(resultado: ResultadoEtapa2, destino: Path) -> Path:
    figura, eixo = plt.subplots(figsize=(7.5, 5.5))
    for nome, metodo in resultado.metodos.items():
        if metodo.fpr.size:
            eixo.plot(metodo.fpr, 1.0 - metodo.tpr, label=nome)
        else:
            eixo.plot([], [], label=f"{nome} (sem duas classes)")
        eixo.scatter(
            [metodo.metricas["far"]],
            [metodo.metricas["frr"]],
            s=26,
        )
    eixo.set_xlabel("FAR")
    eixo.set_ylabel("FRR")
    eixo.set_title("Teste — relação FAR versus FRR")
    eixo.legend()
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[2]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _comparacao_metricas(resultado: ResultadoEtapa2, destino: Path) -> Path:
    nomes = list(resultado.metodos)
    chaves = ("far", "frr", "f1", "auc")
    largura = 0.8 / len(chaves)
    figura, eixo = plt.subplots(figsize=(9, 5.5))
    for indice, chave in enumerate(chaves):
        valores = [
            np.nan if resultado.metodos[nome].metricas[chave] is None
            else float(resultado.metodos[nome].metricas[chave])
            for nome in nomes
        ]
        deslocamento = (indice - (len(chaves) - 1) / 2) * largura
        eixo.bar(
            np.arange(len(nomes)) + deslocamento,
            valores,
            largura,
            label=chave.upper(),
        )
    eixo.set_xticks(np.arange(len(nomes)), labels=nomes)
    eixo.set_ylabel("Valor da métrica")
    eixo.set_title("Teste — comparação de métricas por classificador")
    eixo.legend()
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[3]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _distribuicao_distancias(resultado: ResultadoEtapa2, destino: Path) -> Path:
    figura, eixo = plt.subplots(figsize=(8, 5.5))
    for rotulo, nome in ((1, "Mesma identidade"), (0, "Identidades diferentes")):
        distancias = resultado.distancias[resultado.rotulos == rotulo]
        if distancias.size:
            eixo.hist(
                distancias,
                bins=40,
                density=True,
                alpha=0.55,
                label=f"{nome} (n={distancias.size:,})",
            )
    eixo.set_xlabel("Distância cosseno")
    eixo.set_ylabel("Densidade")
    eixo.set_title("Teste — distribuição de distâncias por classe")
    eixo.legend()
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[4]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _calibracao_logistica(resultado: ResultadoEtapa2, destino: Path) -> Path:
    figura, eixo = plt.subplots(figsize=(6.5, 5.5))
    metodo = resultado.metodos.get("M2")
    if metodo is None or metodo.calibracao is None:
        eixo.text(
            0.5,
            0.5,
            "Regressão logística indisponível",
            ha="center",
            va="center",
        )
    else:
        calibracao = metodo.calibracao
        eixo.plot(
            calibracao["media_probabilidade"],
            calibracao["fracao_positiva"],
            marker="o",
            label="Regressão logística",
        )
        eixo.plot(
            [0, 1], [0, 1], linestyle="--", color="gray", label="Calibração ideal"
        )
        eixo.legend()
    eixo.set_xlim(0, 1)
    eixo.set_ylim(0, 1)
    eixo.set_xlabel("Probabilidade estimada média")
    eixo.set_ylabel("Fração positiva observada")
    eixo.set_title("Teste — curva de calibração da regressão logística")
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[5]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _arvore_decisao(resultado: ResultadoEtapa2, destino: Path) -> Path:
    figura, eixo = plt.subplots(figsize=(12, 6))
    if resultado.arvore is None:
        eixo.text(0.5, 0.5, "Árvore de decisão indisponível", ha="center", va="center")
        eixo.set_axis_off()
    else:
        plot_tree(
            resultado.arvore,
            ax=eixo,
            feature_names=["distância cosseno"],
            class_names=["identidades diferentes", "mesma identidade"],
            filled=True,
            rounded=True,
            precision=3,
        )
    eixo.set_title("Teste — árvore de decisão selecionada na validação")
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[6]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def _tempo_inferencia(resultado: ResultadoEtapa2, destino: Path) -> Path:
    nomes = list(resultado.metodos)
    segundos = [resultado.metodos[nome].tempo_inferencia_s * 1000 for nome in nomes]
    figura, eixo = plt.subplots(figsize=(8, 5.5))
    barras = eixo.bar(nomes, segundos)
    for barra, nome in zip(barras, nomes, strict=True):
        eixo.annotate(
            f"{resultado.metodos[nome].tempo_inferencia_por_par_s * 1e6:.2f} µs/par",
            (barra.get_x() + barra.get_width() / 2, barra.get_height()),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    eixo.set_ylabel("Mediana por execução do conjunto (ms)")
    eixo.set_title("Teste — tempo de inferência vetorizada")
    figura.tight_layout()
    caminho = destino / _ARQUIVOS[7]
    figura.savefig(caminho, format="svg", metadata={"Date": None, "Creator": "Etapa 2"})
    plt.close(figura)
    return caminho


def gerar_graficos(
    resultado: ResultadoEtapa2,
    destino: Path,
    *,
    origem_real_verificada: bool = False,
) -> list[Path]:
    """Gera oito SVGs somente após avaliação real aprovada pelo orquestrador.

    O parâmetro de guarda é explícito para impedir que testes sintéticos
    produzam arquivos que possam ser confundidos com resultados biométricos.
    """
    if not origem_real_verificada:
        raise PermissionError(
            "Gráficos persistentes exigem validação real do dataset e do teste."
        )
    if resultado.conjunto != "teste" or not resultado.metodos:
        raise ValueError("O resultado precisa conter métodos avaliados no teste.")
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    funcoes = (
        _matrizes_confusao,
        _curvas_roc,
        _far_versus_frr,
        _comparacao_metricas,
        _distribuicao_distancias,
        _calibracao_logistica,
        _arvore_decisao,
        _tempo_inferencia,
    )
    return [funcao(resultado, destino) for funcao in funcoes]
