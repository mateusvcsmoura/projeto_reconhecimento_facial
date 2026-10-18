"""Configuracao exclusiva do runtime HTTP.

As variaveis WEB_* sao obrigatorias para evitar herdar defaults e .env da CLI.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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
    public_origin: str | None = None
    trusted_proxy_cidrs: str | None = None
    database_disposable: bool = False
    capture_temp_dir: Path | None = None
    capture_max_bytes_per_capture: Annotated[int, Field(gt=0)] = 8 * 1024 * 1024
    capture_max_frames: Literal[3] = 3
    capture_storage_quota_bytes: Annotated[int, Field(gt=0)] = 300 * 1024 * 1024
    job_reservation_seconds: Annotated[int, Field(gt=0)] = 300
    job_deadline_seconds: Annotated[int, Field(gt=0)] = 900
    job_lease_seconds: Annotated[int, Field(gt=0)] = 120

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

    @field_validator("public_origin")
    @classmethod
    def _validar_origem_publica(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            parsed = urlsplit(value)
            host = parsed.hostname
            porta = parsed.port
        except ValueError as exc:
            raise ValueError(
                "WEB_PUBLIC_ORIGIN deve ser uma origem HTTP(S) valida."
            ) from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "WEB_PUBLIC_ORIGIN deve conter somente esquema, host e porta."
            )
        hostname = host.encode("idna").decode("ascii").lower()
        if ":" in hostname:
            hostname = f"[{hostname}]"
        if (parsed.scheme.lower(), porta) in {("http", 80), ("https", 443)}:
            porta = None
        netloc = f"{hostname}:{porta}" if porta is not None else hostname
        return f"{parsed.scheme.lower()}://{netloc}"

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _validar_proxies_confiaveis(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        for item in value.split(","):
            try:
                ipaddress.ip_network(item.strip(), strict=False)
            except ValueError as exc:
                raise ValueError(
                    "WEB_TRUSTED_PROXY_CIDRS contem uma rede invalida."
                ) from exc
        return ",".join(item.strip() for item in value.split(","))

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
            if self.public_origin is None or not self.public_origin.startswith(
                "https://"
            ):
                raise ValueError("WEB_PUBLIC_ORIGIN HTTPS e obrigatoria em producao.")
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

    @model_validator(mode="after")
    def _validar_limites_de_captura(self) -> WebSettings:
        if self.capture_storage_quota_bytes < self.capture_max_bytes_per_capture * 3:
            raise ValueError(
                "WEB_CAPTURE_STORAGE_QUOTA_BYTES deve comportar um job completo."
            )
        if self.job_lease_seconds < 3:
            raise ValueError("WEB_JOB_LEASE_SECONDS deve ser de ao menos 3s.")
        if self.job_deadline_seconds < self.job_lease_seconds:
            raise ValueError("WEB_JOB_DEADLINE_SECONDS não pode ser menor que o lease.")
        return self


def get_web_settings() -> WebSettings:
    """Lê apenas WEB_* do ambiente; nunca consulta o .env usado pela CLI."""

    return WebSettings()  # type: ignore[call-arg]
