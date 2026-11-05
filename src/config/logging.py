"""Configuracao do logging da aplicacao.

Substitui o print() como mecanismo de diagnostico
nas camadas internas. O print() continua existindo,
mas apenas na camada de apresentacao, para falar com o operador.

Regra de privacidade: log de rotina identifica aluno pelo id interno,
nunca por nome. Nunca registrar imagem, embedding ou credencial.
"""

from __future__ import annotations

import logging

FORMATO = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def configurar_logging(nivel: str = "INFO") -> None:
    """Configura o logging raiz. Idempotente."""
    raiz = logging.getLogger()
    if raiz.handlers:
        raiz.setLevel(nivel)
        return

    logging.basicConfig(level=nivel, format=FORMATO, datefmt="%H:%M:%S")

    # O SQLAlchemy fala demais em INFO e polui o diagnostico da aplicacao.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
