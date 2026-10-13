"""Composicao da politica optativa sem construir engine ou abrir conexao."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from src.config.settings import Settings
from src.domain.services.qualidade_captura import ParametrosQualidade
from tests.fakes import FakeFaceRecognition

URL_VALIDA = "postgresql+psycopg://u:p@h:5432/d"


def _carregar_main_com_deepface_falso() -> Any:
    nomes = (
        "src.main",
        "src.infrastructure.face_recognition.deepface_adapter",
        "src.infrastructure.camera.opencv_camera",
        "src.infrastructure.storage.local_image_storage",
        "src.presentation.cli.viewer",
    )
    anteriores = {nome: sys.modules.pop(nome, None) for nome in nomes}
    deepface_anterior = sys.modules.get("deepface")
    cv2_anterior = sys.modules.get("cv2")
    modulo = types.ModuleType("deepface")
    modulo.DeepFace = object()  # type: ignore[attr-defined]
    sys.modules["deepface"] = modulo
    cv2_falso = types.ModuleType("cv2")
    cv2_falso.FONT_HERSHEY_SIMPLEX = 0  # type: ignore[attr-defined]
    cv2_falso.WINDOW_NORMAL = 16  # type: ignore[attr-defined]
    sys.modules["cv2"] = cv2_falso
    try:
        return importlib.import_module("src.main")
    finally:
        for nome in nomes:
            sys.modules.pop(nome, None)
        for nome, anterior in anteriores.items():
            if anterior is not None:
                sys.modules[nome] = anterior
        if deepface_anterior is None:
            sys.modules.pop("deepface", None)
        else:
            sys.modules["deepface"] = deepface_anterior
        if cv2_anterior is None:
            sys.modules.pop("cv2", None)
        else:
            sys.modules["cv2"] = cv2_anterior


@pytest.mark.parametrize(
    ("habilitada", "esperada"),
    [
        (False, None),
        (
            True,
            ParametrosQualidade(
                min_face_px=96,
                min_brightness=35.0,
                max_brightness=225.0,
                min_sharpness=125.0,
            ),
        ),
    ],
)
def test_montar_menu_aplica_configuracao_sem_conectar_ao_banco(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    habilitada: bool,
    esperada: ParametrosQualidade | None,
) -> None:
    main = _carregar_main_com_deepface_falso()
    recebido: dict[str, Any] = {}

    class AdaptadorEspiao(FakeFaceRecognition):
        def __init__(self, **kwargs: Any) -> None:
            recebido.update(kwargs)

    monkeypatch.setattr(main, "criar_engine", lambda _url: object())
    monkeypatch.setattr(main, "PostgresAlunoRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresPresencaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "LocalImageStorage", lambda _raiz: object())
    monkeypatch.setattr(main, "DeepFaceAdapter", AdaptadorEspiao)
    monkeypatch.setattr(main, "JanelaDeVideo", lambda _titulo: object())

    valores: dict[str, Any] = {
        "_env_file": None,
        "database_url": URL_VALIDA,
        "storage_dir": tmp_path,
        "face_quality_enabled": habilitada,
        "face_anti_spoofing": True,
    }
    if habilitada:
        valores.update(
            face_quality_min_face_px=96,
            face_quality_min_brightness=35.0,
            face_quality_max_brightness=225.0,
            face_quality_min_sharpness=125.0,
        )
    main.montar_menu(Settings(**valores))

    assert recebido.get("qualidade") == esperada
