"""Coordena escritas HTTP/worker e snapshots sem depender do banco de dados."""

from __future__ import annotations

import importlib
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from src.infrastructure.workers.singleton_process_lock import SingletonProcessLock
from src.infrastructure.workers.windows_file_lock import alterar_lock_windows


class ManutencaoAtiva(RuntimeError):
    """A escrita foi recusada enquanto um backup congela o ponto de dados."""


class BackupJaEmExecucao(RuntimeError):
    """Outro processo já está executando um backup nesta raiz compartilhada."""


class ManutencaoWeb:
    """Gate local compartilhado pela API, worker e ferramenta de backup.

    No Linux, mutações compartilham um lock de leitura e o snapshot adquire o
    lock exclusivo. O worker ignora o marcador de manutenção para esvaziar a
    fila antes do snapshot. No Windows, o lock de arquivo é exclusivo para
    ambos os tipos de escrita, mantendo o comportamento seguro com menor
    concorrência no ambiente de desenvolvimento.
    """

    def __init__(self, raiz: Path) -> None:
        if not raiz.is_absolute():
            raise ValueError("A raiz de manutenção deve ser absoluta.")
        self.raiz = raiz.expanduser().resolve()
        self.raiz.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            self.raiz.chmod(0o700)
        self._marker = self.raiz / ".maintenance.requested"
        self._lock_file_path = self.raiz / ".writes.lock"
        self._backup_lock_path = self.raiz / ".backup.lock"
        self._manutencao_solicitada = False

    @property
    def manutencao_ativa(self) -> bool:
        return self._marker.is_file()

    @contextmanager
    def mutacao_http(self) -> Iterator[None]:
        """Mantém lock compartilhado durante toda mutação HTTP."""
        if self.manutencao_ativa:
            raise ManutencaoAtiva
        with self._lock_de_escrita(compartilhado=True, timeout_seconds=0):
            if self.manutencao_ativa:
                raise ManutencaoAtiva
            yield

    @contextmanager
    def mutacao_worker(self) -> Iterator[bool]:
        """Permite ao worker drenar jobs até o coordenador congelar o snapshot."""
        lock = self._lock_de_escrita(compartilhado=True, timeout_seconds=0)
        try:
            lock.__enter__()
        except TimeoutError:
            yield False
            return
        try:
            yield True
        finally:
            lock.__exit__(None, None, None)

    @contextmanager
    def lock_backup(self) -> Iterator[None]:
        lock = SingletonProcessLock(self._backup_lock_path)
        with lock:
            if not lock.adquirido:
                raise BackupJaEmExecucao
            yield

    def solicitar_manutencao(self) -> None:
        """Bloqueia novas mutações HTTP sem impedir que o worker drene a fila."""
        descriptor = os.open(
            self._marker,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as marker:
                marker.write(f"requested_at={datetime.now(UTC).isoformat()}\n")
                marker.flush()
                os.fsync(marker.fileno())
        except Exception:
            self._marker.unlink(missing_ok=True)
            raise
        self._manutencao_solicitada = True

    def liberar_manutencao(self) -> None:
        """Remove apenas o marcador criado por esta instância."""
        if not self._manutencao_solicitada:
            return
        self._marker.unlink(missing_ok=True)
        self._manutencao_solicitada = False

    @contextmanager
    def lock_snapshot(self, timeout_seconds: float) -> Iterator[None]:
        """Espera todas as mutações e jobs ativos liberarem o lock de escrita."""
        if timeout_seconds <= 0:
            raise ValueError("O timeout do snapshot deve ser positivo.")
        with self._lock_de_escrita(
            compartilhado=False, timeout_seconds=timeout_seconds
        ):
            yield

    @contextmanager
    def _lock_de_escrita(
        self, *, compartilhado: bool, timeout_seconds: float
    ) -> Iterator[None]:
        arquivo = self._lock_file_path.open("a+b")
        if self._lock_file_path.stat().st_size == 0:
            arquivo.write(b"\0")
            arquivo.flush()
        prazo = time.monotonic() + timeout_seconds
        adquirido = False
        try:
            while not adquirido:
                arquivo.seek(0)
                try:
                    _bloquear(arquivo, compartilhado=compartilhado)
                    adquirido = True
                except OSError as erro:
                    if time.monotonic() >= prazo:
                        raise TimeoutError(
                            "O lock de escrita do backup expirou."
                        ) from erro
                    time.sleep(min(0.05, max(0.001, prazo - time.monotonic())))
            yield
        finally:
            try:
                if adquirido:
                    arquivo.seek(0)
                    _desbloquear(arquivo)
            finally:
                arquivo.close()


def _bloquear(arquivo: BinaryIO, *, compartilhado: bool) -> None:
    if os.name == "nt":
        alterar_lock_windows(arquivo.fileno(), adquirir=True)
        return
    fcntl = importlib.import_module("fcntl")
    tipo = fcntl.LOCK_SH if compartilhado else fcntl.LOCK_EX
    fcntl.flock(arquivo.fileno(), tipo | fcntl.LOCK_NB)


def _desbloquear(arquivo: BinaryIO) -> None:
    if os.name == "nt":
        alterar_lock_windows(arquivo.fileno(), adquirir=False)
        return
    fcntl = importlib.import_module("fcntl")
    fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)
