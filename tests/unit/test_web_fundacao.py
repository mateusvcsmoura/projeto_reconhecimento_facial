"""Contratos da fundacao HTTP, isolados da stack de visao computacional."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.config.web_settings import WebSettings, get_web_settings
from src.infrastructure.workers.maintenance_gate import ManutencaoWeb
from src.presentation.web.app import (
    WebServices,
    _classificar_erro_http,
    create_app,
    utc_now,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL_TESTE = (
    "postgresql+psycopg://usuario:senha-nao-real@test-db:5432/face_test_task009"
)
SEGREDO_TESTE = "segredo-sintetico-para-testes-com-mais-de-32-caracteres"


def _settings(**overrides: object) -> WebSettings:
    valores: dict[str, object] = {
        "environment": "test",
        "database_url": DATABASE_URL_TESTE,
        "secret_key": SEGREDO_TESTE,
        "retention_days": 14,
        "database_disposable": True,
    }
    valores.update(overrides)
    return WebSettings(**valores)  # type: ignore[arg-type]


def _ready_app() -> TestClient:
    services = WebServices(readiness_probes={"database": lambda: True})
    return TestClient(create_app(_settings(), services))


def test_settings_web_exige_variaveis_proprias_e_nao_le_dotenv_ou_database_url(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "WEB_ENVIRONMENT=test\n"
        f"WEB_DATABASE_URL={DATABASE_URL_TESTE}\n"
        f"WEB_SECRET_KEY={SEGREDO_TESTE}\n"
        "WEB_RETENTION_DAYS=14\n"
        "WEB_DATABASE_DISPOSABLE=true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL_TESTE)
    for nome in (
        "WEB_ENVIRONMENT",
        "WEB_DATABASE_URL",
        "WEB_SECRET_KEY",
        "WEB_RETENTION_DAYS",
        "WEB_DATABASE_DISPOSABLE",
    ):
        monkeypatch.delenv(nome, raising=False)

    with pytest.raises(ValidationError):
        get_web_settings()


def test_settings_web_exige_banco_segredo_e_retencao() -> None:
    with pytest.raises(ValidationError) as erro:
        WebSettings(environment="test")  # type: ignore[call-arg]

    mensagem = str(erro.value)
    assert "database_url" in mensagem
    assert "secret_key" in mensagem
    assert "retention_days" in mensagem


def test_settings_web_so_permite_banco_de_teste_com_opt_in_e_marcador() -> None:
    with pytest.raises(ValidationError, match="descartavel"):
        _settings(database_disposable=False)

    with pytest.raises(ValidationError, match="marcador"):
        _settings(
            database_url="postgresql+psycopg://u:p@db:5432/presencas",
            database_disposable=True,
        )


def test_settings_web_rejeita_driver_ou_retencao_incompativeis() -> None:
    with pytest.raises(ValidationError, match="PostgreSQL"):
        _settings(database_url="mysql://u:p@db:3306/face_test")

    with pytest.raises(ValidationError, match="PostgreSQL"):
        _settings(database_url="postgresql://u:p@db:5432/face_test")

    with pytest.raises(ValidationError, match="inteiro positivo"):
        _settings(retention_days=True)

    with pytest.raises(ValidationError, match="maior que zero"):
        _settings(retention_days=0)


def test_settings_web_limites_atendem_uma_turma_no_mesmo_wifi() -> None:
    settings = _settings()

    # Uma sala inteira sai pelo mesmo IP: 20 alunos x 3 tentativas x 3 etapas.
    assert settings.job_queue_waiting_limit == 30
    assert settings.presence_start_limit_per_window == 60
    assert settings.presence_capture_limit_per_window == 300
    assert settings.public_registration_context_limit_per_minute == 40
    assert settings.capture_max_bytes_per_capture == 2 * 1024 * 1024
    with pytest.raises(ValidationError, match="WEB_JOB_QUEUE_WAITING_LIMIT"):
        _settings(job_queue_waiting_limit=100)


def test_settings_web_rejeita_segredo_curto_sem_reexibi_lo() -> None:
    segredo = "curto-e-sensivel"

    with pytest.raises(ValidationError) as erro:
        _settings(secret_key=segredo)

    assert segredo not in str(erro.value)


def test_settings_producao_rejeita_banco_local_ou_marcado_descartavel() -> None:
    with pytest.raises(ValidationError, match="local"):
        _settings(
            environment="production",
            database_url="postgresql+psycopg://u:p@localhost:5432/face_prod",
            database_disposable=False,
        )


def test_settings_producao_exige_media_pipe_em_ambiente_isolado() -> None:
    valores: dict[str, object] = {
        "environment": "production",
        "database_url": "postgresql+psycopg://u:p@db.example:5432/face_prod",
        "secret_key": SEGREDO_TESTE,
        "retention_days": 14,
        "public_origin": "https://face.example",
        "database_disposable": False,
    }
    with pytest.raises(ValidationError, match="ambiente MediaPipe isolado"):
        WebSettings(**valores)  # type: ignore[arg-type]

    valores["mediapipe_model_path"] = Path("/opt/facediff/models/face_landmarker.task")
    valores["mediapipe_python_executable"] = Path(
        "/opt/facediff/.venv-landmarks/bin/python"
    )
    valores["purpose_end_at"] = datetime(2026, 11, 1, tzinfo=UTC)
    valores["capture_temp_dir"] = Path("/run/facediff/capturas")
    valores["reference_storage_dir"] = Path("/var/lib/facediff/referencias")
    valores["maintenance_dir"] = Path("/var/lib/facediff/maintenance")
    valores["backup_exclusions_file"] = Path(
        "/var/lib/facediff/backup-control/exclusoes.jsonl"
    )
    settings = WebSettings(**valores)  # type: ignore[arg-type]
    assert settings.mediapipe_model_path is not None

    sem_gate = valores.copy()
    del sem_gate["maintenance_dir"]
    with pytest.raises(ValidationError, match="WEB_MAINTENANCE_DIR"):
        WebSettings(**sem_gate)  # type: ignore[arg-type]

    ledger_na_raiz_biometrica = valores.copy()
    ledger_na_raiz_biometrica["backup_exclusions_file"] = Path(
        "/var/lib/facediff/referencias/exclusoes.jsonl"
    )
    with pytest.raises(ValidationError, match="não pode ficar com as referências"):
        WebSettings(**ledger_na_raiz_biometrica)  # type: ignore[arg-type]

    del valores["mediapipe_python_executable"]
    with pytest.raises(ValidationError, match="configurados juntos"):
        WebSettings(**valores)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="descartavel"):
        _settings(
            environment="production",
            database_url="postgresql+psycopg://u:p@db.example:5432/face_prod",
            database_disposable=True,
        )


def test_web_settings_usa_prefixo_web_e_segredos_mascarados(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_ENVIRONMENT", "test")
    monkeypatch.setenv("WEB_DATABASE_URL", DATABASE_URL_TESTE)
    monkeypatch.setenv("WEB_SECRET_KEY", SEGREDO_TESTE)
    monkeypatch.setenv("WEB_RETENTION_DAYS", "14")
    monkeypatch.setenv("WEB_DATABASE_DISPOSABLE", "true")

    settings = get_web_settings()

    assert settings.environment == "test"
    assert settings.database_url.get_secret_value() == DATABASE_URL_TESTE
    assert settings.secret_key.get_secret_value() == SEGREDO_TESTE
    assert SEGREDO_TESTE not in repr(settings)


def test_live_e_ready_entregam_contratos_sem_configuracao_interna() -> None:
    with _ready_app() as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "live"}
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "componentes": {"database": "available"},
    }
    assert SEGREDO_TESTE not in live.text + ready.text


def test_manutencao_responde_503_para_api_e_mantem_health_disponivel(
    tmp_path: Path,
) -> None:
    assert "maintenance_gate" in WebServices.__dataclass_fields__
    gate = ManutencaoWeb(tmp_path / "maintenance")
    app = create_app(_settings(), WebServices(maintenance_gate=gate))
    gate.solicitar_manutencao()
    try:
        with TestClient(app) as client:
            api = client.post("/api/v1/auth/logout")
            live = client.get("/health/live")
    finally:
        gate.liberar_manutencao()

    assert api.status_code == 503
    assert api.json()["codigo"] == "manutencao"
    assert api.json()["request_id"] == api.headers["X-Request-ID"]
    assert api.headers["Retry-After"] == "60"
    assert live.status_code == 200


def test_ready_indica_indisponibilidade_sem_expor_excecao_ou_credencial() -> None:
    def falha_de_banco() -> bool:
        raise RuntimeError("senha-interna-nao-deve-aparecer")

    app = create_app(
        _settings(), WebServices(readiness_probes={"database": falha_de_banco})
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "componentes": {"database": "unavailable"},
    }
    assert "senha-interna" not in response.text
    assert SEGREDO_TESTE not in response.text


def test_erros_http_seguem_envelope_publico_com_request_id() -> None:
    app = create_app(_settings(), WebServices())

    with TestClient(app) as client:
        response = client.get("/rota-inexistente")

    assert response.status_code == 404
    assert set(response.json()) == {"codigo", "mensagem", "request_id"}
    assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert response.json()["codigo"] == "recurso_nao_encontrado"


@pytest.mark.parametrize(
    ("status_code", "detail", "codigo", "mensagem"),
    [
        (
            401,
            "Usuario ou senha invalidos.",
            "credenciais_invalidas",
            "Usuário ou senha inválidos.",
        ),
        (
            401,
            "Autenticação necessária.",
            "autenticacao_necessaria",
            "Sua sessão expirou ou você precisa entrar novamente.",
        ),
        (
            403,
            "Verificação CSRF recusada.",
            "csrf_recusado",
            "Não foi possível validar sua sessão. Atualize a página e tente novamente.",
        ),
        (
            503,
            "Gestão indisponível.",
            "servico_indisponivel",
            "O serviço está temporariamente indisponível. "
            "Tente novamente em instantes.",
        ),
    ],
)
def test_erro_http_tem_codigo_e_mensagem_publicos_coerentes(
    status_code: int, detail: str, codigo: str, mensagem: str
) -> None:
    app = create_app(_settings(), WebServices())

    @app.get("/erro-controlado")
    def erro_controlado() -> None:
        raise HTTPException(status_code=status_code, detail=detail)

    with TestClient(app) as client:
        response = client.get("/erro-controlado")

    assert response.status_code == status_code
    assert response.json()["codigo"] == codigo
    assert response.json()["mensagem"] == mensagem
    assert set(response.json()) == {"codigo", "mensagem", "request_id"}
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("status_code", "detail", "esperado"),
    [
        (
            401,
            "Usuario ou senha invalidos.",
            ("credenciais_invalidas", "Usuário ou senha inválidos."),
        ),
        (
            401,
            "Autenticação necessária.",
            (
                "autenticacao_necessaria",
                "Sua sessão expirou ou você precisa entrar novamente.",
            ),
        ),
        (
            403,
            "Verificação CSRF recusada.",
            (
                "csrf_recusado",
                "Não foi possível validar sua sessão. "
                "Atualize a página e tente novamente.",
            ),
        ),
        (
            403,
            "Origem recusada.",
            (
                "origem_recusada",
                "A origem da solicitação não foi autorizada. "
                "Atualize a página e tente novamente.",
            ),
        ),
        (
            503,
            "Gestão indisponível.",
            (
                "servico_indisponivel",
                "O serviço está temporariamente indisponível. "
                "Tente novamente em instantes.",
            ),
        ),
        (
            400,
            "Dados inválidos.",
            ("requisicao_invalida", "Dados inválidos."),
        ),
        (
            403,
            "Operacao nao autorizada.",
            (
                "operacao_nao_autorizada",
                "Você não tem permissão para realizar esta ação.",
            ),
        ),
        (
            404,
            "Not Found",
            ("recurso_nao_encontrado", "Recurso não encontrado."),
        ),
        (
            405,
            "Method Not Allowed",
            ("metodo_nao_permitido", "Método não permitido."),
        ),
        (
            409,
            "Conflito.",
            ("conflito_estado", "Conflito."),
        ),
        (
            410,
            "Acesso expirado.",
            ("acesso_expirado", "Acesso expirado."),
        ),
        (
            413,
            "Limite excedido.",
            ("conteudo_excedeu_limite", "Limite excedido."),
        ),
        (
            415,
            "Formato inválido.",
            ("tipo_midia_nao_suportado", "Formato inválido."),
        ),
        (
            422,
            "Campo inválido.",
            ("requisicao_invalida", "Campo inválido."),
        ),
        (
            429,
            "Muitas tentativas.",
            ("limite_requisicoes", "Muitas tentativas."),
        ),
        (
            504,
            "Detalhe interno que não deve aparecer.",
            (
                "servico_indisponivel",
                "O serviço está temporariamente indisponível. "
                "Tente novamente em instantes.",
            ),
        ),
        (
            418,
            "Detalhe seguro.",
            ("requisicao_recusada", "Detalhe seguro."),
        ),
        (
            500,
            "senha-interna-nao-deve-aparecer",
            ("erro_interno", "Ocorreu um erro interno."),
        ),
    ],
)
def test_classificacao_http_mantem_codigo_semantico_e_mensagem_segura(
    status_code: int,
    detail: str,
    esperado: tuple[str, str],
) -> None:
    assert _classificar_erro_http(status_code, detail) == esperado


def test_erro_interno_nao_revela_excecao_nem_traceback() -> None:
    app = create_app(_settings(), WebServices())

    @app.get("/erro-de-teste")
    def erro_de_teste() -> None:
        raise RuntimeError("credencial-interna-secreta")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/erro-de-teste")

    assert response.status_code == 500
    assert "credencial-interna-secreta" not in response.text
    assert "Traceback" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_erro_de_validacao_nao_retorna_detalhes_ou_valor_informado() -> None:
    app = create_app(_settings(), WebServices())

    @app.get("/valor/{item_id}")
    def buscar_valor(item_id: int) -> int:
        return item_id

    with TestClient(app) as client:
        response = client.get("/valor/entrada-sensivel")

    assert response.status_code == 422
    assert response.json()["codigo"] == "requisicao_invalida"
    assert "entrada-sensivel" not in response.text
    assert "int_parsing" not in response.text
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_documentacao_interativa_fica_desabilitada_e_openapi_tem_rota_propria() -> None:
    with _ready_app() as client:
        docs = client.get("/docs")
        openapi = client.get("/api/v1/openapi.json")

    assert docs.status_code == 404
    assert openapi.status_code == 200
    assert "/health/live" in openapi.json()["paths"]
    assert "/health/ready" in openapi.json()["paths"]


def test_relogio_padrao_e_relogio_injetado_sao_utc_aware() -> None:
    esperado = datetime(2026, 10, 18, 12, 30, tzinfo=UTC)
    services = WebServices(clock=lambda: esperado)

    assert utc_now().utcoffset().total_seconds() == 0
    assert services.now_utc() == esperado

    with pytest.raises(ValueError, match="UTC"):
        WebServices(clock=lambda: datetime(2026, 10, 18)).now_utc()


def test_import_da_fabrica_nao_carrega_visao_ml_ou_composicao_cli() -> None:
    codigo = """
import builtins
import sys

bloqueados = {"cv2", "deepface", "tensorflow", "torch", "mediapipe"}
importacao_real = builtins.__import__

def bloquear_importacoes(nome, *args, **kwargs):
    if nome == "src.main" or nome.split(".")[0] in bloqueados:
        raise AssertionError(f"import proibido: {nome}")
    return importacao_real(nome, *args, **kwargs)

builtins.__import__ = bloquear_importacoes
from src.presentation.web.app import create_app
assert callable(create_app)
assert not any(nome.split(".")[0] in bloqueados for nome in sys.modules)
assert "src.main" not in sys.modules
"""
    ambiente = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        cwd=PROJECT_ROOT,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr


def test_runtime_web_recusa_api_apos_fim_da_finalidade(tmp_path: Path) -> None:
    fim = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    gate = ManutencaoWeb(tmp_path / "maintenance")
    services = WebServices(maintenance_gate=gate, clock=lambda: fim)
    app = create_app(_settings(purpose_end_at=fim), services)

    with TestClient(app) as client:
        response = client.get("/api/v1/recurso-inexistente")
        openapi = client.get("/api/v1/openapi.json")

    assert response.status_code == 410
    assert response.json()["codigo"] == "finalidade_encerrada"
    assert openapi.status_code == 200
