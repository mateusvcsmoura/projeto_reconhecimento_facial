"""Coleta de entrada do operador.

Sem regra de negocio e sem acesso a banco: so le, normaliza e devolve. A
funcao de leitura e injetada para que isto seja testavel sem stdin.
"""

from __future__ import annotations

from collections.abc import Callable

Leitor = Callable[[str], str]


def perguntar(rotulo: str, ler: Leitor = input) -> str:
    return ler(rotulo).strip()


def perguntar_opcao(opcoes: set[str], ler: Leitor = input) -> str | None:
    """Devolve a opcao escolhida, ou None se nao for uma opcao valida."""
    escolha = perguntar("Escolha: ", ler)
    return escolha if escolha in opcoes else None
