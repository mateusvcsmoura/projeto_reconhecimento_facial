"""Fase 2 -- entrada do operador e configuracao. Sem stdin, sem banco."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config.settings import PROJECT_ROOT, Settings
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


def test_consistencia_temporal_comeca_desabilitada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for nome in (
        "FACE_TEMPORAL_ENABLED",
        "FACE_TEMPORAL_MIN_OBSERVATIONS",
        "FACE_TEMPORAL_WINDOW_SECONDS",
        "FACE_TEMPORAL_MAX_AGE_SECONDS",
    ):
        monkeypatch.delenv(nome, raising=False)

    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_temporal_enabled is False
    assert settings.face_temporal_min_observations == 3
    assert settings.face_temporal_window_seconds == 5.0
    assert settings.face_temporal_max_age_seconds == 2.0


def test_consistencia_temporal_aceita_overrides_de_ambiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FACE_TEMPORAL_ENABLED", "true")
    monkeypatch.setenv("FACE_TEMPORAL_MIN_OBSERVATIONS", "4")
    monkeypatch.setenv("FACE_TEMPORAL_WINDOW_SECONDS", "6.5")
    monkeypatch.setenv("FACE_TEMPORAL_MAX_AGE_SECONDS", "2.5")

    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_temporal_enabled is True
    assert settings.face_temporal_min_observations == 4
    assert settings.face_temporal_window_seconds == 6.5
    assert settings.face_temporal_max_age_seconds == 2.5


def test_consistencia_temporal_aceita_overrides_por_kwargs() -> None:
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        face_temporal_enabled=True,
        face_temporal_min_observations=2,
        face_temporal_window_seconds=1.0,
        face_temporal_max_age_seconds=1.0,
    )

    assert settings.face_temporal_enabled is True
    assert settings.face_temporal_min_observations == 2
    assert settings.face_temporal_window_seconds == 1.0
    assert settings.face_temporal_max_age_seconds == 1.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"face_temporal_min_observations": 1},
        {"face_temporal_min_observations": 0},
        {"face_temporal_min_observations": -1},
        {"face_temporal_min_observations": 2.5},
        {"face_temporal_min_observations": True},
        {"face_temporal_window_seconds": 0.0},
        {"face_temporal_window_seconds": -1.0},
        {"face_temporal_window_seconds": float("nan")},
        {"face_temporal_window_seconds": float("inf")},
        {"face_temporal_window_seconds": True},
        {"face_temporal_max_age_seconds": 0.0},
        {"face_temporal_max_age_seconds": -1.0},
        {"face_temporal_max_age_seconds": float("nan")},
        {"face_temporal_max_age_seconds": float("inf")},
        {"face_temporal_max_age_seconds": True},
        {
            "face_temporal_window_seconds": 1.0,
            "face_temporal_max_age_seconds": 1.1,
        },
    ],
)
def test_consistencia_temporal_rejeita_configuracao_invalida(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=URL_VALIDA, **kwargs)  # type: ignore[arg-type]


def test_ambiguidade_comeca_desabilitada_e_sem_margem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FACE_AMBIGUITY_ENABLED", raising=False)
    monkeypatch.delenv("FACE_AMBIGUITY_MIN_MARGIN", raising=False)

    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_ambiguity_enabled is False
    assert settings.face_ambiguity_min_margin is None


def test_ambiguidade_habilitada_exige_margem_explicita() -> None:
    with pytest.raises(ValidationError, match="FACE_AMBIGUITY_MIN_MARGIN"):
        Settings(
            _env_file=None,
            database_url=URL_VALIDA,
            face_ambiguity_enabled=True,
        )


@pytest.mark.parametrize("margem", [0, 2, 0.25])
def test_ambiguidade_aceita_margens_validas(margem: int | float) -> None:
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        face_ambiguity_enabled=True,
        face_ambiguity_min_margin=margem,
    )

    assert settings.face_ambiguity_enabled is True
    assert settings.face_ambiguity_min_margin == float(margem)


def test_margem_numerica_vinda_do_ambiente_e_aceita(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FACE_AMBIGUITY_ENABLED", "true")
    monkeypatch.setenv("FACE_AMBIGUITY_MIN_MARGIN", "0.125")

    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_ambiguity_enabled is True
    assert settings.face_ambiguity_min_margin == 0.125


def test_margem_valida_nao_habilita_politica_sozinha() -> None:
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        face_ambiguity_min_margin=0.5,
    )

    assert settings.face_ambiguity_enabled is False
    assert settings.face_ambiguity_min_margin == 0.5


@pytest.mark.parametrize(
    "margem",
    [True, False, "", "invalido", -0.1, 2.1, float("nan"), float("inf")],
)
def test_settings_recusa_margem_invalida_mesmo_com_flag_desligada(
    margem: object,
) -> None:
    with pytest.raises(ValidationError, match="FACE_AMBIGUITY_MIN_MARGIN"):
        Settings(
            _env_file=None,
            database_url=URL_VALIDA,
            face_ambiguity_enabled=False,
            face_ambiguity_min_margin=margem,
        )  # type: ignore[arg-type]


def test_margem_vazia_no_ambiente_e_invalida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FACE_AMBIGUITY_MIN_MARGIN", "")

    with pytest.raises(ValidationError, match="FACE_AMBIGUITY_MIN_MARGIN"):
        Settings(_env_file=None, database_url=URL_VALIDA)


def test_landmarks_sao_optativos_e_caminho_padrao_fica_na_raiz_do_projeto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FACE_LANDMARKS_ENABLED", raising=False)
    monkeypatch.delenv("FACE_LANDMARKS_MODEL_PATH", raising=False)
    monkeypatch.delenv("FACE_LANDMARKS_PYTHON_PATH", raising=False)

    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_landmarks_enabled is False
    assert (
        settings.face_landmarks_model_path
        == PROJECT_ROOT / "models" / "face_landmarker.task"
    )
    assert (
        settings.face_landmarks_python_path
        == PROJECT_ROOT / ".venv-landmarks" / "Scripts" / "python.exe"
    )


def test_caminho_relativo_dos_landmarks_resolve_a_partir_da_raiz_do_projeto() -> None:
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        face_landmarks_model_path="models/alternativo.task",
        face_landmarks_python_path="tools/python-landmarks.exe",
    )

    assert (
        settings.face_landmarks_model_path
        == PROJECT_ROOT / "models" / "alternativo.task"
    )
    assert (
        settings.face_landmarks_python_path
        == PROJECT_ROOT / "tools" / "python-landmarks.exe"
    )


def test_landmarks_aceitam_override_de_ambiente(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caminho = tmp_path / "landmarker.task"
    python_path = tmp_path / "python-landmarks.exe"
    monkeypatch.setenv("FACE_LANDMARKS_ENABLED", "true")
    monkeypatch.setenv("FACE_LANDMARKS_MODEL_PATH", str(caminho))
    monkeypatch.setenv("FACE_LANDMARKS_PYTHON_PATH", str(python_path))

    settings = Settings(_env_file=None, database_url=URL_VALIDA)

    assert settings.face_landmarks_enabled is True
    assert settings.face_landmarks_model_path == caminho
    assert settings.face_landmarks_python_path == python_path
