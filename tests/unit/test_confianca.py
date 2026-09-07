"""Fase 8 -- traducao da distancia em confianca legivel."""

from __future__ import annotations

import pytest

from src.presentation.cli.confianca import (
    CONFIANCA_BAIXA,
    confianca,
    cor_por_confianca,
    percentual,
    rotulo_de_estado,
)
from src.presentation.cli.teclas import BRANCO, VERDE, VERMELHO

LIMIAR = 0.30


def test_distancia_zero_e_confianca_maxima() -> None:
    assert confianca(0.0, LIMIAR) == pytest.approx(1.0)


def test_distancia_no_limiar_e_confianca_zero() -> None:
    assert confianca(LIMIAR, LIMIAR) == pytest.approx(0.0)


def test_distancia_alem_do_limiar_nao_fica_negativa() -> None:
    assert confianca(1.5, LIMIAR) == 0.0


def test_distancia_negativa_nao_passa_de_um() -> None:
    """Ruido numerico nao pode virar 120% na tela."""
    assert confianca(-0.01, LIMIAR) == 1.0


def test_confianca_cai_conforme_a_distancia_cresce() -> None:
    valores = [confianca(d, LIMIAR) for d in (0.0, 0.05, 0.15, 0.25)]
    assert valores == sorted(valores, reverse=True)


def test_limiar_invalido_devolve_zero_em_vez_de_dividir_por_zero() -> None:
    assert confianca(0.1, 0.0) == 0.0


def test_percentual_e_inteiro_arredondado() -> None:
    assert percentual(0.03, LIMIAR) == 90


def test_confianca_confortavel_fica_verde() -> None:
    assert cor_por_confianca(0.9) == VERDE


def test_confianca_fraca_fica_branca() -> None:
    assert cor_por_confianca(CONFIANCA_BAIXA - 0.01) == BRANCO


def test_rotulo_sem_reconhecimento_e_vermelho() -> None:
    texto, cor = rotulo_de_estado(None, None, LIMIAR)

    assert texto == "Rosto nao reconhecido"
    assert cor == VERMELHO


def test_rotulo_mostra_nome_e_percentual() -> None:
    texto, cor = rotulo_de_estado("Ana Souza", 0.03, LIMIAR)

    assert "Ana Souza" in texto
    assert "90%" in texto
    assert cor == VERDE


def test_rotulo_avisa_quando_a_confianca_e_baixa() -> None:
    """O operador precisa saber que aquele match merece conferencia."""
    texto, cor = rotulo_de_estado("Ana Souza", 0.28, LIMIAR)

    assert "confianca baixa" in texto
    assert cor == BRANCO


def test_rotulo_nao_expoe_a_distancia_crua() -> None:
    """0.087 nao diz nada a quem opera o sistema."""
    texto, _ = rotulo_de_estado("Ana Souza", 0.087, LIMIAR)

    assert "0.087" not in texto
