"""Metricas de avaliacao de sistema biometrico.

Funcoes puras sobre distancias. Nao importam DeepFace nem banco -- e por
isso a matematica pode ser verificada por teste neste ambiente, mesmo sem
o modelo instalado.

Vocabulario (ISO/IEC 19795):

  * par GENUINO   -- duas imagens da MESMA pessoa
  * par IMPOSTOR  -- duas imagens de pessoas DIFERENTES
  * FAR (False Acceptance Rate)  -- impostores aceitos / total de impostores.
    E o erro que importa aqui: registra a presenca da pessoa errada.
  * FRR (False Rejection Rate)   -- genuinos recusados / total de genuinos.
    Incomoda o aluno, mas nao corrompe o registro.
  * EER (Equal Error Rate)       -- ponto onde FAR = FRR. Serve para
    comparar modelos; NAO e necessariamente o limiar que se deve usar.

Um sistema decide "mesma pessoa" quando a distancia <= limiar. Portanto:
aumentar o limiar aumenta o FAR e diminui o FRR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class PontoDaCurva:
    limiar: float
    far: float
    frr: float

    @property
    def acuracia_balanceada(self) -> float:
        return 1.0 - (self.far + self.frr) / 2.0


def far_frr(
    genuinas: np.ndarray, impostoras: np.ndarray, limiar: float
) -> tuple[float, float]:
    """FAR e FRR para um limiar especifico."""
    if genuinas.size == 0 or impostoras.size == 0:
        raise ValueError("Sao necessarios pares genuinos E impostores.")

    far = float(np.mean(impostoras <= limiar))
    frr = float(np.mean(genuinas > limiar))
    return far, frr


def curva(
    genuinas: np.ndarray, impostoras: np.ndarray, passos: int = 200
) -> list[PontoDaCurva]:
    """Varre limiares entre o minimo e o maximo observados."""
    todas = np.concatenate([genuinas, impostoras])
    limiares = np.linspace(float(todas.min()), float(todas.max()), passos)

    pontos = []
    for limiar in limiares:
        far, frr = far_frr(genuinas, impostoras, float(limiar))
        pontos.append(PontoDaCurva(limiar=float(limiar), far=far, frr=frr))
    return pontos


def eer(genuinas: np.ndarray, impostoras: np.ndarray) -> PontoDaCurva:
    """Ponto de menor diferenca entre FAR e FRR."""
    pontos = curva(genuinas, impostoras)
    return min(pontos, key=lambda p: abs(p.far - p.frr))


def limiar_para_far_maximo(
    genuinas: np.ndarray, impostoras: np.ndarray, far_maximo: float
) -> PontoDaCurva | None:
    """Maior limiar cujo FAR ainda respeita o teto pedido.

    Para controle de presenca este e o criterio util: fixa-se o quanto de
    fraude se tolera e aceita-se o FRR que vier. Recusar um aluno legitimo
    custa uma segunda tentativa; aceitar o impostor corrompe o registro.

    Exato, sem grade: o teto admite no maximo k = floor(teto * n) impostores
    aceitos, entao o limiar precisa ficar abaixo do (k+1)-esimo impostor
    mais proximo -- a "barreira". O supremo (a propria barreira) nao serve,
    porque a aceitaria; qualquer valor entre a ultima distancia observada
    abaixo dela e a barreira da o mesmo FAR e FRR nestes dados -- o menor
    FRR possivel sob o teto. Adota-se o ponto medio desse intervalo, como o
    corte de uma arvore de decisao.

    None: nenhuma distancia observada respeita o teto (so "recusar tudo").
    """
    if genuinas.size == 0 or impostoras.size == 0:
        raise ValueError("Sao necessarios pares genuinos E impostores.")
    if not 0.0 <= far_maximo <= 1.0:
        raise ValueError(f"O teto de FAR deve estar em [0, 1]; recebido {far_maximo}.")

    genuinas = np.asarray(genuinas, dtype=np.float64)
    impostoras = np.sort(np.asarray(impostoras, dtype=np.float64))
    todas = np.concatenate([genuinas, impostoras])

    # Tolerancia: 0.001 * 3000 da 3.0000000000000004 em ponto flutuante.
    aceitos_no_maximo = int(np.floor(far_maximo * impostoras.size + 1e-9))
    if aceitos_no_maximo >= impostoras.size:
        limiar = float(todas.max())
    else:
        barreira = impostoras[aceitos_no_maximo]
        abaixo = todas[todas < barreira]
        if abaixo.size == 0:
            return None
        limiar = float((abaixo.max() + barreira) / 2.0)

    far, frr = far_frr(genuinas, impostoras, limiar)
    return PontoDaCurva(limiar=limiar, far=far, frr=frr)


def area_sob_a_curva(genuinas: np.ndarray, impostoras: np.ndarray) -> float:
    """AUC pela estatistica U de Mann-Whitney.

    Probabilidade de um par genuino ter distancia MENOR que a de um par
    impostor sorteado ao acaso. 1.0 = separacao perfeita; 0.5 = aleatorio.

    Por busca binaria, O(n log n): a comparacao todos-contra-todos alocaria
    genuinos x impostores booleanos -- gigabytes num dataset publico.
    """
    if genuinas.size == 0 or impostoras.size == 0:
        raise ValueError("Sao necessarios pares genuinos E impostores.")

    ordenadas = np.sort(impostoras)
    acima = np.searchsorted(ordenadas, genuinas, side="right")
    empates = acima - np.searchsorted(ordenadas, genuinas, side="left")
    maiores = ordenadas.size - acima
    total = genuinas.size * ordenadas.size
    return float((maiores.sum() + 0.5 * empates.sum()) / total)


def roc(
    genuinas: np.ndarray, impostoras: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Curva ROC exata: limiar, FAR e TAR (= 1 - FRR) em cada distancia observada.

    Comeca em (0, 0) -- limiar -inf, recusa tudo -- e termina em (1, 1).
    Trocar o limiar so escolhe um ponto desta curva; nao muda a curva nem a
    AUC.
    """
    limiares = np.unique(np.concatenate([genuinas, impostoras]))
    far = np.searchsorted(np.sort(impostoras), limiares, side="right") / impostoras.size
    tar = np.searchsorted(np.sort(genuinas), limiares, side="right") / genuinas.size
    return (
        np.concatenate([[-np.inf], limiares]),
        np.concatenate([[0.0], far]),
        np.concatenate([[0.0], tar]),
    )


@dataclass(frozen=True, slots=True)
class MatrizDeConfusao:
    """Contagens num limiar. Positivo = "mesma pessoa" (aceitar).

    Metricas sem denominador devolvem None em vez de inventar um numero.
    """

    tp: int  # genuino aceito
    fn: int  # genuino recusado
    fp: int  # impostor aceito -- presenca indevida
    tn: int  # impostor recusado

    @staticmethod
    def _razao(numerador: int, denominador: int) -> float | None:
        return numerador / denominador if denominador else None

    @property
    def far(self) -> float | None:
        return self._razao(self.fp, self.fp + self.tn)

    @property
    def frr(self) -> float | None:
        return self._razao(self.fn, self.fn + self.tp)

    @property
    def acuracia(self) -> float | None:
        return self._razao(self.tp + self.tn, self.tp + self.fn + self.fp + self.tn)

    @property
    def precisao(self) -> float | None:
        return self._razao(self.tp, self.tp + self.fp)

    @property
    def recall(self) -> float | None:
        return self._razao(self.tp, self.tp + self.fn)

    @property
    def f1(self) -> float | None:
        p, r = self.precisao, self.recall
        if p is None or r is None:
            return None
        # p = r = 0: media harmonica tende a 0 (mesma convencao do sklearn).
        return 2 * p * r / (p + r) if p + r else 0.0


def matriz_de_confusao(
    genuinas: np.ndarray, impostoras: np.ndarray, limiar: float
) -> MatrizDeConfusao:
    tp = int(np.sum(genuinas <= limiar))
    fp = int(np.sum(impostoras <= limiar))
    return MatrizDeConfusao(
        tp=tp, fn=int(genuinas.size) - tp, fp=fp, tn=int(impostoras.size) - fp
    )
