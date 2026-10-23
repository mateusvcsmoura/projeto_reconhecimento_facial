"""Configuracao exclusiva do runtime HTTP.

As variaveis WEB_* sao obrigatorias para evitar herdar defaults e .env da CLI.
"""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated, Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    purpose_end_at: datetime | None = None
    consent_notice_version: str = "v1-2026-10-18"
    app_timezone: str = "America/Sao_Paulo"
    trusted_proxy_cidrs: str | None = None
    database_disposable: bool = False
    capture_temp_dir: Path | None = None
    reference_storage_dir: Path | None = None
    legacy_image_storage_dir: Path | None = None
    maintenance_dir: Path | None = None
    backup_exclusions_file: Path | None = None
    # Uma captura 960x720 JPEG tem ~100-250 KB; 2 MiB mantém folga e deixa a cota
    # de 300 MiB reservar espaço para a fila inteira (6 MiB por job).
    capture_max_bytes_per_capture: Annotated[int, Field(gt=0)] = 2 * 1024 * 1024
    capture_max_frames: Literal[3] = 3
    capture_storage_quota_bytes: Annotated[int, Field(gt=0)] = 300 * 1024 * 1024
    # Uma tentativa de presença ocupa vaga na fila durante todo o desafio; 30 cobre
    # uma turma de 20 verificando ao mesmo tempo.
    job_queue_waiting_limit: Annotated[int, Field(gt=0, le=1000)] = 30
    # Por link e IP numa janela de 15 min. Na faculdade a sala inteira sai pelo
    # mesmo IP: 20 alunos x 3 tentativas = 60 inícios; x 3 etapas = 180 capturas.
    presence_start_limit_per_window: Annotated[int, Field(gt=0, le=100_000)] = 60
    presence_capture_limit_per_window: Annotated[int, Field(gt=0, le=100_000)] = 300
    mediapipe_model_path: Path | None = None
    mediapipe_python_executable: Path | None = None
    job_reservation_seconds: Annotated[int, Field(gt=0)] = 300
    job_deadline_seconds: Annotated[int, Field(gt=0)] = 900
    job_lease_seconds: Annotated[int, Field(gt=0)] = 120
    public_registration_context_limit_per_minute: Annotated[
        int, Field(gt=0, le=100_000)
    ] = 10
    public_registration_query_limit_per_minute: Annotated[
        int, Field(gt=0, le=100_000)
    ] = 60
    public_registration_origin_limit_per_minute: Annotated[
        int, Field(gt=0, le=100_000)
    ] = 600

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

    @field_validator("purpose_end_at")
    @classmethod
    def _validar_fim_da_finalidade(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("WEB_PURPOSE_END_AT deve conter fuso horário.")
        return value

    @field_validator("consent_notice_version")
    @classmethod
    def _validar_versao_aviso(cls, value: str) -> str:
        normalizada = value.strip()
        if not normalizada or len(normalizada) > 64:
            raise ValueError("WEB_CONSENT_NOTICE_VERSION é inválida.")
        return normalizada

    @field_validator("app_timezone")
    @classmethod
    def _validar_fuso_aplicacao(cls, value: str) -> str:
        nome = value.strip()
        try:
            ZoneInfo(nome)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("WEB_APP_TIMEZONE deve ser um fuso IANA valido.") from exc
        return nome

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
        # Cada job reserva 3 capturas; a fila (+1 em processamento) precisa caber
        # na cota, senão ela trava em silêncio antes do limite configurado.
        reserva_da_fila = (
            self.capture_max_bytes_per_capture * 3 * (self.job_queue_waiting_limit + 1)
        )
        if self.capture_storage_quota_bytes < reserva_da_fila:
            raise ValueError(
                "WEB_JOB_QUEUE_WAITING_LIMIT excede o que "
                "WEB_CAPTURE_STORAGE_QUOTA_BYTES comporta."
            )
        if self.job_lease_seconds < 3:
            raise ValueError("WEB_JOB_LEASE_SECONDS deve ser de ao menos 3s.")
        if self.job_deadline_seconds < self.job_lease_seconds:
            raise ValueError("WEB_JOB_DEADLINE_SECONDS não pode ser menor que o lease.")
        return self

    @model_validator(mode="after")
    def _validar_landmarks_do_worker(self) -> WebSettings:
        if (self.mediapipe_model_path is None) != (
            self.mediapipe_python_executable is None
        ):
            raise ValueError(
                "WEB_MEDIAPIPE_MODEL_PATH e WEB_MEDIAPIPE_PYTHON_EXECUTABLE "
                "devem ser configurados juntos."
            )
        if self.environment == "production" and self.mediapipe_model_path is None:
            raise ValueError(
                "A produção exige modelo e ambiente MediaPipe isolado do worker."
            )
        if self.environment == "production":
            if self.purpose_end_at is None:
                raise ValueError("A produção exige WEB_PURPOSE_END_AT explícito.")
            if self.capture_temp_dir is None or self.reference_storage_dir is None:
                raise ValueError(
                    "A produção exige WEB_CAPTURE_TEMP_DIR e "
                    "WEB_REFERENCE_STORAGE_DIR explícitos."
                )
            if not _path_is_absolute(self.capture_temp_dir) or not _path_is_absolute(
                self.reference_storage_dir
            ):
                raise ValueError(
                    "Os diretórios biométricos de produção devem ser absolutos."
                )
            raiz_captura = self.capture_temp_dir.resolve()
            raiz_referencias = self.reference_storage_dir.resolve()
            if raiz_captura.is_relative_to(
                raiz_referencias
            ) or raiz_referencias.is_relative_to(raiz_captura):
                raise ValueError("Raizes temporaria e privada devem ser separadas.")
            if raiz_captura == raiz_referencias:
                raise ValueError("As raízes temporária e privada devem ser distintas.")
            if self.maintenance_dir is None or self.backup_exclusions_file is None:
                raise ValueError(
                    "A produção exige WEB_MAINTENANCE_DIR e "
                    "WEB_BACKUP_EXCLUSIONS_FILE explícitos."
                )
            if not _path_is_absolute(self.maintenance_dir) or not _path_is_absolute(
                self.backup_exclusions_file
            ):
                raise ValueError(
                    "Os caminhos de manutenção e exclusões devem ser absolutos."
                )
            raiz_manutencao = self.maintenance_dir.resolve()
            arquivo_exclusoes = self.backup_exclusions_file.resolve()
            if (
                raiz_manutencao.is_relative_to(raiz_captura)
                or raiz_captura.is_relative_to(raiz_manutencao)
                or raiz_manutencao.is_relative_to(raiz_referencias)
                or raiz_referencias.is_relative_to(raiz_manutencao)
            ):
                raise ValueError(
                    "Raizes de manutencao, captura e referencia devem ser distintas."
                )
            if arquivo_exclusoes.is_relative_to(raiz_manutencao):
                raise ValueError(
                    "O registro de exclusões não pode ficar na raiz do backup."
                )
            if arquivo_exclusoes.is_relative_to(self.capture_temp_dir.resolve()):
                raise ValueError(
                    "O registro de exclusoes nao pode ficar com capturas temporarias."
                )
            if arquivo_exclusoes.is_relative_to(self.reference_storage_dir.resolve()):
                raise ValueError(
                    "O registro de exclusões não pode ficar com as referências faciais."
                )
        return self


def get_web_settings() -> WebSettings:
    """Lê apenas WEB_* do ambiente; nunca consulta o .env usado pela CLI."""

    return WebSettings()  # type: ignore[call-arg]


def _path_is_absolute(value: Path) -> bool:
    return (
        value.is_absolute()
        or PurePosixPath(value.as_posix()).is_absolute()
        or PureWindowsPath(str(value)).is_absolute()
    )
