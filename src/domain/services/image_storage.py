"""Contrato de armazenamento das imagens de referencia.

O caminho absoluto gravado no banco pelo prototipo tornava a base nao
portavel: o unico registro existente apontava para o diretorio temporario
de outra maquina (problema A11). Aqui o banco guarda so o nome do arquivo,
e o storage resolve onde ele vive.
"""

from __future__ import annotations

from typing import Any, Protocol


class ImageStorage(Protocol):
    def salvar(self, nome_arquivo: str, imagem: Any) -> str:
        """Grava a imagem e devolve o nome do arquivo (relativo)."""
        ...

    def existe(self, nome_arquivo: str) -> bool: ...

    def caminho_absoluto(self, nome_arquivo: str) -> str:
        """Caminho no disco -- so para quem precisa ler o arquivo de fato."""
        ...
