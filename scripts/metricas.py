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
    """
    candidatos = [p for p in curva(genuinas, impostoras) if p.far <= far_maximo]
    return max(candidatos, key=lambda p: p.limiar) if candidatos else None


def area_sob_a_curva(genuinas: np.ndarray, impostoras: np.ndarray) -> float:
    """AUC pela estatistica U de Mann-Whitney.

    Probabilidade de um par genuino ter distancia MENOR que a de um par
    impostor sorteado ao acaso. 1.0 = separacao perfeita; 0.5 = aleatorio.
    """
    if genuinas.size == 0 or impostoras.size == 0:
        raise ValueError("Sao necessarios pares genuinos E impostores.")

    comparacoes = genuinas[:, None] < impostoras[None, :]
    empates = genuinas[:, None] == impostoras[None, :]
    return float((comparacoes.sum() + 0.5 * empates.sum()) / comparacoes.size)
