"""Composicao HTTP com banco injetado, sem abrir conexao real."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from src.config.web_settings import WebSettings
from src.web_main import create_web_app


class _ConnectionFake:
    def __enter__(self) -> _ConnectionFake:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, statement: Any) -> None:
        assert str(statement) == "SELECT 1"


class _EngineFake:
    def __init__(self) -> None:
        self.connect_calls = 0
        self.dispose_calls = 0

    def connect(self) -> _ConnectionFake:
        self.connect_calls += 1
        return _ConnectionFake()

    def dispose(self) -> None:
        self.dispose_calls += 1


def test_runtime_cria_engine_sem_conectar_e_fecha_no_shutdown() -> None:
    settings = WebSettings(
        environment="test",
        database_url=(
            "postgresql+psycopg://usuario:senha-nao-real@test-db:5432/face_test_task009"
        ),
        secret_key="segredo-sintetico-para-testes-com-mais-de-32-caracteres",
        retention_days=14,
        database_disposable=True,
    )
    engine = _EngineFake()

    app = create_web_app(settings, engine_factory=lambda *_args, **_kwargs: engine)

    assert engine.connect_calls == 0
    with TestClient(app) as client:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {
            "status": "ready",
            "componentes": {"database": "available"},
        }
        assert engine.connect_calls == 1

    assert engine.dispose_calls == 1
