"""Gráficos da Etapa 3; recebe resultados reais mantidos em memória.

O módulo não fabrica dados nem lê imagens. O executor só o chama depois de
uma avaliação autorizada e grava os gráficos sob avaliacao/.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from scripts.identificacao_aberta import RelatorioIdentificacao


def _salvar(figura: plt.Figure, destino: Path) -> Path:
    figura.tight_layout()
    figura.savefig(destino, dpi=150)
    plt.close(figura)
    return destino


def _taxa(numerador: int, denominador: int) -> float:
    return numerador / denominador if denominador else float("nan")


def _numero_ou_nan(valor: float | None) -> float:
    return valor if valor is not None else float("nan")


def gerar(
    saida: Path,
    *,
    relatorio_curva: RelatorioIdentificacao,
    relatorio_erros: RelatorioIdentificacao,
    nome_limiar_erros: str,
    limiar_erros: float,
    por_limiar: Mapping[str, RelatorioIdentificacao],
    por_tamanho: Mapping[int, RelatorioIdentificacao],
    por_referencias: Mapping[int, RelatorioIdentificacao] | None = None,
) -> list[Path]:
    """Produz oito PNGs a partir de observações do conjunto de teste em RAM."""
    saida.mkdir(parents=True, exist_ok=True)
    arquivos: list[Path] = []
    observacoes = relatorio_curva.observacoes
    conhecidas = [obs for obs in observacoes if obs.conhecida]
    desconhecidas = [obs for obs in observacoes if not obs.conhecida]

    limiares = np.linspace(0.0, 2.0, 201)
    fpir: list[float] = []
    fnir: list[float] = []
    identificacao: list[float] = []
    for limiar in limiares:
        falsas = int(
            sum(
                obs.extracao_valida
                and obs.distancia_candidata is not None
                and obs.motivo.value != "empate"
                and obs.distancia_candidata <= limiar
                for obs in desconhecidas
            )
        )
        corretas = int(
            sum(
                obs.extracao_valida
                and obs.candidato_correto
                and obs.distancia_candidata is not None
                and obs.distancia_candidata <= limiar
                for obs in conhecidas
            )
        )
        fpir.append(_taxa(falsas, len(desconhecidas)))
        fnir.append(1.0 - _taxa(corretas, len(conhecidas)))
        identificacao.append(_taxa(corretas, len(conhecidas)))

    fig, ax = plt.subplots()
    ax.plot(fpir, fnir, label="FPIR × FNIR (teste)")
    ax.set(
        xlabel="FPIR end-to-end",
        ylabel="FNIR end-to-end",
        title="Etapa 3 — FPIR versus FNIR (teste)",
    )
    ax.grid(True, alpha=0.3)
    ax.legend()
    arquivos.append(_salvar(fig, saida / "fpir-vs-fnir.png"))

    fig, ax = plt.subplots()
    ax.plot(limiares, identificacao, label="Identificação correta")
    ax.set(
        xlabel="Limiar de distância cosseno",
        ylabel="Taxa end-to-end",
        title="Etapa 3 — identificação correta por limiar (teste)",
    )
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend()
    arquivos.append(_salvar(fig, saida / "identificacao-por-limiar.png"))

    tamanhos = sorted(por_tamanho)
    fig, ax = plt.subplots()
    ax.plot(
        tamanhos,
        [
            _numero_ou_nan(por_tamanho[n].metricas.identificacao_correta_end_to_end)
            for n in tamanhos
        ],
        marker="o",
        label="Identificação correta",
    )
    ax.plot(
        tamanhos,
        [
            _numero_ou_nan(por_tamanho[n].metricas.top1_accuracy_end_to_end)
            for n in tamanhos
        ],
        marker="o",
        label="Top-1",
    )
    ax.set(
        xlabel="Identidades na galeria",
        ylabel="Taxa end-to-end",
        title="Etapa 3 — desempenho por tamanho da galeria (teste)",
    )
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend()
    arquivos.append(_salvar(fig, saida / "desempenho-por-galeria.png"))

    erros = relatorio_erros.erros
    nomes_erros = (
        "identificação correta",
        "rejeição conhecido",
        "troca de identidade",
        "rejeição desconhecido",
        "falsa identificação",
        "falha de extração",
        "empate",
    )
    contagens = (
        erros.identificacao_correta,
        erros.rejeicao_conhecido_limiar,
        erros.troca_identidade,
        erros.rejeicao_desconhecido,
        erros.falsa_identificacao_desconhecido,
        erros.falha_extracao_consulta,
        erros.empate,
    )
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.barh(nomes_erros, contagens)
    ax.set(
        xlabel="Consultas",
        title=(
            "Etapa 3 — contagens de erros e acertos "
            f"({nome_limiar_erros}, limiar {limiar_erros:.6g}, teste)"
        ),
    )
    ax.grid(axis="x", alpha=0.3)
    arquivos.append(_salvar(fig, saida / "tipos-de-erro.png"))

    dist_conhecidas = [
        obs.distancia_candidata
        for obs in conhecidas
        if obs.distancia_candidata is not None
    ]
    dist_desconhecidas = [
        obs.distancia_candidata
        for obs in desconhecidas
        if obs.distancia_candidata is not None
    ]
    fig, ax = plt.subplots()
    ax.hist(dist_conhecidas, bins=40, range=(0, 2), alpha=0.55, label="Conhecidas")
    ax.hist(
        dist_desconhecidas, bins=40, range=(0, 2), alpha=0.55, label="Desconhecidas"
    )
    ax.set(
        xlabel="Menor distância cosseno",
        ylabel="Consultas extraídas",
        title="Etapa 3 — distâncias de candidatos (teste)",
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    arquivos.append(_salvar(fig, saida / "distribuicao-distancias.png"))

    nomes = list(por_limiar)
    fig, ax = plt.subplots()
    localizacoes = np.arange(len(nomes))
    largura = 0.38
    taxas_fpir = [_numero_ou_nan(por_limiar[n].metricas.fpir_end_to_end) for n in nomes]
    taxas_fnir = [_numero_ou_nan(por_limiar[n].metricas.fnir_end_to_end) for n in nomes]
    ax.bar(localizacoes - largura / 2, taxas_fpir, largura, label="FPIR")
    ax.bar(localizacoes + largura / 2, taxas_fnir, largura, label="FNIR")
    ax.set_xticks(localizacoes, nomes)
    ax.set(
        ylabel="Taxa end-to-end",
        title=(
            f"Etapa 3 — comparação dos limiares disponíveis ({', '.join(nomes)}, teste)"
        ),
    )
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    arquivos.append(_salvar(fig, saida / "comparacao-limiares.png"))

    fig, ax = plt.subplots()
    ax.plot(
        tamanhos,
        [por_tamanho[n].tempo_comparacao_ms_por_consulta for n in tamanhos],
        marker="o",
        label="Comparação",
    )
    ax.plot(
        tamanhos,
        [por_tamanho[n].tempo_decisao_ms_por_consulta for n in tamanhos],
        marker="o",
        label="Decisão total",
    )
    ax.set(
        xlabel="Identidades na galeria",
        ylabel="Mediana por consulta (ms)",
        title="Etapa 3 — tempo por tamanho da galeria (teste)",
    )
    ax.grid(True, alpha=0.3)
    ax.legend()
    arquivos.append(_salvar(fig, saida / "tempo-por-galeria.png"))

    if por_referencias and len(por_referencias) > 1:
        quantidades = sorted(por_referencias)
        fig, ax = plt.subplots()
        ax.plot(
            quantidades,
            [
                _numero_ou_nan(
                    por_referencias[n].metricas.identificacao_correta_end_to_end
                )
                for n in quantidades
            ],
            marker="o",
            label="Identificação correta",
        )
        ax.plot(
            quantidades,
            [
                _numero_ou_nan(por_referencias[n].metricas.fpir_end_to_end)
                for n in quantidades
            ],
            marker="o",
            label="FPIR",
        )
        ax.set(
            xlabel="Embeddings de referência por identidade",
            ylabel="Taxa end-to-end",
            title="Etapa 3 — impacto de referências com T0 fixo (teste pareado)",
        )
        ax.grid(True, alpha=0.3)
        ax.legend()
        arquivos.append(_salvar(fig, saida / "impacto-multiplas-referencias.png"))
    return arquivos
