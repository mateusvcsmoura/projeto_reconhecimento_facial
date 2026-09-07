"""Fase 7 -- camera OpenCV, com cv2 dublado.

Este modulo estava em 0% de cobertura desde a Fase 2, porque o OpenCV nao
esta instalado neste ambiente. Injetar um duble em sys.modules permite
exercitar a logica que e nossa -- abrir, falhar, ler e sobretudo LIBERAR --
sem hardware e sem a biblioteca.
"""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest

from src.domain.errors import CameraIndisponivel, FalhaNaLeituraDaCamera

CAMINHO = "src.infrastructure.camera.opencv_camera"


class CapturaDuble:
    def __init__(self, indice: int) -> None:
        self.indice = indice
        self.aberta = True
        self.liberada = False
        self.frames: list[Any] = []
        self.falhar_leitura = False

    def isOpened(self) -> bool:
        return self.aberta

    def read(self) -> tuple[bool, Any]:
        if self.falhar_leitura or not self.frames:
            return False, None
        return True, self.frames.pop(0)

    def release(self) -> None:
        self.liberada = True
        self.aberta = False


class Cv2Duble:
    def __init__(self) -> None:
        self.ultima_captura: CapturaDuble | None = None
        self.abrir_com_sucesso = True
        self.frames: list[Any] = []

    def VideoCapture(self, indice: int) -> CapturaDuble:
        captura = CapturaDuble(indice)
        captura.aberta = self.abrir_com_sucesso
        captura.frames = list(self.frames)
        self.ultima_captura = captura
        return captura


@pytest.fixture
def cv2_duble() -> Iterator[Cv2Duble]:
    falso = Cv2Duble()
    modulo = types.ModuleType("cv2")
    for nome in dir(falso):
        if not nome.startswith("_"):
            setattr(modulo, nome, getattr(falso, nome))

    original = sys.modules.get("cv2")
    sys.modules["cv2"] = modulo
    sys.modules.pop(CAMINHO, None)
    try:
        yield falso
    finally:
        sys.modules.pop(CAMINHO, None)
        if original is None:
            sys.modules.pop("cv2", None)
        else:
            sys.modules["cv2"] = original


def montar(indice: int = 0) -> Any:
    return importlib.import_module(CAMINHO).OpenCVCamera(indice)


def test_camera_indisponivel_falha_com_erro_de_dominio(cv2_duble: Cv2Duble) -> None:
    cv2_duble.abrir_com_sucesso = False

    with pytest.raises(CameraIndisponivel) as capturado, montar(indice=3):
        pass

    assert capturado.value.indice == 3


def test_dispositivo_e_liberado_mesmo_quando_a_abertura_falha(
    cv2_duble: Cv2Duble,
) -> None:
    """Sem release aqui, o indice fica preso ate reiniciar o processo."""
    cv2_duble.abrir_com_sucesso = False

    with pytest.raises(CameraIndisponivel), montar():
        pass

    assert cv2_duble.ultima_captura is not None
    assert cv2_duble.ultima_captura.liberada is True


def test_le_frames_em_sequencia(cv2_duble: Cv2Duble) -> None:
    cv2_duble.frames = ["frame-1", "frame-2"]

    with montar() as camera:
        assert camera.ler_frame() == "frame-1"
        assert camera.ler_frame() == "frame-2"


def test_falha_de_leitura_vira_erro_de_dominio(cv2_duble: Cv2Duble) -> None:
    cv2_duble.frames = []

    with montar() as camera, pytest.raises(FalhaNaLeituraDaCamera):
        camera.ler_frame()


def test_ler_sem_abrir_e_recusado(cv2_duble: Cv2Duble) -> None:
    camera = montar()

    with pytest.raises(FalhaNaLeituraDaCamera, match="nao foi aberta"):
        camera.ler_frame()


def test_dispositivo_e_liberado_na_saida_normal(cv2_duble: Cv2Duble) -> None:
    cv2_duble.frames = ["f"]

    with montar() as camera:
        camera.ler_frame()

    assert cv2_duble.ultima_captura is not None
    assert cv2_duble.ultima_captura.liberada is True


def test_dispositivo_e_liberado_quando_o_corpo_levanta(
    cv2_duble: Cv2Duble,
) -> None:
    """Problema A17: o prototipo vazava o dispositivo em caso de excecao."""
    cv2_duble.frames = ["f"]

    with pytest.raises(RuntimeError), montar() as camera:
        camera.ler_frame()
        raise RuntimeError("erro no meio do laco")

    assert cv2_duble.ultima_captura is not None
    assert cv2_duble.ultima_captura.liberada is True


def test_ler_depois_de_sair_do_contexto_e_recusado(cv2_duble: Cv2Duble) -> None:
    cv2_duble.frames = ["f"]

    with montar() as camera:
        camera.ler_frame()

    with pytest.raises(FalhaNaLeituraDaCamera):
        camera.ler_frame()
