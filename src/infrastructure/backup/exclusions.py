"""Registro privado append-only para reaplicar exclusÃµes em restores antigos."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from src.infrastructure.workers.singleton_process_lock import SingletonProcessLock

TipoExclusao = Literal["aluno"]


@dataclass(frozen=True, slots=True)
class Exclusao:
    evento_id: str
    tipo: TipoExclusao
    identificador: int
    estado: Literal["pendente", "confirmada", "cancelada"]


class RegistroExclusoes:
    """Guarda apenas IDs estritamente necessÃ¡rios, nunca nomes, imagens ou vetores."""

    def __init__(self, caminho: Path, *, project_root: Path) -> None:
        self._original = caminho.expanduser()
        self._path = self._original.resolve()
        self._root = project_root.resolve()
        if not self._path.is_absolute() or self._original.is_symlink():
            raise ValueError(
                "O registro de exclusÃµes deve ser caminho absoluto regular."
            )
        if self._path.is_relative_to(self._root):
            raise ValueError(
                "O registro de exclusÃµes deve ficar fora do repositÃ³rio."
            )
        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self._path.parent.chmod(0o700)

    def registrar_pendente(self, tipo: TipoExclusao, identificador: int) -> str:
        self._validar(tipo, identificador)
        evento_id = uuid4().hex
        self._append(evento_id, tipo, identificador, "pendente")
        return evento_id

    def confirmar(self, evento_id: str, tipo: TipoExclusao, identificador: int) -> None:
        self._validar(tipo, identificador)
        self._append(evento_id, tipo, identificador, "confirmada")

    def cancelar(self, evento_id: str, tipo: TipoExclusao, identificador: int) -> None:
        self._validar(tipo, identificador)
        self._append(evento_id, tipo, identificador, "cancelada")

    def exclusoes_a_reaplicar(self) -> tuple[Exclusao, ...]:
        estados: dict[str, Exclusao] = {}
        anterior = "0" * 64
        if not self._path.exists():
            return ()
        with self._lock():
            try:
                linhas = self._path.read_text(encoding="utf-8").splitlines()
                for linha in linhas:
                    evento = json.loads(linha)
                    assinatura = evento.pop("hash")
                    if evento.get("anterior") != anterior:
                        raise ValueError("A cadeia do registro de exclusÃµes diverge.")
                    calculado = _hash(evento)
                    if assinatura != calculado:
                        raise ValueError(
                            "A assinatura do registro de exclusÃµes diverge."
                        )
                    anterior = assinatura
                    exclusao = Exclusao(
                        evento_id=str(evento["evento_id"]),
                        tipo=evento["tipo"],
                        identificador=int(evento["identificador"]),
                        estado=evento["estado"],
                    )
                    estados[exclusao.evento_id] = exclusao
            except (
                OSError,
                KeyError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ) as erro:
                raise RuntimeError(
                    "O registro de exclusÃµes estÃ¡ invÃ¡lido."
                ) from erro
        return tuple(
            item
            for item in estados.values()
            if item.estado in {"pendente", "confirmada"}
        )

    def _append(
        self,
        evento_id: str,
        tipo: TipoExclusao,
        identificador: int,
        estado: Literal["pendente", "confirmada", "cancelada"],
    ) -> None:
        if len(evento_id) != 32 or any(
            char not in "0123456789abcdef" for char in evento_id
        ):
            raise ValueError("Identificador do evento de exclusÃ£o invÃ¡lido.")
        with self._lock():
            anterior = "0" * 64
            if self._path.exists():
                for linha in self._path.read_text(encoding="utf-8").splitlines():
                    registro = json.loads(linha)
                    assinatura = registro.pop("hash")
                    if registro.get("anterior") != anterior or assinatura != _hash(
                        registro
                    ):
                        raise RuntimeError("Registro de exclusÃµes invÃ¡lido.")
                    anterior = str(assinatura)
            evento: dict[str, object] = {
                "evento_id": evento_id,
                "tipo": tipo,
                "identificador": identificador,
                "estado": estado,
                "instante": datetime.now(UTC).isoformat(),
                "anterior": anterior,
            }
            evento["hash"] = _hash(evento)
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
            fd = os.open(self._path, flags, 0o600)
            try:
                with os.fdopen(fd, "a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(evento, sort_keys=True, separators=(",", ":")) + "\n"
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
            finally:
                if os.name == "posix":
                    self._path.chmod(0o600)

    @contextmanager
    def _lock(self) -> Iterator[None]:
        lock = SingletonProcessLock(self._path.with_suffix(self._path.suffix + ".lock"))
        with lock:
            if not lock.adquirido:
                raise TimeoutError("Registro de exclusÃµes em uso.")
            yield

    @staticmethod
    def _validar(tipo: str, identificador: int) -> None:
        if tipo != "aluno" or isinstance(identificador, bool) or identificador <= 0:
            raise ValueError("ExclusÃ£o invÃ¡lida.")


def _hash(evento: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(evento, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
