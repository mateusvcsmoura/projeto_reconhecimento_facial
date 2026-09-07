"""Configuracao do pytest-bdd.

Os cenarios sao escritos em portugues (# language: pt). Os passos ficam nos
modulos test_*_steps.py deste diretorio.

Estes cenarios nao sao documentacao decorativa: falham de verdade quando o
comportamento muda.
"""

from __future__ import annotations

from pathlib import Path

FEATURES = Path(__file__).parent
