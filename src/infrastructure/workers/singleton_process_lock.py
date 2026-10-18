"""Lock de processo local para impedir workers simultâneos na mesma VPS."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from types import TracebackType
from typing import BinaryIO


class SingletonProcessLock:
    """Mantém um lock de arquivo durante a vida do processo worker."""

    def __init__(self, caminho: Path) -> None:
        self._caminho = caminho.expanduser().resolve()
        self._arquivo: BinaryIO | None = None
        self._adquirido = False

    def __enter__(self) -> SingletonProcessLock:
        self._caminho.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        arquivo = self._caminho.open("a+b")
        if self._caminho.stat().st_size == 0:
            arquivo.write(b"\0")
            arquivo.flush()
        arquivo.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            arquivo.close()
            return self
        self._arquivo = arquivo
        self._adquirido = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        arquivo = self._arquivo
        if arquivo is None:
            return
        try:
            arquivo.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl = importlib.import_module("fcntl")
                fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
        finally:
            arquivo.close()
            self._arquivo = None
            self._adquirido = False

    @property
    def adquirido(self) -> bool:
        return self._adquirido
