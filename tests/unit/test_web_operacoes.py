from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.application.services.fila_facial import (
    EstadoJobFacial,
    FilaCheia,
    OperacaoNaoEncontrada,
    StatusOperacao,
)
from src.config.web_settings import WebSettings
from src.presentation.web.app import WebServices, create_app

UTC = dt.UTC
ORIGEM_TESTE = "https://face.example.test"
SEGREDO_TESTE = "segredo-sintetico-para-testes-com-mais-de-32-caracteres"
URL_TESTE = "postgresql+psycopg://user:password@test-db:5432/face_test_task012"


def _settings() -> WebSettings:
    return WebSettings(
        environment="test",
        database_url=URL_TESTE,
        secret_key=SEGREDO_TESTE,
        retention_days=14,
        public_origin=ORIGEM_TESTE,
        database_disposable=True,
    )


class FilaFake:
    def __init__(self, job_id: uuid.UUID) -> None:
        self.job_id = job_id
        self.token = "opaque-owner-credential"

    def consultar(self, job_id: uuid.UUID, token: str) -> StatusOperacao:
        if job_id != self.job_id or token != self.token:
            raise OperacaoNaoEncontrada()
        instante = dt.datetime(2026, 10, 18, 12, tzinfo=UTC)
        return StatusOperacao(
            id=job_id,
            estado=EstadoJobFacial.PROCESSANDO,
            criada_em=instante,
            atualizada_em=instante,
            codigo=None,
        )


def _client(fila: Any) -> TestClient:
    return TestClient(create_app(_settings(), WebServices(fila_facial=fila)))


def test_consulta_operacao_exige_credencial_opaca_e_nao_cacheia() -> None:
    job_id = uuid.uuid4()
    fila = FilaFake(job_id)
    client = _client(fila)

    sem_credencial = client.get(f"/api/v1/operacoes/{job_id}")
    errada = client.get(
        f"/api/v1/operacoes/{job_id}",
        headers={"Authorization": "Bearer another-owner"},
    )
    correta = client.get(
        f"/api/v1/operacoes/{job_id}",
        headers={"Authorization": f"Bearer {fila.token}"},
    )

    assert sem_credencial.status_code == 404
    assert errada.status_code == 404
    assert correta.status_code == 200
    assert correta.json()["estado"] == "processando"
    assert correta.headers["cache-control"] == "no-store"
    assert correta.headers["x-request-id"]


def test_fila_cheia_retorna_503_com_retry_after() -> None:
    app = create_app(_settings(), WebServices())

    @app.get("/test-fila-cheia")
    def fila_cheia() -> None:
        raise FilaCheia(7)

    with TestClient(app) as client:
        response = client.get("/test-fila-cheia")

    assert response.status_code == 503
    assert response.headers["retry-after"] == "7"
    assert response.json()["codigo"] == "fila_cheia"
    assert "detalhe" not in response.text


def test_operacao_nao_configurada_responde_indisponivel_sem_ml() -> None:
    client = _client(None)

    response = client.get(
        f"/api/v1/operacoes/{uuid.uuid4()}",
        headers={"Authorization": "Bearer opaque-token"},
    )

    assert response.status_code == 503
    assert response.json()["codigo"] == "requisicao_recusada"


@pytest.mark.parametrize("frames", [0, 4])
def test_settings_nao_permite_limite_de_frames_incompativel(frames: int) -> None:
    with pytest.raises(ValueError):
        WebSettings(
            environment="test",
            database_url=URL_TESTE,
            secret_key=SEGREDO_TESTE,
            retention_days=14,
            database_disposable=True,
            capture_max_frames=frames,  # type: ignore[arg-type]
        )
