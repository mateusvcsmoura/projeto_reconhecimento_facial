"""Configuracao lida do ambiente.

Regra do projeto (CLAUDE.md secao 4): credenciais nunca no codigo. A unica
fonte e o ambiente / arquivo .env, e a aplicacao falha no boot se a conexao
nao estiver definida.

Escopo: somente o que a Fase 1 realmente le. Chaves de fases posteriores
(modelo, detector, threshold) entram quando houver codigo que as consuma.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sem default: ausencia e erro de boot, nao um fallback silencioso.
    database_url: str
    test_database_url: str | None = None

    app_timezone: str = "America/Sao_Paulo"
    storage_dir: Path = PROJECT_ROOT / "storage" / "faces"

    @field_validator("database_url", "test_database_url")
    @classmethod
    def _exigir_driver_postgres(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        if not valor.startswith("postgresql"):
            raise ValueError(
                "A URL deve apontar para PostgreSQL "
                "(ex.: postgresql+psycopg://user:senha@host:5432/banco)."
            )
        return valor

    @field_validator("app_timezone")
    @classmethod
    def _exigir_timezone_valido(cls, valor: str) -> str:
        try:
            ZoneInfo(valor)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"APP_TIMEZONE desconhecido: {valor!r}") from exc
        return valor

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
