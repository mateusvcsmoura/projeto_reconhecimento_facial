"""Fase 2 -- entrada do operador e configuracao. Sem stdin, sem banco."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config.settings import Settings
from src.presentation.cli import prompts

URL_VALIDA = "postgresql+psycopg://u:p@h:5432/d"


def leitor(*respostas: str) -> prompts.Leitor:
    fila = list(respostas)
    return lambda _rotulo: fila.pop(0)


def test_perguntar_remove_espacos_das_bordas() -> None:
    assert prompts.perguntar("Nome: ", leitor("  Maria  ")) == "Maria"


def test_opcao_valida_e_devolvida() -> None:
    assert prompts.perguntar_opcao({"1", "2", "3"}, leitor("2")) == "2"


def test_opcao_invalida_vira_none() -> None:
    assert prompts.perguntar_opcao({"1", "2", "3"}, leitor("9")) is None


def test_opcao_vazia_vira_none() -> None:
    assert prompts.perguntar_opcao({"1"}, leitor("   ")) is None


def test_database_url_ausente_falha_no_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem conexao definida nao ha default silencioso -- ha erro.

    O monkeypatch e necessario: em CI a DATABASE_URL vem do ambiente, e o
    pydantic-settings a encontraria mesmo com _env_file desligado. O teste
    precisa controlar o proprio ambiente para significar algo.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_url_que_nao_e_postgres_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(_env_file=None, database_url="sqlite:///escola.db")


def test_log_level_invalido_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(_env_file=None, database_url=URL_VALIDA, log_level="VERBOSO")


def test_log_level_e_normalizado_para_maiusculas() -> None:
    assert (
        Settings(_env_file=None, database_url=URL_VALIDA, log_level="debug").log_level
        == "DEBUG"
    )


def test_camera_index_negativo_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="CAMERA_INDEX"):
        Settings(_env_file=None, database_url=URL_VALIDA, camera_index=-1)


def test_timezone_invalido_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="APP_TIMEZONE"):
        Settings(_env_file=None, database_url=URL_VALIDA, app_timezone="Marte/Olympus")


def test_timezone_valido_vira_zoneinfo() -> None:
    settings = Settings(
        _env_file=None, database_url=URL_VALIDA, app_timezone="America/Sao_Paulo"
    )
    assert str(settings.timezone) == "America/Sao_Paulo"


def test_qualidade_de_captura_comeca_desabilitada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nome in (
        "FACE_QUALITY_ENABLED",
        "FACE_QUALITY_MIN_FACE_PX",
        "FACE_QUALITY_MIN_BRIGHTNESS",
        "FACE_QUALITY_MAX_BRIGHTNESS",
        "FACE_QUALITY_MIN_SHARPNESS",
    ):
        monkeypatch.delenv(nome, raising=False)
    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_quality_enabled is False
    assert settings.face_quality_min_face_px == 80
    assert settings.face_quality_min_brightness == 40.0
    assert settings.face_quality_max_brightness == 215.0
    assert settings.face_quality_min_sharpness == 100.0


def test_qualidade_de_captura_aceita_valores_personalizados() -> None:
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        face_quality_enabled=True,
        face_quality_min_face_px=96,
        face_quality_min_brightness=35.0,
        face_quality_max_brightness=220.0,
        face_quality_min_sharpness=125.0,
    )

    assert settings.face_quality_enabled is True
    assert settings.face_quality_min_face_px == 96
    assert settings.face_quality_min_brightness == 35.0
    assert settings.face_quality_max_brightness == 220.0
    assert settings.face_quality_min_sharpness == 125.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"face_quality_min_face_px": 2},
        {"face_quality_min_brightness": -1.0},
        {"face_quality_min_brightness": 256.0},
        {"face_quality_min_brightness": float("nan")},
        {"face_quality_max_brightness": 256.0},
        {"face_quality_max_brightness": float("inf")},
        {"face_quality_min_sharpness": -1.0},
        {"face_quality_min_sharpness": float("nan")},
        {
            "face_quality_min_brightness": 215.0,
            "face_quality_max_brightness": 215.0,
        },
    ],
)
def test_qualidade_de_captura_rejeita_configuracao_invalida(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=URL_VALIDA, **kwargs)  # type: ignore[arg-type]
