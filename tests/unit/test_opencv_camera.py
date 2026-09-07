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
from unittest import mock

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
        # A camera aceita o que for pedido, por padrao.
        self.propriedades: dict[int, float] = {}
        self.resolucao_forcada: tuple[int, int] | None = None

    def set(self, prop: int, valor: float) -> bool:
        self.propriedades[prop] = valor
        return True

    def get(self, prop: int) -> float:
        if self.resolucao_forcada is not None:
            largura, altura = self.resolucao_forcada
            return float(largura if prop == Cv2Duble.CAP_PROP_FRAME_WIDTH else altura)
        return self.propriedades.get(prop, 0.0)

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
    CAP_PROP_FRAME_WIDTH = 3
    CAP_PROP_FRAME_HEIGHT = 4
    CAP_ANY = 0
    CAP_DSHOW = 700
    CAP_MSMF = 1400

    def __init__(self) -> None:
        self.ultima_captura: CapturaDuble | None = None
        self.abrir_com_sucesso = True
        self.frames: list[Any] = []
        self.resolucao_forcada: tuple[int, int] | None = None
        self.backends_usados: list[int] = []

    def VideoCapture(
        self, indice: int, backend: int = 0
    ) -> CapturaDuble:
        self.backends_usados.append(backend)
        captura = CapturaDuble(indice)
        captura.aberta = self.abrir_com_sucesso
        captura.frames = list(self.frames)
        captura.resolucao_forcada = self.resolucao_forcada
        self.ultima_captura = captura
        return captura


@pytest.fixture
def cv2_duble() -> Iterator[Cv2Duble]:
    falso = Cv2Duble()
    modulo = types.ModuleType("cv2")
    modulo.CAP_PROP_FRAME_WIDTH = Cv2Duble.CAP_PROP_FRAME_WIDTH  # type: ignore[attr-defined]
    modulo.CAP_PROP_FRAME_HEIGHT = Cv2Duble.CAP_PROP_FRAME_HEIGHT  # type: ignore[attr-defined]
    for constante in ("CAP_ANY", "CAP_DSHOW", "CAP_MSMF"):
        setattr(modulo, constante, getattr(Cv2Duble, constante))
    modulo.VideoCapture = falso.VideoCapture  # type: ignore[attr-defined]

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


def montar(
    indice: int = 0,
    largura: int = 1280,
    altura: int = 720,
    backend: str = "auto",
) -> Any:
    return importlib.import_module(CAMINHO).OpenCVCamera(
        indice, largura=largura, altura=altura, backend=backend
    )


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


def test_resolucao_pedida_e_aplicada_na_camera(cv2_duble: Cv2Duble) -> None:
    """O padrao do OpenCV costuma ser 640x480, pequeno demais para o rosto."""
    cv2_duble.frames = ["f"]

    with montar(largura=1280, altura=720):
        pass

    captura = cv2_duble.ultima_captura
    assert captura is not None
    assert captura.propriedades[Cv2Duble.CAP_PROP_FRAME_WIDTH] == 1280
    assert captura.propriedades[Cv2Duble.CAP_PROP_FRAME_HEIGHT] == 720


def test_camera_que_entrega_resolucao_menor_gera_aviso(
    cv2_duble: Cv2Duble, caplog: Any
) -> None:
    """Nem toda camera aceita o pedido; o operador precisa saber."""
    import logging

    cv2_duble.resolucao_forcada = (640, 480)
    cv2_duble.frames = ["f"]

    with caplog.at_level(logging.WARNING), montar(largura=1280, altura=720):
        pass

    assert "640" in caplog.text
    assert "1280" in caplog.text


# -- backend de captura ----------------------------------------------------


def test_auto_escolhe_directshow_no_windows(cv2_duble: Cv2Duble) -> None:
    """Medido: MSMF leva ~10 s para abrir; DirectShow, menos de 1 s."""
    modulo = importlib.import_module(CAMINHO)
    with mock.patch.object(modulo.sys, "platform", "win32"):
        cv2_duble.frames = ["f"]
        with montar(backend="auto"):
            pass

    assert cv2_duble.backends_usados == [Cv2Duble.CAP_DSHOW]


def test_auto_deixa_o_opencv_escolher_fora_do_windows(
    cv2_duble: Cv2Duble,
) -> None:
    """DirectShow so existe no Windows."""
    modulo = importlib.import_module(CAMINHO)
    with mock.patch.object(modulo.sys, "platform", "linux"):
        cv2_duble.frames = ["f"]
        with montar(backend="auto"):
            pass

    assert cv2_duble.backends_usados == [Cv2Duble.CAP_ANY]


def test_backend_explicito_e_respeitado(cv2_duble: Cv2Duble) -> None:
    cv2_duble.frames = ["f"]

    with montar(backend="msmf"):
        pass

    assert cv2_duble.backends_usados == [Cv2Duble.CAP_MSMF]
