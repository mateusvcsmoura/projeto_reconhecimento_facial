from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

from src.config.web_settings import WebSettings
from src.web_main import create_web_app

SEGREDO = "segredo-sintetico-de-composicao-com-mais-de-trinta-e-dois-caracteres"
URL_TESTE = "postgresql+psycopg://usuario:senha@test-db:5432/face_test_task014"


def _settings(**overrides: object) -> WebSettings:
    valores: dict[str, object] = {
        "environment": "test",
        "database_url": URL_TESTE,
        "secret_key": SEGREDO,
        "retention_days": 14,
        "database_disposable": True,
    }
    valores.update(overrides)
    return WebSettings(**valores)  # type: ignore[arg-type]


def test_composicao_web_injeta_engine_e_storages_locais(
    tmp_path: Path,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    dispose = Mock(wraps=engine.dispose)
    engine.dispose = dispose  # type: ignore[method-assign]
    settings = _settings(
        capture_temp_dir=tmp_path / "capturas",
        reference_storage_dir=tmp_path / "referencias",
    )

    app = create_web_app(settings, engine_factory=lambda *_args, **_kwargs: engine)
    with TestClient(app) as client:
        ready = client.get("/health/ready")

    assert ready.status_code == 200
    assert ready.json() == {"status": "ready", "componentes": {"database": "available"}}
    assert (tmp_path / "capturas").is_dir()
    assert (tmp_path / "referencias").is_dir()
    dispose.assert_called_once_with()


def test_composicao_web_marca_banco_indisponivel_sem_expor_erro() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "engine_connect")
    def falhar_conexao(_connection: Any) -> None:
        raise RuntimeError("erro e credencial que nao podem vazar")

    app = create_web_app(_settings(), engine_factory=lambda *_args, **_kwargs: engine)
    with TestClient(app) as client:
        ready = client.get("/health/ready")

    assert ready.status_code == 503
    assert ready.json() == {
        "status": "not_ready",
        "componentes": {"database": "unavailable"},
    }
    assert "credencial" not in ready.text
