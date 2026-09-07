"""Engine e sessao do SQLAlchemy.

Nao cria schema. A criacao de tabelas pertence as migrations (Alembic).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config.settings import get_settings


def criar_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    return create_engine(url, future=True, pool_pre_ping=True)


def criar_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def sessao(engine: Engine) -> Iterator[Session]:
    """Sessao transacional: commit no sucesso, rollback em qualquer erro."""
    factory = criar_session_factory(engine)
    with factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
