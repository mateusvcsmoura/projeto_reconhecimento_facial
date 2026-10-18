"""Composition root HTTP; não importa nem inicializa a composição da CLI."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

from src.application.services.fila_facial import FilaFacial
from src.config.web_settings import WebSettings, get_web_settings
from src.infrastructure.repositories.postgres_conta_repository import (
    PostgresContaRepository,
)
from src.infrastructure.repositories.postgres_job_repository import (
    PostgresJobRepository,
)
from src.presentation.web.app import WebServices, create_app


def _database_ready(engine: Engine) -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


def create_web_app(
    settings: WebSettings | None = None,
    *,
    engine_factory: Callable[..., Engine] = create_engine,
) -> FastAPI:
    """Cria a aplicacao ASGI com engine lazy e configuracao WEB_* obrigatoria.

    Executar com ``uvicorn src.web_main:create_web_app --factory``. A engine
    nao abre conexao ate o probe de readiness ser solicitado.
    """

    configuracao = settings or get_web_settings()
    engine = engine_factory(
        configuracao.database_url.get_secret_value(),
        future=True,
        pool_pre_ping=True,
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    auth_repository = PostgresContaRepository(
        session_factory,
        segredo=configuracao.secret_key.get_secret_value(),
    )
    jobs_repository = PostgresJobRepository(session_factory)
    fila_facial = FilaFacial(
        jobs_repository,
        segredo=configuracao.secret_key.get_secret_value().encode(),
        relogio=lambda: datetime.now(UTC),
        limite_aguardando=10,
        quota_temporaria_bytes=configuracao.capture_storage_quota_bytes,
        max_bytes_por_captura=configuracao.capture_max_bytes_per_capture,
        max_capturas=configuracao.capture_max_frames,
        prazo_maximo_reserva=timedelta(seconds=configuracao.job_reservation_seconds),
        prazo_maximo_execucao=timedelta(seconds=configuracao.job_deadline_seconds),
        duracao_lease=timedelta(seconds=configuracao.job_lease_seconds),
    )
    services = WebServices(
        readiness_probes={"database": lambda: _database_ready(engine)},
        auth_repository=auth_repository,
        fila_facial=fila_facial,
        on_shutdown=engine.dispose,
    )
    return create_app(configuracao, services)
