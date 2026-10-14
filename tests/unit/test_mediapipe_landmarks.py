"""Contratos leves dos DTOs e import opcional do provider visual."""

from __future__ import annotations

import builtins
import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import pytest

from src.domain.services.facial_landmarks import PontoFacial, ResultadoLandmarks

CAMINHO = "src.infrastructure.face_recognition.mediapipe_landmarks"


def test_dtos_de_landmarks_sao_imutaveis() -> None:
    ponto = PontoFacial(0.5, 0.25, -0.1)
    resultado = ResultadoLandmarks(rostos=((ponto,),), conexoes=((0, 0),))

    with pytest.raises(FrozenInstanceError):
        ponto.x = 0.0
    with pytest.raises(FrozenInstanceError):
        resultado.rostos = ()


def test_importar_provider_nao_importa_mediapipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = builtins.__import__
    imports: list[str] = []

    def observar(nome: str, *args: Any, **kwargs: Any) -> Any:
        if nome.startswith("mediapipe"):
            imports.append(nome)
            raise AssertionError("MediaPipe deve permanecer no processo auxiliar")
        return original(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", observar)
    monkeypatch.delitem(importlib.sys.modules, CAMINHO, raising=False)

    importlib.import_module(CAMINHO)

    assert imports == []


def test_modelo_ausente_falha_sem_carregar_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    modulo = importlib.import_module(CAMINHO)
    importador_original = modulo.importlib.import_module

    def impedir_runtime(nome: str, *args: Any, **kwargs: Any) -> Any:
        if nome == "cv2" or nome.startswith("mediapipe"):
            raise AssertionError("runtime nao deve carregar sem modelo")
        return importador_original(nome, *args, **kwargs)

    monkeypatch.setattr(modulo.importlib, "import_module", impedir_runtime)

    with pytest.raises(FileNotFoundError, match="Modelo de landmarks"):
        modulo.MediaPipeLandmarks(tmp_path / "ausente.task")
