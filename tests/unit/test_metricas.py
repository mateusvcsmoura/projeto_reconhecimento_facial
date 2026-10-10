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
    MatrizDeConfusao,
    area_sob_a_curva,
    curva,
    eer,
    far_frr,
    limiar_para_far_maximo,
    matriz_de_confusao,
    roc,
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


# -- Etapa 1: limiar exato por teto de FAR --------------------------------

SOBREPOSTAS_G = np.array([0.10, 0.20, 0.30, 0.40])
SOBREPOSTAS_I = np.array([0.25, 0.50, 0.60, 0.70])


def test_teto_de_far_e_exato_e_nao_preso_a_uma_grade() -> None:
    """Teto 25% admite 1 impostor aceito: o corte fica antes do 2o (0.50)."""
    ponto = limiar_para_far_maximo(SOBREPOSTAS_G, SOBREPOSTAS_I, 0.25)
    assert ponto is not None
    # Ponto medio entre 0.40 (ultimo valor aceitavel) e 0.50 (barreira).
    assert ponto.limiar == pytest.approx(0.45)
    assert (ponto.far, ponto.frr) == (0.25, 0.0)


def test_teto_zero_corta_antes_do_impostor_mais_proximo() -> None:
    ponto = limiar_para_far_maximo(SOBREPOSTAS_G, SOBREPOSTAS_I, 0.0)
    assert ponto is not None
    assert ponto.limiar == pytest.approx(0.225)  # entre 0.20 e 0.25
    assert (ponto.far, ponto.frr) == (0.0, 0.5)


@pytest.mark.parametrize("seed", range(20))
@pytest.mark.parametrize("teto", [0.0, 0.001, 0.01, 0.05, 0.3])
def test_limiar_respeita_o_teto_e_nenhum_maior_respeita(seed: int, teto: float) -> None:
    """O contrato: MAIOR limiar com FAR <= teto, sobre os dados observados."""
    rng = np.random.default_rng(seed)
    genuinas = np.round(rng.normal(0.3, 0.1, 300), 3)  # com empates
    impostoras = np.round(rng.normal(0.8, 0.12, 3000), 3)

    ponto = limiar_para_far_maximo(genuinas, impostoras, teto)

    assert ponto is not None
    assert ponto.far <= teto
    acima = np.concatenate([genuinas, impostoras])
    acima = acima[acima > ponto.limiar]
    if acima.size:
        far_seguinte, _ = far_frr(genuinas, impostoras, float(acima.min()))
        assert far_seguinte > teto


def test_teto_de_100_por_cento_aceita_tudo() -> None:
    ponto = limiar_para_far_maximo(SOBREPOSTAS_G, SOBREPOSTAS_I, 1.0)
    assert ponto is not None
    assert (ponto.far, ponto.frr) == (1.0, 0.0)


@pytest.mark.parametrize("teto", [-0.01, 1.01])
def test_teto_fora_de_0_a_1_e_recusado(teto: float) -> None:
    with pytest.raises(ValueError, match="teto de FAR"):
        limiar_para_far_maximo(GENUINAS, IMPOSTORAS, teto)


def test_teto_sem_impostores_e_recusado() -> None:
    with pytest.raises(ValueError, match="genuinos E impostores"):
        limiar_para_far_maximo(GENUINAS, np.array([]), 0.01)


def test_auc_bate_com_a_forca_bruta_inclusive_com_empates() -> None:
    rng = np.random.default_rng(3)
    genuinas = np.round(rng.normal(0.4, 0.2, 200), 2)
    impostoras = np.round(rng.normal(0.6, 0.2, 300), 2)
    menores = (genuinas[:, None] < impostoras[None, :]).sum()
    empates = (genuinas[:, None] == impostoras[None, :]).sum()
    esperado = (menores + 0.5 * empates) / (genuinas.size * impostoras.size)
    assert area_sob_a_curva(genuinas, impostoras) == pytest.approx(esperado)


def test_roc_vai_de_0_0_a_1_1_sem_voltar() -> None:
    limiares, far, tar = roc(SOBREPOSTAS_G, SOBREPOSTAS_I)
    assert (far[0], tar[0]) == (0.0, 0.0)
    assert (far[-1], tar[-1]) == (1.0, 1.0)
    assert np.all(np.diff(far) >= 0) and np.all(np.diff(tar) >= 0)
    assert np.all(np.diff(limiares) > 0)


# -- Etapa 1: matriz de confusao ------------------------------------------


def test_classificador_aceita_distancia_igual_ao_limiar() -> None:
    """y_hat = 1 se d <= tau: o proprio limiar ainda e 'mesma pessoa'."""
    m = matriz_de_confusao(np.array([0.30]), np.array([0.30]), limiar=0.30)
    assert (m.tp, m.fp) == (1, 1)


def test_matriz_conta_os_quatro_casos_e_deriva_as_metricas() -> None:
    m = matriz_de_confusao(SOBREPOSTAS_G, SOBREPOSTAS_I, limiar=0.35)
    # genuinos aceitos: 0.10 0.20 0.30 | impostores aceitos: 0.25
    assert (m.tp, m.fn, m.fp, m.tn) == (3, 1, 1, 3)
    assert m.far == pytest.approx(0.25)
    assert m.frr == pytest.approx(0.25)
    assert m.acuracia == pytest.approx(0.75)
    assert m.precisao == pytest.approx(0.75)
    assert m.recall == pytest.approx(0.75)
    assert m.f1 == pytest.approx(0.75)


@pytest.mark.parametrize(
    ("limiar", "esperado"),
    [(0.0, (0, 4, 0, 4)), (0.27, (2, 2, 1, 3)), (1.0, (4, 0, 4, 0))],
)
def test_matriz_muda_com_o_limiar(
    limiar: float, esperado: tuple[int, int, int, int]
) -> None:
    m = matriz_de_confusao(SOBREPOSTAS_G, SOBREPOSTAS_I, limiar)
    assert (m.tp, m.fn, m.fp, m.tn) == esperado


def test_metricas_sem_denominador_ficam_indefinidas() -> None:
    """Divisao por zero vira None, nunca um numero inventado."""
    sem_genuinos = MatrizDeConfusao(tp=0, fn=0, fp=0, tn=5)
    assert sem_genuinos.frr is None
    assert sem_genuinos.recall is None
    assert sem_genuinos.precisao is None  # nada foi aceito
    assert sem_genuinos.f1 is None
    assert sem_genuinos.far == 0.0

    vazia = MatrizDeConfusao(tp=0, fn=0, fp=0, tn=0)
    assert vazia.far is None
    assert vazia.acuracia is None


def test_f1_e_zero_quando_so_aceita_impostores() -> None:
    m = MatrizDeConfusao(tp=0, fn=3, fp=2, tn=1)
    assert (m.precisao, m.recall, m.f1) == (0.0, 0.0, 0.0)
