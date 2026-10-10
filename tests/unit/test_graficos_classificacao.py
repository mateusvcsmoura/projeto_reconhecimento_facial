"""Teste do contrato gráfico sem salvar resultados biométricos sintéticos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from matplotlib.figure import Figure

from scripts.avaliacao_classificadores import ResultadoEtapa2, avaliar_no_teste
from scripts.classificadores_binarios import (
    caracteristicas_da_distancia,
    treinar_e_selecionar_modelos,
)
from scripts.experimento_classificacao_binaria import ParesEtapa1
from scripts.graficos_classificacao import gerar_graficos


def _resultado_sintetico() -> ResultadoEtapa2:
    identidade_a = np.array([10, 10, 20, 20, 10, 10], dtype=np.int32)
    identidade_b = np.array([10, 10, 21, 21, 30, 30], dtype=np.int32)
    pares = ParesEtapa1(
        conjunto="teste",
        imagem_a=np.arange(0, 12, 2),
        imagem_b=np.arange(1, 12, 2),
        identidade_a=identidade_a,
        identidade_b=identidade_b,
        distancia=np.array([0.1, 0.2, 0.6, 0.7, 0.8, 0.9]),
        rotulo=(identidade_a == identidade_b).astype(np.int8),
    )
    distancia_treino = np.array([0.1, 0.15, 0.2, 0.25, 0.65, 0.7, 0.75, 0.8])
    rotulos_treino = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=np.int8)
    modelos = treinar_e_selecionar_modelos(
        caracteristicas_da_distancia(distancia_treino),
        rotulos_treino,
        caracteristicas_da_distancia(distancia_treino),
        rotulos_treino,
        far_maximo=0.0,
        seed=42,
    )
    return avaliar_no_teste(pares, modelos, seed=42, replicas=20)


def test_gerar_graficos_retorna_oito_svg_rotulados(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    salvos: list[tuple[str, str]] = []

    def capturar_salvamento(
        figura: Figure, caminho: str | Path, *_args: object, **_kwargs: object
    ) -> None:
        salvos.append((Path(caminho).name, figura.axes[0].get_title()))

    monkeypatch.setattr(Figure, "savefig", capturar_salvamento)
    resultado = _resultado_sintetico()

    caminhos = gerar_graficos(
        resultado, tmp_path, origem_real_verificada=True
    )

    assert len(caminhos) == 8
    assert all(caminho.suffix == ".svg" for caminho in caminhos)
    assert {caminho.name for caminho in caminhos} == {nome for nome, _ in salvos}
    assert all("teste" in titulo.casefold() for _, titulo in salvos)
    assert all(not caminho.exists() for caminho in caminhos)


def test_graficos_sinteticos_nao_sao_persistidos_por_padrao(
    tmp_path: Path,
) -> None:
    with pytest.raises(PermissionError, match="validação real"):
        gerar_graficos(_resultado_sintetico(), tmp_path)
    assert not list(tmp_path.glob("*.svg"))
