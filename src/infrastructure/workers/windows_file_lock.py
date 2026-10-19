"""Acesso tipado ao lock de arquivo da API nativa do Windows."""

from __future__ import annotations

import importlib
from typing import Protocol, cast


class _Msvcrt(Protocol):
    LK_NBLCK: int
    LK_UNLCK: int

    def locking(self, fd: int, mode: int, nbytes: int) -> None: ...


def alterar_lock_windows(fd: int, *, adquirir: bool) -> None:
    """Adquire ou libera um byte de lock usando o módulo msvcrt."""
    msvcrt = cast(_Msvcrt, importlib.import_module("msvcrt"))
    codigo = msvcrt.LK_NBLCK if adquirir else msvcrt.LK_UNLCK
    msvcrt.locking(fd, codigo, 1)
