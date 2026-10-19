from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.infrastructure.workers import web_worker_healthcheck


class _Result:
    def __init__(self, value: bool) -> None:
        self.value = value

    def scalar_one(self) -> bool:
        return self.value


class _Connection:
    def __init__(self, lock_acquired: bool) -> None:
        self.lock_acquired = lock_acquired
        self.statements: list[str] = []
        self.commits = 0

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: Any, _parameters: object = None) -> _Result:
        self.statements.append(str(statement))
        return _Result(self.lock_acquired)

    def commit(self) -> None:
        self.commits += 1


class _Engine:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.disposed = False

    def connect(self) -> _Connection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def test_worker_nao_pronto_sem_marcador_nao_abre_conexao(
    tmp_path: Path, monkeypatch: Any
) -> None:
    maintenance = tmp_path / "maintenance"
    settings = SimpleNamespace(maintenance_dir=maintenance)
    monkeypatch.setattr(
        web_worker_healthcheck,
        "create_engine",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("conectou")),
    )

    assert not web_worker_healthcheck.worker_pronto(settings)


def test_worker_pronto_exige_lock_advisory_ativo(
    tmp_path: Path, monkeypatch: Any
) -> None:
    maintenance = tmp_path / "maintenance"
    maintenance.mkdir()
    (maintenance / ".worker-ready").touch()
    settings = SimpleNamespace(
        maintenance_dir=maintenance,
        database_url=SimpleNamespace(get_secret_value=lambda: "postgresql://test"),
    )
    connection = _Connection(lock_acquired=True)
    engine = _Engine(connection)
    monkeypatch.setattr(
        web_worker_healthcheck,
        "create_engine",
        lambda *_args, **_kwargs: engine,
    )

    assert not web_worker_healthcheck.worker_pronto(settings)
    assert any("pg_advisory_unlock" in sql for sql in connection.statements)
    assert engine.disposed


def test_worker_pronto_confirma_modelos_aquecidos_e_lock_do_banco(
    tmp_path: Path, monkeypatch: Any
) -> None:
    maintenance = tmp_path / "maintenance"
    maintenance.mkdir()
    (maintenance / ".worker-ready").touch()
    settings = SimpleNamespace(
        maintenance_dir=maintenance,
        database_url=SimpleNamespace(get_secret_value=lambda: "postgresql://test"),
    )
    connection = _Connection(lock_acquired=False)
    engine = _Engine(connection)
    monkeypatch.setattr(
        web_worker_healthcheck,
        "create_engine",
        lambda *_args, **_kwargs: engine,
    )

    assert web_worker_healthcheck.worker_pronto(settings)
    assert not any("pg_advisory_unlock" in sql for sql in connection.statements)
    assert engine.disposed
