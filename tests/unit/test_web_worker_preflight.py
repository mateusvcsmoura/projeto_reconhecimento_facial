from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts import web_worker_preflight


def _criar_modelos_deepface(raiz: Path) -> None:
    pesos = raiz / ".deepface" / "weights"
    pesos.mkdir(parents=True)
    for nome in (
        "facenet512_weights.h5",
        "2.7_80x80_MiniFASNetV2.pth",
        "4_0_0_80x80_MiniFASNetV1SE.pth",
    ):
        (pesos / nome).write_bytes(b"modelo-sintetico")


def test_preflight_aceita_somente_modelos_locais_legiveis(
    monkeypatch: Any, tmp_path: Path
) -> None:
    deepface_home = tmp_path / "home"
    model_path = tmp_path / "face_landmarker.task"
    _criar_modelos_deepface(deepface_home)
    model_path.write_bytes(b"modelo-sintetico")
    monkeypatch.setenv("DEEPFACE_HOME", str(deepface_home))
    monkeypatch.setenv("WEB_MEDIAPIPE_MODEL_PATH", str(model_path))

    assert web_worker_preflight.arquivos_de_modelo_ausentes() == ()


def test_preflight_lista_modelos_ausentes_sem_expor_caminhos(
    monkeypatch: Any, tmp_path: Path
) -> None:
    monkeypatch.setenv("DEEPFACE_HOME", str(tmp_path / "inexistente"))
    monkeypatch.delenv("WEB_MEDIAPIPE_MODEL_PATH", raising=False)

    ausentes = web_worker_preflight.arquivos_de_modelo_ausentes()

    assert ausentes == (
        "facenet512_weights.h5",
        "2.7_80x80_MiniFASNetV2.pth",
        "4_0_0_80x80_MiniFASNetV1SE.pth",
        "WEB_MEDIAPIPE_MODEL_PATH",
    )
    assert all(str(tmp_path) not in nome for nome in ausentes)
