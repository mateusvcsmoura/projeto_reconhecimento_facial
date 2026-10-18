"""Configuracao exclusiva do runtime HTTP.

As variaveis WEB_* sao obrigatorias para evitar herdar defaults e .env da CLI.
"""

from __future__ import annotations

import ipaddress
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebSettings(BaseSettings):
    """Configuracao do servico web, independente de ``src.config.settings``."""

    model_config = SettingsConfigDict(
        env_prefix="WEB_",
        env_file=None,
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Literal["development", "test", "production"]
    database_url: SecretStr
    secret_key: SecretStr
    retention_days: int
    database_disposable: bool = False

    @field_validator("database_url")
    @classmethod
    def _validar_url_postgres(cls, value: SecretStr) -> SecretStr:
        try:
            parsed = urlsplit(value.get_secret_value())
            host = parsed.hostname
        except ValueError as exc:
            raise ValueError(
                "WEB_DATABASE_URL deve ser uma URL PostgreSQL valida."
            ) from exc

        if (
            parsed.scheme != "postgresql+psycopg"
            or not host
            or not parsed.path.strip("/")
        ):
            raise ValueError("WEB_DATABASE_URL deve apontar para um banco PostgreSQL.")
        return value

    @field_validator("secret_key")
    @classmethod
    def _exigir_segredo_forte(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("WEB_SECRET_KEY deve conter ao menos 32 caracteres.")
        return value

    @field_validator("retention_days", mode="before")
    @classmethod
    def _rejeitar_booleano_como_retencao(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("WEB_RETENTION_DAYS deve ser um inteiro positivo.")
        return value

    @field_validator("retention_days")
    @classmethod
    def _exigir_retencao_positiva(cls, value: int) -> int:
        if value < 1:
            raise ValueError("WEB_RETENTION_DAYS deve ser maior que zero.")
        return value

    @model_validator(mode="after")
    def _proteger_destino_do_banco(self) -> WebSettings:
        parsed = urlsplit(self.database_url.get_secret_value())
        host = (parsed.hostname or "").lower().rstrip(".")
        nome_banco = parsed.path.strip("/").lower()
        host_local = host == "localhost" or host.endswith(".localhost")
        try:
            endereco = ipaddress.ip_address(host)
        except ValueError:
            endereco = None
        if endereco is not None and (endereco.is_loopback or endereco.is_unspecified):
            host_local = True

        if self.environment == "production":
            if host_local:
                raise ValueError(
                    "WEB_DATABASE_URL de producao nao pode usar banco local."
                )
            if self.database_disposable:
                raise ValueError("Banco descartavel nao pode ser usado em producao.")
            return self

        if host_local and not self.database_disposable:
            raise ValueError("Banco local exige WEB_DATABASE_DISPOSABLE=true.")

        if self.environment == "test":
            if not self.database_disposable:
                raise ValueError(
                    "Ambiente test exige banco descartavel explicitamente."
                )
            marcadores = set(re.split(r"[-_]", nome_banco))
            if not marcadores.intersection(
                {"test", "tests", "testing", "disposable", "descartavel"}
            ):
                raise ValueError(
                    "Nome do banco de test deve conter marcador descartavel."
                )

        return self


def get_web_settings() -> WebSettings:
    """Lê apenas WEB_* do ambiente; nunca consulta o .env usado pela CLI."""

    return WebSettings()  # type: ignore[call-arg]
