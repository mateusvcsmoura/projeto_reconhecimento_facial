"""Remoção segura de imagens legadas sem importar OpenCV no runtime web."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath


class LegacyImageRemover:
    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()

    def remover(self, nome_arquivo: str) -> None:
        caminho = Path(nome_arquivo)
        windows = PureWindowsPath(nome_arquivo)
        if (
            not nome_arquivo
            or caminho.is_absolute()
            or windows.is_absolute()
            or windows.drive
            or windows.root
            or caminho.name != nome_arquivo
            or nome_arquivo in {".", ".."}
        ):
            raise ValueError("O nome da imagem legada deve ser relativo e seguro.")
        destino = (self._root / caminho).resolve()
        try:
            destino.relative_to(self._root)
        except ValueError as erro:
            raise ValueError("A imagem legada escapou da raiz configurada.") from erro
        destino.unlink(missing_ok=True)
