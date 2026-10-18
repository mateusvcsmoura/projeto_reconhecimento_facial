"""Contrato de armazenamento privado para recortes faciais já preparados."""

from __future__ import annotations

from typing import Protocol


class PrivateReferenceStorage(Protocol):
    def salvar(self, solicitacao_id: int, ordinal: int, recorte: bytes) -> str: ...

    def remover(self, caminho_relativo: str) -> None: ...
