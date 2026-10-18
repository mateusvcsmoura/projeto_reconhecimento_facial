"""Composition root HTTP; não importa nem inicializa a composição da CLI."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker

from src.config.web_settings import WebSettings, get_web_settings
from src.infrastructure.repositories.postgres_conta_repository import (
    PostgresContaRepository,
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
    services = WebServices(
        readiness_probes={"database": lambda: _database_ready(engine)},
        auth_repository=auth_repository,
        on_shutdown=engine.dispose,
    )
    return create_app(configuracao, services)
