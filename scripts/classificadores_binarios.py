"""Classificadores supervisionados para pares de verificação facial 1:1.

Este módulo recebe somente distâncias derivadas de embeddings já extraídos.
Ele não importa nem ajusta o FaceNet512.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.naive_bayes import GaussianNB  # type: ignore[import-untyped]
from sklearn.tree import DecisionTreeClassifier  # type: ignore[import-untyped]


@dataclass(frozen=True, slots=True)
class ModeloSelecionado:
    """Estimador congelado pela seleção feita no subconjunto de validação."""

    nome: str
    estimador: Any
    parametros: dict[str, object]
    limiar_score: float
    far_treino: float
    frr_treino: float
    far_validacao: float
    frr_validacao: float
    tempo_treino_s: float


def caracteristicas_da_distancia(distancias: np.ndarray) -> np.ndarray:
    """Converte um vetor de distâncias finitas em uma característica por linha."""
    valores = np.asarray(distancias, dtype=np.float64)
    if valores.ndim != 1 or valores.size == 0:
        raise ValueError("As distâncias devem ser um vetor 1-D não vazio.")
    if not np.isfinite(valores).all():
        raise ValueError("As distâncias devem conter somente valores finitos.")
    return valores.reshape(-1, 1)


def _validar_rotulos(rotulos: np.ndarray, quantidade: int, nome: str) -> np.ndarray:
    valores = np.asarray(rotulos)
    if valores.ndim != 1 or valores.size != quantidade:
        raise ValueError(f"Os rótulos de {nome} devem ter forma ({quantidade},).")
    if not np.isin(valores, [0, 1]).all() or np.unique(valores).size != 2:
        raise ValueError(f"{nome} precisa conter as duas classes 0 e 1.")
    return valores.astype(np.int8, copy=False)


def _validar_X(X: np.ndarray, nome: str) -> np.ndarray:
    valores = np.asarray(X, dtype=np.float64)
    if valores.ndim != 2 or valores.shape[1] != 1 or valores.shape[0] == 0:
        raise ValueError(f"X_{nome} deve ser uma matriz não vazia com uma coluna.")
    if not np.isfinite(valores).all():
        raise ValueError(f"X_{nome} deve conter somente valores finitos.")
    return valores


def selecionar_limiar_por_far(
    rotulos: np.ndarray,
    escores: np.ndarray,
    far_maximo: float = 0.001,
) -> tuple[float, float, float] | None:
    """Escolhe limiar exato no score que minimiza FRR sob o teto de FAR.

    Ordena os scores uma vez e acumula os rótulos em grupos de empate.
    Escores maiores indicam mais evidência de identidade igual. Os empates
    entre taxas são resolvidos por FAR menor e depois pelo limiar mais alto.
    """
    scores = np.asarray(escores, dtype=np.float64)
    y = _validar_rotulos(rotulos, scores.size, "dados de limiar")
    if scores.ndim != 1 or scores.size == 0 or not np.isfinite(scores).all():
        raise ValueError("Os escores devem ser um vetor 1-D finito e não vazio.")
    if not 0.0 <= far_maximo <= 1.0:
        raise ValueError("O teto de FAR deve estar entre 0 e 1.")

    ordem = np.argsort(scores, kind="mergesort")[::-1]
    scores_ordenados = scores[ordem]
    rotulos_ordenados = y[ordem]
    fins_dos_empates = np.flatnonzero(
        np.r_[scores_ordenados[:-1] != scores_ordenados[1:], True]
    )
    verdadeiros_positivos = np.cumsum(rotulos_ordenados == 1)[fins_dos_empates]
    falsos_positivos = np.cumsum(rotulos_ordenados == 0)[fins_dos_empates]
    limiares = scores_ordenados[fins_dos_empates]
    far = falsos_positivos / np.count_nonzero(y == 0)
    frr = 1.0 - verdadeiros_positivos / np.count_nonzero(y == 1)
    elegiveis = np.flatnonzero(
        (far <= far_maximo + 1e-12) & (verdadeiros_positivos > 0)
    )
    if not elegiveis.size:
        return None
    # Primary: minimum FRR. Ties: minimum FAR, then highest threshold.
    ordem_preferencia = np.lexsort(
        (-limiares[elegiveis], far[elegiveis], frr[elegiveis])
    )
    indice = int(elegiveis[ordem_preferencia[0]])
    return float(limiares[indice]), float(far[indice]), float(frr[indice])


def _taxas(
    rotulos: np.ndarray, escores: np.ndarray, limiar: float
) -> tuple[float, float]:
    aceitos = escores >= limiar
    genuinos = rotulos == 1
    impostores = rotulos == 0
    return (
        float(np.mean(aceitos[impostores])),
        float(np.mean(~aceitos[genuinos])),
    )


def _probabilidade_classe_1(estimador: Any, X: np.ndarray) -> np.ndarray:
    probabilidades = np.asarray(estimador.predict_proba(X), dtype=np.float64)
    classes = np.asarray(estimador.classes_)
    indices = np.flatnonzero(classes == 1)
    if probabilidades.ndim != 2 or indices.size != 1:
        raise ValueError("O estimador não produziu probabilidade para a classe 1.")
    scores = probabilidades[:, int(indices[0])]
    if not np.isfinite(scores).all():
        raise ValueError("O estimador produziu escores não finitos.")
    return scores


def treinar_e_selecionar_modelos(
    X_treino: np.ndarray,
    y_treino: np.ndarray,
    X_validacao: np.ndarray,
    y_validacao: np.ndarray,
    *,
    far_maximo: float = 0.001,
    seed: int = 42,
) -> dict[str, ModeloSelecionado]:
    """Ajusta M2–M4 no treino e seleciona configuração/limiar na validação."""
    treino = _validar_X(X_treino, "treino")
    validacao = _validar_X(X_validacao, "validação")
    y_train = _validar_rotulos(y_treino, treino.shape[0], "treino")
    y_val = _validar_rotulos(y_validacao, validacao.shape[0], "validação")
    if not 0.0 <= far_maximo <= 1.0:
        raise ValueError("O teto de FAR deve estar entre 0 e 1.")

    configuracoes: dict[str, list[tuple[Any, dict[str, object]]]] = {
        "M2": [
            (
                LogisticRegression(
                    C=C, class_weight=class_weight, solver="lbfgs",
                    max_iter=1000, random_state=seed,
                ),
                {"C": C, "class_weight": class_weight},
            )
            for C in (0.1, 1.0, 10.0)
            for class_weight in (None, "balanced")
        ],
        "M3": [
            (GaussianNB(var_smoothing=1e-9), {"var_smoothing": 1e-9})
        ],
        "M4": [
            (
                DecisionTreeClassifier(
                    criterion="gini", max_depth=depth, random_state=seed
                ),
                {"criterion": "gini", "max_depth": depth},
            )
            for depth in (1, 2, 3)
        ],
    }

    selecionados: dict[str, ModeloSelecionado] = {}
    for nome, candidatos in configuracoes.items():
        elegiveis: list[tuple[tuple[float, float, float, int], ModeloSelecionado]] = []
        for ordem, (estimador, parametros) in enumerate(candidatos):
            inicio = perf_counter()
            estimador.fit(treino, y_train)
            tempo_treino = perf_counter() - inicio
            scores_validacao = _probabilidade_classe_1(estimador, validacao)
            selecao = selecionar_limiar_por_far(y_val, scores_validacao, far_maximo)
            if selecao is None:
                continue
            limiar, far_val, frr_val = selecao
            scores_treino = _probabilidade_classe_1(estimador, treino)
            far_train, frr_train = _taxas(y_train, scores_treino, limiar)
            modelo = ModeloSelecionado(
                nome=nome,
                estimador=estimador,
                parametros=parametros,
                limiar_score=limiar,
                far_treino=far_train,
                frr_treino=frr_train,
                far_validacao=far_val,
                frr_validacao=frr_val,
                tempo_treino_s=tempo_treino,
            )
            chave = (frr_val, far_val, -limiar, ordem)
            elegiveis.append((chave, modelo))
        if elegiveis:
            selecionados[nome] = min(elegiveis, key=lambda item: item[0])[1]
    return selecionados
