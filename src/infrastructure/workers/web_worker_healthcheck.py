"""Probe de prontidao do worker facial para o healthcheck do container."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.config.web_settings import WebSettings, get_web_settings
from src.infrastructure.repositories.postgres_job_repository import (
    _LOCK_WORKER_UNICO,
)


def worker_pronto(settings: WebSettings | None = None) -> bool:
    """Confirma aquecimento concluido, DB acessivel e lock unico mantido."""
    try:
        configuracao = settings or get_web_settings()
    except Exception:
        return False
    if configuracao.maintenance_dir is None:
        return False
    marcador = Path(configuracao.maintenance_dir) / ".worker-ready"
    if not marcador.is_file():
        return False

    engine: Engine | None = None
    try:
        engine = create_engine(
            configuracao.database_url.get_secret_value(),
            future=True,
            pool_pre_ping=True,
        )
        with engine.connect() as connection:
            adquiriu_lock = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": _LOCK_WORKER_UNICO},
                ).scalar_one()
            )
            connection.commit()
            if adquiriu_lock:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": _LOCK_WORKER_UNICO},
                )
                connection.commit()
                return False
        return marcador.is_file()
    except SQLAlchemyError:
        return False
    finally:
        if engine is not None:
            engine.dispose()


def main() -> int:
    return 0 if worker_pronto() else 1


if __name__ == "__main__":
    sys.exit(main())
