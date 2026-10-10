"""Graficos da Etapa 1 -- so no ambiente experimental (matplotlib).

Desenhados exclusivamente a partir de um Experimento executado: nenhum
numero e digitado aqui. SVG vetorial com agregados (contagens, taxas,
histogramas) -- nenhuma imagem de rosto, nenhum nome.

Paleta: instancia de referencia da skill de visualizacao (azul = genuino,
laranja = impostor; texto em tinta neutra, nunca na cor da serie).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")  # sem janela: o script roda em terminal

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure

from scripts.metricas import MatrizDeConfusao, roc

if TYPE_CHECKING:
    from scripts.calibrar_limiar import Experimento, ResultadoNoTeste

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
GRADE = "#e4e3df"
GENUINO = "#2a78d6"
IMPOSTOR = "#eb6834"
AZUL_SEQUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"]

plt.rcParams.update(
    {
        "figure.facecolor": SUPERFICIE,
        "axes.facecolor": SUPERFICIE,
        "savefig.facecolor": SUPERFICIE,
        "axes.edgecolor": GRADE,
        "axes.labelcolor": TINTA_SECUNDARIA,
        "axes.titlecolor": TINTA,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": GRADE,
        "grid.linewidth": 0.6,
        "xtick.color": TINTA_SECUNDARIA,
        "ytick.color": TINTA_SECUNDARIA,
        "legend.frameon": False,
        "font.size": 9,
        "lines.linewidth": 2,
        # Texto como texto, e SVG identico a cada execucao (reprodutivel).
        "svg.fonttype": "none",
        "svg.hashsalt": "etapa1",
    }
)

Limiares = Sequence[tuple[str, float, str]]


def _rarear(n: int, pontos: int = 4000) -> np.ndarray:
    """Indices para desenhar uma curva de n pontos com no maximo ~2*pontos.

    Centenas de milhares de vertices dariam um SVG de dezenas de MB. O
    espacamento log adensa o comeco (FAR baixo, onde a operacao vive); o
    linear cobre o resto.
    """
    if n <= 2 * pontos:
        return np.arange(n)
    log = np.geomspace(1, n, pontos).astype(int) - 1
    linear = np.linspace(0, n - 1, pontos).astype(int)
    return np.unique(np.concatenate([log, linear]))


def _salvar(figura: Figure, caminho: Path) -> Path:
    figura.savefig(
        caminho, format="svg", bbox_inches="tight", metadata={"Date": None}
    )
    plt.close(figura)
    return caminho


def _linhas_de_limiar(eixo: Axes, limiares: Limiares) -> None:
    """Linha vertical por limiar; o menor rotulado a esquerda, o maior a direita.

    Os limiares comparados costumam ficar proximos: rotulos do mesmo lado
    se sobreporiam.
    """
    menor = min(limiar for _, limiar, _ in limiares)
    for rotulo, limiar, estilo in limiares:
        a_esquerda = limiar == menor
        eixo.axvline(limiar, color=TINTA, linestyle=estilo, linewidth=1.2)
        eixo.annotate(
            f"{rotulo}\n{limiar:.4f}",
            xy=(limiar, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(-4 if a_esquerda else 4, -4),
            textcoords="offset points",
            ha="right" if a_esquerda else "left",
            va="top",
            color=TINTA,
            fontsize=8,
            # Fundo da superficie: o rotulo cai sobre as barras do histograma.
            bbox={"boxstyle": "round,pad=0.2", "fc": SUPERFICIE, "ec": "none"},
        )


def histograma(
    destino: Path, genuinas: np.ndarray, impostoras: np.ndarray, limiares: Limiares
) -> Path:
    figura, eixo = plt.subplots(figsize=(7, 3.6))
    todas = np.concatenate([genuinas, impostoras])
    bordas = np.linspace(todas.min(), todas.max(), 120)
    for valores, cor, rotulo in (
        (genuinas, GENUINO, "genuinos"),
        (impostoras, IMPOSTOR, "impostores"),
    ):
        eixo.hist(
            valores,
            bins=bordas,
            density=True,
            histtype="step",
            color=cor,
            label=f"{rotulo}, n = {valores.size}",
        )
    # Folga no topo: os rotulos dos limiares ficam acima das barras.
    eixo.set_ylim(0, eixo.get_ylim()[1] * 1.3)
    _linhas_de_limiar(eixo, limiares)
    eixo.set_title("Distancia cosseno no teste -- cada classe normalizada")
    eixo.set_xlabel("distancia cosseno (Facenet512)")
    eixo.set_ylabel("densidade")
    eixo.legend(loc="upper right")
    return _salvar(figura, destino / "1-histograma-distancias.svg")


def far_frr_por_limiar(
    destino: Path, genuinas: np.ndarray, impostoras: np.ndarray, limiares: Limiares
) -> Path:
    corte, far, tar = roc(genuinas, impostoras)
    # Sem o -inf inicial; rarefeito para o SVG.
    indice = 1 + _rarear(corte.size - 1)
    corte, far, tar = corte[indice], far[indice], tar[indice]
    figura, eixo = plt.subplots(figsize=(7, 3.6))
    eixo.plot(corte, far, color=IMPOSTOR, label="FAR")
    eixo.plot(corte, 1 - tar, color=GENUINO, label="FRR")
    eixo.set_yscale("log")
    # Teto acima de 1 so como folga para os rotulos dos limiares.
    eixo.set_ylim(0.5 / max(impostoras.size, genuinas.size), 8.0)
    _linhas_de_limiar(eixo, limiares)
    eixo.set_title("FAR e FRR por limiar no teste (escala log)")
    eixo.set_xlabel("limiar tau: aceita se distancia <= tau")
    eixo.set_ylabel("taxa de erro")
    eixo.legend(loc="lower right")
    return _salvar(figura, destino / "2-far-frr-por-limiar.svg")


def _matriz(eixo: Axes, titulo: str, m: MatrizDeConfusao, rotular: bool) -> None:
    contagens = np.array([[m.tp, m.fn], [m.fp, m.tn]])
    # Cor pela taxa da linha: com milhares de impostores, a contagem bruta
    # apagaria a linha dos genuinos.
    taxas = contagens / contagens.sum(axis=1, keepdims=True)
    mapa = LinearSegmentedColormap.from_list("azul", AZUL_SEQUENCIAL)
    eixo.imshow(taxas, cmap=mapa, vmin=0, vmax=1)
    nomes = [["TP", "FN"], ["FP", "TN"]]
    for i in range(2):
        for j in range(2):
            eixo.text(
                j,
                i,
                f"{nomes[i][j]}\n{contagens[i, j]}\n{taxas[i, j]:.3%}",
                ha="center",
                va="center",
                fontsize=9,
                color="#ffffff" if taxas[i, j] > 0.55 else TINTA,
            )
    eixo.set_xticks([0, 1], ["aceitar", "recusar"])
    eixo.set_xlabel("decisao")
    eixo.set_title(titulo)
    eixo.grid(False)
    # So o primeiro painel rotula as linhas: no segundo, os rotulos
    # invadiriam o painel vizinho.
    if rotular:
        eixo.set_yticks([0, 1], ["mesma pessoa", "pessoa diferente"])
        eixo.set_ylabel("verdade")
    else:
        eixo.set_yticks([0, 1], ["", ""])


def matrizes(
    destino: Path, base: ResultadoNoTeste, calibrado: ResultadoNoTeste
) -> Path:
    figura, eixos = plt.subplots(1, 2, figsize=(8, 3.6), constrained_layout=True)
    for i, (eixo, r) in enumerate(zip(eixos, (base, calibrado), strict=True)):
        _matriz(eixo, f"{r.metodo} (tau = {r.limiar:.4f})", r.matriz, i == 0)
    figura.suptitle("Matrizes de confusao no teste (percentual por linha)")
    return _salvar(figura, destino / "3-matrizes-de-confusao.svg")


def curva_roc(
    destino: Path,
    genuinas: np.ndarray,
    impostoras: np.ndarray,
    auc: float,
    pontos: Sequence[ResultadoNoTeste],
) -> Path:
    _, far, tar = roc(genuinas, impostoras)
    indice = _rarear(far.size)
    far, tar = far[indice], tar[indice]
    piso = 0.5 / impostoras.size  # FAR zero nao existe em escala log
    figura, eixo = plt.subplots(figsize=(5.5, 4.2))
    eixo.plot(np.maximum(far, piso), tar, color=GENUINO)
    for r, marcador in zip(pontos, ("o", "s"), strict=True):
        far_r = r.matriz.far or 0.0
        tar_r = 1 - (r.matriz.frr or 0.0)
        x = max(far_r, piso)
        eixo.plot(
            x, tar_r, marcador, color=TINTA, markersize=8, markerfacecolor=SUPERFICIE
        )
        eixo.annotate(
            f"{r.metodo}\nFAR {far_r:.3%} | TAR {tar_r:.2%}",
            (x, tar_r),
            xytext=(8, -18),
            textcoords="offset points",
            color=TINTA,
            fontsize=8,
        )
    eixo.set_xscale("log")
    eixo.set_xlim(piso, 1.0)
    eixo.set_title(f"ROC no teste -- AUC {auc:.4f} (a mesma para todo limiar)")
    eixo.set_xlabel("FAR (escala log)")
    eixo.set_ylabel("TAR = 1 - FRR")
    return _salvar(figura, destino / "4-roc.svg")


def _pct(valor: float | None) -> str:
    return "indef." if valor is None else f"{valor:.3%}"


def tabela(destino: Path, resultados: Sequence[ResultadoNoTeste]) -> Path:
    cabecalho = [
        "metodo", "limiar", "TP", "FN", "FP", "TN", "FAR [IC95]", "FRR [IC95]",
        "acuracia", "precisao", "recall", "F1",
    ]  # fmt: skip
    linhas = [
        [
            r.metodo,
            f"{r.limiar:.4f}",
            r.matriz.tp,
            r.matriz.fn,
            r.matriz.fp,
            r.matriz.tn,
            f"{_pct(r.matriz.far)} [{r.ic_far.inferior:.3%}; {r.ic_far.superior:.3%}]",
            f"{_pct(r.matriz.frr)} [{r.ic_frr.inferior:.3%}; {r.ic_frr.superior:.3%}]",
            _pct(r.matriz.acuracia),
            _pct(r.matriz.precisao),
            _pct(r.matriz.recall),
            _pct(r.matriz.f1),
        ]
        for r in resultados
    ]
    figura, eixo = plt.subplots(figsize=(13, 0.6 + 0.35 * len(linhas)))
    eixo.axis("off")
    quadro = eixo.table(
        cellText=linhas, colLabels=cabecalho, loc="center", cellLoc="center"
    )
    quadro.auto_set_font_size(False)
    quadro.set_fontsize(8)
    quadro.auto_set_column_width(list(range(len(cabecalho))))
    for (linha, _), celula in quadro.get_celld().items():
        celula.set_edgecolor(GRADE)
        celula.set_text_props(color=TINTA, weight="bold" if linha == 0 else "normal")
    eixo.set_title("Metricas no teste (IC95: bootstrap por identidade)")
    return _salvar(figura, destino / "5-tabela-metricas.svg")


def gerar(destino: Path, experimento: Experimento) -> list[Path]:
    from scripts.calibrar_limiar import BASELINE

    destino.mkdir(parents=True, exist_ok=True)
    teste = experimento.pares["teste"]
    genuinas, impostoras = teste.genuinas, teste.impostoras
    por_metodo = {r.metodo: r for r in experimento.resultados}
    base, calibrado = por_metodo[BASELINE], por_metodo[experimento.principal]
    limiares = [
        ("baseline (herdado)", base.limiar, "--"),
        (f"calibrado {calibrado.metodo}", calibrado.limiar, "-"),
    ]
    return [
        histograma(destino, genuinas, impostoras, limiares),
        far_frr_por_limiar(destino, genuinas, impostoras, limiares),
        matrizes(destino, base, calibrado),
        curva_roc(destino, genuinas, impostoras, experimento.auc, [base, calibrado]),
        tabela(destino, experimento.resultados),
    ]
