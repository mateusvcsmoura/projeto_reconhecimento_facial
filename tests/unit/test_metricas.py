"""Fase 7 -- metricas de avaliacao biometrica.

A inferencia exige DeepFace, mas a MATEMATICA nao. Estes testes verificam
que FAR, FRR, EER e AUC estao corretos -- porque um numero errado aqui
levaria a calibrar o FACE_THRESHOLD no valor errado, e a conclusao da
avaliacao valeria menos que nenhuma avaliacao.
"""

from __future__ import annotations

import numpy as np
import pytest

from scripts.metricas import (
    area_sob_a_curva,
    curva,
    eer,
    far_frr,
    limiar_para_far_maximo,
)

# Separacao perfeita: genuinos proximos, impostores distantes.
GENUINAS = np.array([0.05, 0.10, 0.15, 0.20])
IMPOSTORAS = np.array([0.80, 0.90, 1.00, 1.10])


def test_limiar_generoso_aceita_todos_os_genuinos() -> None:
    far, frr = far_frr(GENUINAS, IMPOSTORAS, limiar=0.50)
    assert frr == 0.0
    assert far == 0.0


def test_limiar_apertado_recusa_genuinos() -> None:
    """FRR alto: o aluno legitimo tenta de novo."""
    far, frr = far_frr(GENUINAS, IMPOSTORAS, limiar=0.01)
    assert frr == 1.0
    assert far == 0.0


def test_limiar_frouxo_aceita_impostores() -> None:
    """FAR alto: a presenca vai para a pessoa errada."""
    far, frr = far_frr(GENUINAS, IMPOSTORAS, limiar=2.0)
    assert far == 1.0
    assert frr == 0.0


def test_far_cresce_e_frr_cai_conforme_o_limiar_aumenta() -> None:
    pontos = curva(GENUINAS, IMPOSTORAS, passos=50)
    fars = [p.far for p in pontos]
    frrs = [p.frr for p in pontos]

    assert fars == sorted(fars)
    assert frrs == sorted(frrs, reverse=True)


def test_far_e_a_fracao_de_impostores_aceitos() -> None:
    # limiar 0.85 aceita 1 dos 4 impostores (0.80)
    far, _ = far_frr(GENUINAS, IMPOSTORAS, limiar=0.85)
    assert far == pytest.approx(0.25)


def test_frr_e_a_fracao_de_genuinos_recusados() -> None:
    # limiar 0.12 recusa 2 dos 4 genuinos (0.15 e 0.20)
    _, frr = far_frr(GENUINAS, IMPOSTORAS, limiar=0.12)
    assert frr == pytest.approx(0.50)


def test_eer_encontra_o_ponto_de_equilibrio() -> None:
    ponto = eer(GENUINAS, IMPOSTORAS)
    assert ponto.far == pytest.approx(ponto.frr, abs=0.26)


def test_eer_e_zero_quando_a_separacao_e_perfeita() -> None:
    ponto = eer(GENUINAS, IMPOSTORAS)
    assert ponto.far == 0.0
    assert ponto.frr == 0.0


def test_auc_maxima_com_separacao_perfeita() -> None:
    assert area_sob_a_curva(GENUINAS, IMPOSTORAS) == pytest.approx(1.0)


def test_auc_meio_a_meio_quando_as_distribuicoes_coincidem() -> None:
    """Distribuicoes identicas = decisao no chute."""
    iguais = np.array([0.5, 0.5, 0.5, 0.5])
    assert area_sob_a_curva(iguais, iguais.copy()) == pytest.approx(0.5)


def test_auc_reflete_sobreposicao_parcial() -> None:
    genuinas = np.array([0.10, 0.60])
    impostoras = np.array([0.50, 0.90])
    # 3 dos 4 pares tem genuina < impostora
    assert area_sob_a_curva(genuinas, impostoras) == pytest.approx(0.75)


def test_teto_de_far_devolve_o_maior_limiar_seguro() -> None:
    """Fixado o quanto de fraude se tolera, quer-se o menor FRR possivel."""
    ponto = limiar_para_far_maximo(GENUINAS, IMPOSTORAS, far_maximo=0.0)

    assert ponto is not None
    assert ponto.far == 0.0
    assert ponto.limiar < IMPOSTORAS.min()
    assert ponto.limiar > GENUINAS.max()


def test_teto_de_far_impossivel_devolve_none() -> None:
    """Se todo limiar aceita algum impostor, e melhor dizer que nao da."""
    sobrepostas_g = np.array([0.5, 0.5])
    sobrepostas_i = np.array([0.1, 0.1])

    assert limiar_para_far_maximo(sobrepostas_g, sobrepostas_i, 0.0) is None


def test_acuracia_balanceada_penaliza_os_dois_erros() -> None:
    pontos = curva(GENUINAS, IMPOSTORAS, passos=50)
    melhor = max(pontos, key=lambda p: p.acuracia_balanceada)

    assert melhor.acuracia_balanceada == pytest.approx(1.0)


def test_conjunto_sem_impostores_e_recusado() -> None:
    with pytest.raises(ValueError, match="genuinos E impostores"):
        far_frr(GENUINAS, np.array([]), 0.3)


def test_conjunto_sem_genuinos_e_recusado() -> None:
    with pytest.raises(ValueError, match="genuinos E impostores"):
        area_sob_a_curva(np.array([]), IMPOSTORAS)
