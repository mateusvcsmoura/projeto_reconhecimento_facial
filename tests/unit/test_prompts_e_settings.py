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


def test_database_url_ausente_falha_no_boot() -> None:
    """Sem conexao definida nao ha default silencioso -- ha erro."""
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_url_que_nao_e_postgres_e_rejeitada() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(database_url="sqlite:///escola.db")


def test_log_level_invalido_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(database_url=URL_VALIDA, log_level="VERBOSO")


def test_log_level_e_normalizado_para_maiusculas() -> None:
    assert Settings(database_url=URL_VALIDA, log_level="debug").log_level == "DEBUG"


def test_camera_index_negativo_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="CAMERA_INDEX"):
        Settings(database_url=URL_VALIDA, camera_index=-1)


def test_timezone_invalido_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="APP_TIMEZONE"):
        Settings(database_url=URL_VALIDA, app_timezone="Marte/Olympus")


def test_timezone_valido_vira_zoneinfo() -> None:
    settings = Settings(database_url=URL_VALIDA, app_timezone="America/Sao_Paulo")
    assert str(settings.timezone) == "America/Sao_Paulo"
