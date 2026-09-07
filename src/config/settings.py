"""Configuracao lida do ambiente.

Regra do projeto (CLAUDE.md secao 4): credenciais nunca no codigo. A unica
fonte e o ambiente / arquivo .env, e a aplicacao falha no boot se a conexao
nao estiver definida.

Escopo: somente chaves que algum modulo realmente le. Nada de
configuracao morta.
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

    log_level: str = "INFO"

    # Camera e reconhecimento -- eram constantes no topo do cadastro.py.
    camera_index: int = 0
    face_model: str = "Facenet512"
    face_detector: str = "opencv"

    # Distancia cosseno maxima para considerar duas faces a mesma pessoa.
    # 0.30 e o limiar que o DeepFace usa para (Facenet512, cosine). Ate a
    # Fase 7 calibrar este numero com FAR/FRR sobre dados reais, ele e uma
    # heranca da biblioteca -- agora ao menos explicita e ajustavel.
    face_threshold: float = 0.30

    # Recusa frames que o detector classifique como apresentacao (foto
    # impressa, tela de celular). Sem isto, um controle de presenca por
    # rosto nao entrega a garantia que promete (problema A7).
    face_anti_spoofing: bool = True

    # Retencao de presencas, em dias. 0 desliga o expurgo.
    # Dado pessoal nao deve ser guardado por mais tempo do que a finalidade
    # exige (LGPD art. 15/16). 1825 dias = 5 anos, prazo tipico de guarda
    # de registro academico.
    retencao_presencas_dias: int = 1825

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

    @field_validator("log_level")
    @classmethod
    def _exigir_nivel_de_log_valido(cls, valor: str) -> str:
        nivel = valor.strip().upper()
        validos = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if nivel not in validos:
            raise ValueError(
                f"LOG_LEVEL invalido: {valor!r}. Use um de {sorted(validos)}."
            )
        return nivel

    @field_validator("face_threshold")
    @classmethod
    def _exigir_limiar_valido(cls, valor: float) -> float:
        # Distancia cosseno entre vetores normalizados vive em [0, 2].
        if not 0.0 < valor <= 2.0:
            raise ValueError(
                f"FACE_THRESHOLD deve estar em (0, 2]; recebido {valor}."
            )
        return valor

    @field_validator("retencao_presencas_dias")
    @classmethod
    def _exigir_retencao_valida(cls, valor: int) -> int:
        if valor < 0:
            raise ValueError("RETENCAO_PRESENCAS_DIAS nao pode ser negativo.")
        return valor

    @field_validator("camera_index")
    @classmethod
    def _exigir_indice_de_camera_valido(cls, valor: int) -> int:
        if valor < 0:
            raise ValueError("CAMERA_INDEX nao pode ser negativo.")
        return valor

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
