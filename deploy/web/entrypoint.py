"""Carrega segredos fornecidos por arquivo e executa o processo do container."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ARQUIVOS_DE_SEGREDO = {
    "WEB_DATABASE_URL_FILE": "WEB_DATABASE_URL",
    "WEB_SECRET_KEY_FILE": "WEB_SECRET_KEY",
    "ALEMBIC_DATABASE_URL_FILE": "ALEMBIC_DATABASE_URL",
}


def main() -> None:
    for variavel_arquivo, variavel_valor in _ARQUIVOS_DE_SEGREDO.items():
        caminho = os.environ.pop(variavel_arquivo, None)
        if caminho is None:
            continue
        try:
            valor = Path(caminho).read_text(encoding="utf-8").rstrip("\r\n")
        except OSError:
            raise SystemExit(f"Arquivo de segredo ausente para {variavel_valor}.") from None
        if not valor:
            raise SystemExit(f"Arquivo de segredo vazio para {variavel_valor}.")
        os.environ[variavel_valor] = valor

    if len(sys.argv) < 2:
        raise SystemExit("Comando do container ausente.")
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
