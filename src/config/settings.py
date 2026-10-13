"""Configuracao lida do ambiente.

Regra do projeto (CLAUDE.md secao 4): credenciais nunca no codigo. A unica
fonte e o ambiente / arquivo .env, e a aplicacao falha no boot se a conexao
nao estiver definida.

Escopo: somente chaves que algum modulo realmente le. Nada de
configuracao morta.
"""

from __future__ import annotations

from functools import lru_cache
from math import isfinite
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator, model_validator
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

    # Resolucao pedida a camera. O padrao do OpenCV costuma ser 640x480, o
    # que produz um recorte de rosto pequeno -- e o modelo de anti-spoofing
    # e sensivel ao tamanho e a nitidez desse recorte.
    # A camera pode recusar e entregar a resolucao mais proxima que suporta.
    camera_largura: int = 1280
    camera_altura: int = 720

    # Backend de captura do OpenCV.
    #   auto   -- DirectShow no Windows, padrao do sistema nos demais
    #   dshow  -- DirectShow (Windows)
    #   msmf   -- Media Foundation (Windows)
    #   any    -- deixa o OpenCV escolher
    #
    # Medido nesta maquina: MSMF leva ~10 s para abrir e ~18 s para aceitar
    # a resolucao; DirectShow faz as duas coisas em menos de 1 s.
    camera_backend: str = "auto"
    face_model: str = "Facenet512"
    face_detector: str = "opencv"

    # Distancia cosseno maxima para considerar duas faces a mesma pessoa.
    # 0.30 e o limiar que o DeepFace usa para (Facenet512, cosine). Ate a
    # Fase 7 calibrar este numero com FAR/FRR sobre dados reais, ele e uma
    # heranca da biblioteca -- agora ao menos explicita e ajustavel.
    face_threshold: float = 0.30

    # Heuristicas optativas de qualidade. Os valores nao foram calibrados
    # com rostos e a politica fica desabilitada para preservar o baseline.
    face_quality_enabled: bool = False
    face_quality_min_face_px: int = 80
    face_quality_min_brightness: float = 40.0
    face_quality_max_brightness: float = 215.0
    face_quality_min_sharpness: float = 100.0

    # Validacao temporal optativa para exigir observacoes consecutivas.
    # Os limites iniciais sao de engenharia, sem calibracao biometrica.
    face_temporal_enabled: bool = False
    face_temporal_min_observations: int = 3
    face_temporal_window_seconds: float = 5.0
    face_temporal_max_age_seconds: float = 2.0

    # A politica de margem e optativa e nao foi calibrada com dados
    # biometricos autorizados. Ao habilitar, a margem deve ser escolhida
    # explicitamente pelo ambiente, inclusive 0.0 para recusar so empates.
    face_ambiguity_enabled: bool = False
    face_ambiguity_min_margin: float | None = None

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
            raise ValueError(f"FACE_THRESHOLD deve estar em (0, 2]; recebido {valor}.")
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

    @field_validator("camera_backend")
    @classmethod
    def _exigir_backend_conhecido(cls, valor: str) -> str:
        backend = valor.strip().lower()
        validos = {"auto", "dshow", "msmf", "any"}
        if backend not in validos:
            raise ValueError(
                f"CAMERA_BACKEND invalido: {valor!r}. Use um de {sorted(validos)}."
            )
        return backend

    @field_validator("camera_largura", "camera_altura")
    @classmethod
    def _exigir_resolucao_valida(cls, valor: int) -> int:
        if valor < 160:
            raise ValueError(
                "Resolucao de camera abaixo de 160 px nao serve para "
                "reconhecimento facial."
            )
        return valor

    @field_validator("face_quality_min_face_px", mode="before")
    @classmethod
    def _rejeitar_booleano_como_tamanho_de_face(cls, valor: object) -> object:
        if isinstance(valor, bool):
            raise ValueError("FACE_QUALITY_MIN_FACE_PX deve ser um inteiro >= 3.")
        return valor

    @field_validator("face_quality_min_face_px")
    @classmethod
    def _exigir_tamanho_minimo_de_face(cls, valor: int) -> int:
        if valor < 3:
            raise ValueError("FACE_QUALITY_MIN_FACE_PX deve ser um inteiro >= 3.")
        return valor

    @field_validator("face_quality_min_brightness", "face_quality_max_brightness")
    @classmethod
    def _exigir_brilho_finito(cls, valor: float) -> float:
        if not isfinite(valor) or not 0.0 <= valor <= 255.0:
            raise ValueError("Os limites de brilho devem estar entre 0 e 255.")
        return valor

    @field_validator("face_quality_min_sharpness")
    @classmethod
    def _exigir_nitidez_finita(cls, valor: float) -> float:
        if not isfinite(valor) or valor < 0.0:
            raise ValueError("FACE_QUALITY_MIN_SHARPNESS deve ser finito e >= 0.")
        return valor

    @model_validator(mode="after")
    def _exigir_intervalo_de_brilho_valido(self) -> Settings:
        if self.face_quality_min_brightness >= self.face_quality_max_brightness:
            raise ValueError(
                "FACE_QUALITY_MAX_BRIGHTNESS deve ser maior que "
                "FACE_QUALITY_MIN_BRIGHTNESS."
            )
        return self

    @field_validator("face_temporal_min_observations", mode="before")
    @classmethod
    def _rejeitar_booleano_como_contagem_temporal(cls, valor: object) -> object:
        if isinstance(valor, bool):
            raise ValueError("FACE_TEMPORAL_MIN_OBSERVATIONS deve ser inteiro >= 2.")
        return valor

    @field_validator("face_temporal_min_observations")
    @classmethod
    def _exigir_contagem_temporal_minima(cls, valor: int) -> int:
        if valor < 2:
            raise ValueError("FACE_TEMPORAL_MIN_OBSERVATIONS deve ser inteiro >= 2.")
        return valor

    @field_validator(
        "face_temporal_window_seconds", "face_temporal_max_age_seconds", mode="before"
    )
    @classmethod
    def _rejeitar_booleano_como_tempo_temporal(cls, valor: object) -> object:
        if isinstance(valor, bool):
            raise ValueError("Os tempos temporais devem ser numeros positivos.")
        return valor

    @field_validator("face_temporal_window_seconds", "face_temporal_max_age_seconds")
    @classmethod
    def _exigir_tempo_temporal_finito_positivo(cls, valor: float) -> float:
        if not isfinite(valor) or valor <= 0.0:
            raise ValueError("Os tempos temporais devem ser finitos e positivos.")
        return valor

    @model_validator(mode="after")
    def _exigir_validade_temporal_na_janela(self) -> Settings:
        if self.face_temporal_max_age_seconds > self.face_temporal_window_seconds:
            raise ValueError(
                "FACE_TEMPORAL_MAX_AGE_SECONDS nao pode exceder "
                "FACE_TEMPORAL_WINDOW_SECONDS."
            )
        return self

    @field_validator("face_ambiguity_min_margin", mode="before")
    @classmethod
    def _validar_formato_da_margem_de_ambiguidade(cls, valor: object) -> object:
        if valor is None:
            return None
        if isinstance(valor, bool):
            raise ValueError(
                "FACE_AMBIGUITY_MIN_MARGIN deve ser um numero finito entre 0 e 2."
            )
        if isinstance(valor, str):
            if not valor.strip():
                raise ValueError(
                    "FACE_AMBIGUITY_MIN_MARGIN nao pode estar vazia; informe um "
                    "numero entre 0 e 2."
                )
            try:
                float(valor)
            except ValueError as exc:
                raise ValueError(
                    "FACE_AMBIGUITY_MIN_MARGIN deve ser um numero entre 0 e 2."
                ) from exc
        return valor

    @field_validator("face_ambiguity_min_margin")
    @classmethod
    def _exigir_margem_de_ambiguidade_valida(cls, valor: float | None) -> float | None:
        if valor is not None and (not isfinite(valor) or not 0.0 <= valor <= 2.0):
            raise ValueError(
                "FACE_AMBIGUITY_MIN_MARGIN deve ser finita e estar entre 0 e 2."
            )
        return valor

    @model_validator(mode="after")
    def _exigir_margem_quando_ambiguidade_ativa(self) -> Settings:
        if self.face_ambiguity_enabled and self.face_ambiguity_min_margin is None:
            raise ValueError(
                "FACE_AMBIGUITY_MIN_MARGIN e obrigatoria quando "
                "FACE_AMBIGUITY_ENABLED=true; informe um valor explicito entre 0 e 2."
            )
        return self

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.app_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
