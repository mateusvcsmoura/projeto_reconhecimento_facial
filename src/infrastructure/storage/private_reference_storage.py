"""Armazenamento privado de recortes web sem dependência de OpenCV."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

MAX_REFERENCE_BYTES = 10 * 1024 * 1024


class PrivateReferenceStorageLocal:
    """Grava nomes aleatórios sob uma raiz privada fora da raiz HTTP.

    A raiz deve ser configurada pelo composition root como volume privado.
    Em POSIX os arquivos/diretórios recebem permissões restritas; no Windows,
    o operador deve conceder acesso NTFS somente à identidade do serviço.
    """

    def __init__(self, raiz_privada: Path) -> None:
        self._raiz = raiz_privada.expanduser().resolve()
        self._raiz.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            self._raiz.chmod(0o700)

    def salvar(self, solicitacao_id: int, ordinal: int, recorte: bytes) -> str:
        if solicitacao_id <= 0 or ordinal not in (1, 2, 3):
            raise ValueError("Identificador/ordinal de referência inválido.")
        if not recorte or len(recorte) > MAX_REFERENCE_BYTES:
            raise ValueError("O recorte está vazio ou excede o limite de tamanho.")

        diretorio = self._raiz / str(solicitacao_id)
        diretorio.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            diretorio.chmod(0o700)
        nome = f"{ordinal}-{secrets.token_hex(24)}.bin"
        destino = (diretorio / nome).resolve()
        self._exigir_dentro_da_raiz(destino)
        try:
            with destino.open("xb") as arquivo:
                arquivo.write(recorte)
            if os.name == "posix":
                destino.chmod(0o600)
        except Exception:
            destino.unlink(missing_ok=True)
            raise
        return destino.relative_to(self._raiz).as_posix()

    def remover(self, caminho_relativo: str) -> None:
        caminho = Path(caminho_relativo)
        if caminho.is_absolute() or not caminho.parts or ".." in caminho.parts:
            raise ValueError("Caminho de referência deve ser relativo e seguro.")
        destino = (self._raiz / caminho).resolve()
        self._exigir_dentro_da_raiz(destino)
        if destino.is_file():
            destino.unlink()

    def _exigir_dentro_da_raiz(self, destino: Path) -> None:
        try:
            destino.relative_to(self._raiz)
        except ValueError as erro:
            raise ValueError(
                "O caminho da referência escapa da raiz privada."
            ) from erro
