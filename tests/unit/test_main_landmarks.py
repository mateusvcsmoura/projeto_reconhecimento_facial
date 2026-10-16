"""Composição optativa dos landmarks sem banco, câmera ou modelo."""

from __future__ import annotations

import builtins
import sys
import types
from pathlib import Path
from typing import Any, ClassVar

import pytest

from src.config.settings import Settings
from src.domain.entities.turma import Periodo, Turma
from tests.unit.test_main_qualidade import _carregar_main_com_deepface_falso

URL_VALIDA = "postgresql+psycopg://u:p@h:5432/d"
CAMINHO_PROVIDER = "src.infrastructure.face_recognition.mediapipe_landmarks"


class MenuEspiao:
    instancias: ClassVar[list[MenuEspiao]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.instancias.append(self)

    def executar(self) -> None:
        pass


class JanelaEspiao:
    def __init__(self, titulo: str, **kwargs: Any) -> None:
        self.titulo = titulo
        self.kwargs = kwargs


def montar_com_settings(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> tuple[Any, list[JanelaEspiao]]:
    main = _carregar_main_com_deepface_falso()
    janelas: list[JanelaEspiao] = []

    monkeypatch.setattr(main, "criar_engine", lambda _url: object())
    monkeypatch.setattr(main, "PostgresAlunoRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresPresencaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "PostgresTurmaRepository", lambda _engine: object())
    monkeypatch.setattr(main, "LocalImageStorage", lambda _raiz: object())
    monkeypatch.setattr(main, "DeepFaceAdapter", lambda **_kwargs: object())
    monkeypatch.setattr(main, "MenuCLI", MenuEspiao)

    def criar_janela(titulo: str, **kwargs: Any) -> JanelaEspiao:
        janela = JanelaEspiao(titulo, **kwargs)
        janelas.append(janela)
        return janela

    monkeypatch.setattr(main, "JanelaDeVideo", criar_janela)
    MenuEspiao.instancias.clear()
    menu = main.montar_menu(settings)
    menu._abrir_turma(Turma(id=1, materia="IA", periodo=Periodo.DIURNO))
    return MenuEspiao.instancias[-1], janelas


def test_flag_desligada_nao_importa_provider_nem_injeta_factory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    original = builtins.__import__

    def impedir_provider(nome: str, *args: Any, **kwargs: Any) -> Any:
        if nome == CAMINHO_PROVIDER:
            raise AssertionError("provider nao pode ser importado com flag false")
        return original(nome, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", impedir_provider)
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        storage_dir=tmp_path,
        face_landmarks_enabled=False,
    )

    menu, janelas = montar_com_settings(monkeypatch, settings)
    janela = menu.kwargs["abrir_janela"]("Cadastro facial")

    assert janela.kwargs == {}
    assert janelas == [janela]


def test_flag_true_injeta_provider_somente_na_janela_de_cadastro(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    caminho = tmp_path / "face_landmarker.task"
    python_path = tmp_path / "landmarks" / "python.exe"
    instancias: list[tuple[Path, Path]] = []
    modulo_provider = types.ModuleType(CAMINHO_PROVIDER)

    class ProviderFalso:
        def __init__(self, model_path: Path, python_executable: Path) -> None:
            instancias.append((model_path, python_executable))

    modulo_provider.MediaPipeLandmarks = ProviderFalso  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, CAMINHO_PROVIDER, modulo_provider)
    settings = Settings(
        _env_file=None,
        database_url=URL_VALIDA,
        storage_dir=tmp_path,
        face_landmarks_enabled=True,
        face_landmarks_model_path=caminho,
        face_landmarks_python_path=python_path,
    )

    menu, janelas = montar_com_settings(monkeypatch, settings)
    abrir_janela = menu.kwargs["abrir_janela"]
    reconhecimento = abrir_janela("Reconhecimento")
    cadastro = abrir_janela("Cadastro facial")

    assert reconhecimento.kwargs == {}
    assert "criar_landmarks" in cadastro.kwargs
    assert callable(cadastro.kwargs["criar_landmarks"])
    assert instancias == []

    provider = cadastro.kwargs["criar_landmarks"]()

    assert isinstance(provider, ProviderFalso)
    assert instancias == [(caminho, python_path)]

    cadastro_reaberto = abrir_janela("Cadastro facial")
    provider_reaberto = cadastro_reaberto.kwargs["criar_landmarks"]()

    assert isinstance(provider_reaberto, ProviderFalso)
    assert provider_reaberto is not provider
    assert instancias == [(caminho, python_path), (caminho, python_path)]
    assert [janela.titulo for janela in janelas] == [
        "Reconhecimento",
        "Cadastro facial",
        "Cadastro facial",
    ]
