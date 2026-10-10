"""Métricas, incerteza agrupada e latência para a Etapa 2."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
from scipy.stats import kurtosis, norm, skew  # type: ignore[import-untyped]
from sklearn.metrics import roc_auc_score, roc_curve  # type: ignore[import-untyped]

from scripts.calibrar_limiar import (
    Intervalo,
    Pares,
    bootstrap_por_identidade,
    intervalo_95,
)
from scripts.classificadores_binarios import ModeloSelecionado
from scripts.experimento_classificacao_binaria import (
    LIMIAR_M1_ETAPA1,
    ParesEtapa1,
)
from scripts.metricas import MatrizDeConfusao

TETO_FAR_PADRAO = 0.001
REPETICOES_TEMPO = 10
QUANTIS = (0.05, 0.25, 0.5, 0.75, 0.95)
DiagnosticoClasse = dict[str, int | float | dict[str, float] | None]


@dataclass(frozen=True, slots=True)
class ResultadoMetodo:
    """Métricas agregadas e escores em memória para os gráficos."""

    nome: str
    limiar_score: float
    metricas: dict[str, Any]
    escores: np.ndarray
    probabilidades: np.ndarray | None
    fpr: np.ndarray
    tpr: np.ndarray
    ic_far: Intervalo
    ic_frr: Intervalo
    pares_de_identidades_impostoras: int
    atende_teto_far: bool
    tempo_treino_s: float | None
    tempo_inferencia_s: float
    tempo_inferencia_por_par_s: float
    diferenca_ic_far_vs_m0: Intervalo | None
    diferenca_ic_frr_vs_m0: Intervalo | None
    calibracao: dict[str, list[float | int]] | None
    distribuicao_probabilidades: dict[str, float] | None


@dataclass(frozen=True, slots=True)
class ResultadoEtapa2:
    """Resultado agregado da avaliação final, sem IDs de pessoas ou imagens."""

    conjunto: str
    seed: int
    replicas_bootstrap: int
    quantidade_pares: int
    quantidade_identidades: int
    rotulos: np.ndarray
    distancias: np.ndarray
    metodos: dict[str, ResultadoMetodo]
    indisponiveis: dict[str, str]
    diagnostico_gaussian_nb: dict[str, DiagnosticoClasse]
    parametros_arvore: dict[str, Any] | None
    arvore: Any | None


def _validar_escores(
    rotulos: np.ndarray,
    escores: np.ndarray,
    probabilidades: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
    y = np.asarray(rotulos)
    scores = np.asarray(escores, dtype=np.float64)
    if y.ndim != 1 or scores.ndim != 1 or y.size == 0 or y.size != scores.size:
        raise ValueError("Rótulos e escores devem ser vetores não vazios e alinhados.")
    if not np.isin(y, [0, 1]).all():
        raise ValueError("Os rótulos devem ser binários 0/1.")
    if not np.isfinite(scores).all():
        raise ValueError("Os escores devem ser finitos.")
    probs: np.ndarray | None = None
    if probabilidades is not None:
        probs = np.asarray(probabilidades, dtype=np.float64)
        if probs.ndim != 1 or probs.size != y.size or not np.isfinite(probs).all():
            raise ValueError("As probabilidades devem ser finitas e alinhadas.")
        if np.any((probs < 0.0) | (probs > 1.0)):
            raise ValueError("As probabilidades devem estar no intervalo [0, 1].")
    return y.astype(np.int8, copy=False), scores, probs


def _calibracao_probabilidades(
    rotulos: np.ndarray, probabilidades: np.ndarray, bins: int = 10
) -> dict[str, list[float] | list[int]]:
    limites = np.linspace(0.0, 1.0, bins + 1)
    indices = np.minimum((probabilidades * bins).astype(np.int64), bins - 1)
    medias_previstas: list[float] = []
    fracoes_positivas: list[float] = []
    quantidades: list[int] = []
    for indice in range(bins):
        mascara = indices == indice
        if not np.any(mascara):
            continue
        medias_previstas.append(float(np.mean(probabilidades[mascara])))
        fracoes_positivas.append(float(np.mean(rotulos[mascara])))
        quantidades.append(int(np.count_nonzero(mascara)))
    return {
        "limite_inferior": [
            float(limites[index])
            for index in range(bins)
            if np.any(indices == index)
        ],
        "media_probabilidade": medias_previstas,
        "fracao_positiva": fracoes_positivas,
        "quantidade": quantidades,
    }


def _distribuicao_probabilidades(probabilidades: np.ndarray) -> dict[str, float]:
    valores = np.quantile(probabilidades, QUANTIS)
    return {
        "media": float(np.mean(probabilidades)),
        "desvio_padrao": float(np.std(probabilidades)),
        "minimo": float(np.min(probabilidades)),
        "maximo": float(np.max(probabilidades)),
        **{
            f"q{int(q * 100):02d}": float(valor)
            for q, valor in zip(QUANTIS, valores, strict=True)
        },
    }


def _eer(rotulos: np.ndarray, escores: np.ndarray) -> float | None:
    if np.unique(rotulos).size != 2:
        return None
    far, tar, _ = roc_curve(rotulos, escores, drop_intermediate=False)
    frr = 1.0 - tar
    diferenca = far - frr
    indices = np.flatnonzero(diferenca >= 0.0)
    if indices.size == 0:
        return None
    indice = int(indices[0])
    if indice == 0 or diferenca[indice] == 0.0:
        return float((far[indice] + frr[indice]) / 2.0)
    anterior = indice - 1
    denominador = diferenca[indice] - diferenca[anterior]
    if denominador == 0.0:
        return float((far[indice] + frr[indice]) / 2.0)
    fracao = -diferenca[anterior] / denominador
    far_interpolada = far[anterior] + fracao * (far[indice] - far[anterior])
    frr_interpolada = frr[anterior] + fracao * (frr[indice] - frr[anterior])
    return float((far_interpolada + frr_interpolada) / 2.0)


def avaliar_escores(
    rotulos: np.ndarray,
    escores: np.ndarray,
    limiar_score: float,
    *,
    probabilidades: np.ndarray | None = None,
) -> dict[str, Any]:
    """Calcula métricas binárias; score maior sempre indica classe positiva."""
    y, scores, probs = _validar_escores(rotulos, escores, probabilidades)
    if not np.isfinite(limiar_score):
        raise ValueError("O limiar de score deve ser finito.")
    previsto = scores >= limiar_score
    genuinos = y == 1
    impostores = y == 0
    tp = int(np.count_nonzero(previsto & genuinos))
    fn = int(np.count_nonzero(~previsto & genuinos))
    fp = int(np.count_nonzero(previsto & impostores))
    tn = int(np.count_nonzero(~previsto & impostores))
    matriz = MatrizDeConfusao(tp=tp, tn=tn, fp=fp, fn=fn)
    auc = (
        float(roc_auc_score(y, scores))
        if np.unique(y).size == 2
        else None
    )
    probabilidades_metricas: dict[str, Any] = {
        "brier": None,
        "calibracao": None,
        "quantis_probabilidade": None,
    }
    if probs is not None:
        probabilidades_metricas = {
            "brier": float(np.mean((probs - y) ** 2)),
            "calibracao": _calibracao_probabilidades(y, probs),
            "quantis_probabilidade": _distribuicao_probabilidades(probs),
        }
    return {
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
        "far": matriz.far,
        "frr": matriz.frr,
        "acuracia": matriz.acuracia,
        "precisao": matriz.precisao,
        "recall": matriz.recall,
        "f1": matriz.f1,
        "auc": auc,
        "eer": _eer(y, scores),
        **probabilidades_metricas,
    }


def _probabilidade_classe_1(estimador: Any, X: np.ndarray) -> np.ndarray:
    probabilidades = np.asarray(estimador.predict_proba(X), dtype=np.float64)
    classes = np.asarray(estimador.classes_)
    indices = np.flatnonzero(classes == 1)
    if (
        probabilidades.ndim != 2
        or probabilidades.shape[0] != X.shape[0]
        or indices.size != 1
    ):
        raise ValueError("O estimador não produziu escores alinhados para a classe 1.")
    resultado = probabilidades[:, int(indices[0])]
    if not np.isfinite(resultado).all():
        raise ValueError("O estimador produziu escores não finitos.")
    return resultado


def _medir_inferencia(
    estimador: Any, X: np.ndarray, *, baseline: bool = False
) -> tuple[np.ndarray, float]:
    def inferir() -> np.ndarray:
        if baseline:
            return np.negative(X[:, 0])
        return _probabilidade_classe_1(estimador, X)

    scores = inferir()  # aquecimento
    tempos: list[float] = []
    for _ in range(REPETICOES_TEMPO):
        inicio = perf_counter()
        scores = inferir()
        tempos.append(perf_counter() - inicio)
    return scores, float(np.median(tempos))


def _para_bootstrap(pares: ParesEtapa1, escores: np.ndarray) -> Pares:
    return Pares(
        conjunto=pares.conjunto,
        imagem_a=pares.imagem_a,
        imagem_b=pares.imagem_b,
        identidade_a=pares.identidade_a,
        identidade_b=pares.identidade_b,
        # The Etapa 1 bootstrap accepts ``distance <= threshold``. Negating
        # each method's score preserves its ``score >= threshold`` decision.
        distancia=-np.asarray(escores, dtype=np.float64),
        rotulo=pares.rotulo,
        impostores_possiveis=int(np.count_nonzero(pares.rotulo == 0)),
    )


def _diagnostico_gaussiano(
    pares: ParesEtapa1,
) -> dict[str, DiagnosticoClasse]:
    diagnostico: dict[str, DiagnosticoClasse] = {}
    nomes = {1: "mesma_identidade", 0: "identidades_diferentes"}
    for rotulo, nome in nomes.items():
        valores = np.asarray(pares.distancia[pares.rotulo == rotulo], dtype=np.float64)
        if not valores.size:
            diagnostico[nome] = {"quantidade": 0.0}
            continue
        media = float(np.mean(valores))
        desvio = float(np.std(valores))
        assimetria_bruta = skew(valores, bias=False) if valores.size > 2 else 0.0
        assimetria = (
            float(assimetria_bruta)
            if np.isfinite(assimetria_bruta)
            else None
        )
        curtose_bruta = (
            kurtosis(valores, fisher=True, bias=False) if valores.size > 3 else 0.0
        )
        curtose_valor = float(curtose_bruta) if np.isfinite(curtose_bruta) else None
        quantis_empiricos = {
            f"q{int(q * 100):02d}": float(np.quantile(valores, q)) for q in QUANTIS
        }
        quantis_gaussianos = {
            f"q{int(q * 100):02d}": float(media + desvio * norm.ppf(q))
            for q in QUANTIS
        }
        diagnostico[nome] = {
            "quantidade": float(valores.size),
            "media": media,
            "desvio_padrao": desvio,
            "assimetria": assimetria,
            "curtose_excesso": curtose_valor,
            "quantis_empiricos": quantis_empiricos,
            "quantis_gaussianos": quantis_gaussianos,
        }
    return diagnostico


def avaliar_no_teste(
    pares: ParesEtapa1,
    modelos: Mapping[str, ModeloSelecionado],
    *,
    seed: int = 42,
    replicas: int = 1000,
) -> ResultadoEtapa2:
    """Avalia uma única vez os modelos congelados no teste independente."""
    if pares.conjunto != "teste":
        raise ValueError("A avaliação final aceita somente o subconjunto teste.")
    if replicas <= 0:
        raise ValueError("O número de réplicas do bootstrap deve ser positivo.")
    from scripts.experimento_classificacao_binaria import validar_pares

    validar_pares(pares)
    y = np.asarray(pares.rotulo, dtype=np.int8)
    distancias = np.asarray(pares.distancia, dtype=np.float64)
    X = distancias.reshape(-1, 1)
    scores_por_metodo: dict[str, np.ndarray] = {}
    probabilidades_por_metodo: dict[str, np.ndarray | None] = {}
    tempos_por_metodo: dict[str, float] = {}
    tempos_treino: dict[str, float | None] = {}
    limiares: dict[str, float] = {
        "M0": -0.30,
        "M1": -LIMIAR_M1_ETAPA1,
    }

    score_m0, tempo_m0 = _medir_inferencia(None, X, baseline=True)
    scores_por_metodo["M0"] = score_m0
    probabilidades_por_metodo["M0"] = None
    tempos_por_metodo["M0"] = tempo_m0
    tempos_treino["M0"] = None
    score_m1, tempo_m1 = _medir_inferencia(None, X, baseline=True)
    scores_por_metodo["M1"] = score_m1
    probabilidades_por_metodo["M1"] = None
    tempos_por_metodo["M1"] = tempo_m1
    tempos_treino["M1"] = None

    for nome in ("M2", "M3", "M4"):
        modelo = modelos.get(nome)
        if modelo is None:
            continue
        if modelo.nome != nome:
            raise ValueError(f"Modelo incompatível recebido para {nome}.")
        scores, tempo = _medir_inferencia(modelo.estimador, X)
        scores_por_metodo[nome] = scores
        probabilidades_por_metodo[nome] = scores
        tempos_por_metodo[nome] = tempo
        tempos_treino[nome] = modelo.tempo_treino_s
        limiares[nome] = modelo.limiar_score

    pares_bootstrap = _para_bootstrap(pares, scores_por_metodo["M0"])
    # O bootstrap da Etapa 1 recebe limiares de distância (distância menor
    # aceita); os classificadores usam score maior para a classe positiva.
    limiares_distancia = {
        nome: -limiar_score for nome, limiar_score in limiares.items()
    }
    bootstrap = {
        nome: bootstrap_por_identidade(
            _para_bootstrap(pares, scores),
            {nome: limiares_distancia[nome]},
            replicas,
            seed,
        )[nome]
        for nome, scores in scores_por_metodo.items()
    }
    n_identidades = int(
        np.unique(np.concatenate([pares.identidade_a, pares.identidade_b])).size
    )
    n_pares_identidades = pares_bootstrap.pares_de_identidades_impostores()
    resultados: dict[str, ResultadoMetodo] = {}
    far_base, frr_base = bootstrap["M0"]
    for nome, scores in scores_por_metodo.items():
        limiar = limiares[nome]
        probabilidades = probabilidades_por_metodo[nome]
        metricas = avaliar_escores(
            y, scores, limiar, probabilidades=probabilidades
        )
        far_replicas, frr_replicas = bootstrap[nome]
        ic_far = intervalo_95(far_replicas)
        ic_frr = intervalo_95(frr_replicas)
        far = metricas["far"]
        far_regra_tres = (
            3.0 / n_pares_identidades
            if metricas["fp"] == 0 and n_pares_identidades > 0
            else None
        )
        demonstrado = bool(
            far is not None
            and far <= TETO_FAR_PADRAO
            and np.isfinite(ic_far.superior)
            and ic_far.superior <= TETO_FAR_PADRAO
            and (far_regra_tres is None or far_regra_tres <= TETO_FAR_PADRAO)
        )
        metricas["far_maximo_regra_do_tres"] = far_regra_tres
        metricas["far_teto_demonstrado"] = demonstrado
        if np.unique(y).size == 2:
            fpr, tpr, _ = roc_curve(y, scores, drop_intermediate=False)
        else:
            fpr = np.array([], dtype=np.float64)
            tpr = np.array([], dtype=np.float64)
        if nome == "M0":
            delta_far = None
            delta_frr = None
        else:
            delta_far = intervalo_95(far_replicas - far_base)
            delta_frr = intervalo_95(frr_replicas - frr_base)
        resultado = ResultadoMetodo(
            nome=nome,
            limiar_score=limiar,
            metricas=metricas,
            escores=scores,
            probabilidades=probabilidades,
            fpr=np.asarray(fpr, dtype=np.float64),
            tpr=np.asarray(tpr, dtype=np.float64),
            ic_far=ic_far,
            ic_frr=ic_frr,
            pares_de_identidades_impostoras=n_pares_identidades,
            atende_teto_far=demonstrado,
            tempo_treino_s=tempos_treino[nome],
            tempo_inferencia_s=tempos_por_metodo[nome],
            tempo_inferencia_por_par_s=tempos_por_metodo[nome] / y.size,
            diferenca_ic_far_vs_m0=delta_far,
            diferenca_ic_frr_vs_m0=delta_frr,
            calibracao=metricas["calibracao"],
            distribuicao_probabilidades=metricas["quantis_probabilidade"],
        )
        resultados[nome] = resultado

    indisponiveis = {
        nome: "sem configuração treinada com limiar elegível na validação"
        for nome in ("M2", "M3", "M4")
        if nome not in modelos
    }
    modelo_arvore = modelos.get("M4")
    parametros_arvore = (
        {
            "profundidade": int(modelo_arvore.estimador.get_depth()),
            "folhas": int(modelo_arvore.estimador.get_n_leaves()),
            "parametros": modelo_arvore.parametros,
        }
        if modelo_arvore is not None
        else None
    )
    diagnostico = _diagnostico_gaussiano(pares)
    return ResultadoEtapa2(
        conjunto=pares.conjunto,
        seed=seed,
        replicas_bootstrap=replicas,
        quantidade_pares=int(y.size),
        quantidade_identidades=n_identidades,
        rotulos=y,
        distancias=distancias,
        metodos=resultados,
        indisponiveis=indisponiveis,
        diagnostico_gaussian_nb=diagnostico,
        parametros_arvore=parametros_arvore,
        arvore=(modelo_arvore.estimador if modelo_arvore is not None else None),
    )


def _intervalo_json(intervalo: Intervalo | None) -> dict[str, float] | None:
    if (
        intervalo is None
        or not np.isfinite(intervalo.inferior)
        or not np.isfinite(intervalo.superior)
    ):
        return None
    return asdict(intervalo)


def resumo_publicavel(resultado: ResultadoEtapa2) -> dict[str, Any]:
    """Retorna somente contagens agregadas e métricas, sem arrays ou IDs."""
    metodos: dict[str, dict[str, Any]] = {}
    for nome, metodo in resultado.metodos.items():
        metodos[nome] = {
            "limiar_score": metodo.limiar_score,
            "metricas": metodo.metricas,
            "ic95_far": _intervalo_json(metodo.ic_far),
            "ic95_frr": _intervalo_json(metodo.ic_frr),
            "pares_de_identidades_impostoras": metodo.pares_de_identidades_impostoras,
            "atende_teto_far": metodo.atende_teto_far,
            "tempo_treino_s": metodo.tempo_treino_s,
            "tempo_inferencia_s": metodo.tempo_inferencia_s,
            "tempo_inferencia_por_par_s": metodo.tempo_inferencia_por_par_s,
            "diferenca_ic95_far_vs_m0": _intervalo_json(metodo.diferenca_ic_far_vs_m0),
            "diferenca_ic95_frr_vs_m0": _intervalo_json(metodo.diferenca_ic_frr_vs_m0),
        }
    return {
        "conjunto": resultado.conjunto,
        "seed_bootstrap": resultado.seed,
        "replicas_bootstrap": resultado.replicas_bootstrap,
        "quantidade_pares": resultado.quantidade_pares,
        "quantidade_identidades": resultado.quantidade_identidades,
        "indisponiveis": resultado.indisponiveis,
        "diagnostico_gaussian_nb": resultado.diagnostico_gaussian_nb,
        "parametros_arvore": resultado.parametros_arvore,
        "metodos": metodos,
    }


def salvar_resultado(resultado: ResultadoEtapa2, arquivo: Path) -> Path:
    destino = Path(arquivo)
    destino.parent.mkdir(parents=True, exist_ok=True)
    conteudo = json.dumps(
        resumo_publicavel(resultado), ensure_ascii=False, indent=2, allow_nan=False
    )
    destino.write_text(conteudo + "\n", encoding="utf-8")
    return destino
