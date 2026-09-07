"""Traducao da distancia em algo que o operador entenda.

A distancia cosseno e a grandeza certa para decidir, e a errada para
mostrar: 0.087 nao diz nada a quem opera o sistema.

ATENCAO -- honestidade sobre o que este numero e:

  * NAO e probabilidade de ser a pessoa certa;
  * NAO sai de calibracao estatistica;
  * e uma leitura linear de "quao longe do limiar ficou a decisao".

Serve para o operador perceber que um reconhecimento em 12% e fraco e
merece uma segunda olhada, enquanto um em 95% e confortavel. Trocar isto
por probabilidade de verdade exigiria a calibracao da Fase 7 sobre dados
reais.
"""

from __future__ import annotations

from src.presentation.cli.teclas import BRANCO, VERDE, VERMELHO

# Abaixo disto o operador deveria conferir manualmente antes de registrar.
CONFIANCA_BAIXA = 0.40


def confianca(distancia: float, limiar: float) -> float:
    """Fracao de 0 a 1: 1.0 e distancia zero; 0.0 e exatamente no limiar."""
    if limiar <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - distancia / limiar))


def percentual(distancia: float, limiar: float) -> int:
    return round(confianca(distancia, limiar) * 100)


def cor_por_confianca(valor: float) -> tuple[int, int, int]:
    """Verde quando confortavel, branco quando fraco."""
    return VERDE if valor >= CONFIANCA_BAIXA else BRANCO


def rotulo_de_estado(
    nome: str | None, distancia: float | None, limiar: float
) -> tuple[str, tuple[int, int, int]]:
    """Texto e cor do overlay, conforme o estado do reconhecimento."""
    if nome is None or distancia is None:
        return "Rosto nao reconhecido", VERMELHO

    valor = confianca(distancia, limiar)
    texto = f"{nome} -- {percentual(distancia, limiar)}%"
    if valor < CONFIANCA_BAIXA:
        texto += " (confianca baixa)"
    return texto, cor_por_confianca(valor)
