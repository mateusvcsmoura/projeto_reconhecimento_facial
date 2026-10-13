"""Fase 7 -- janela de video, com cv2 dublado."""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from src.presentation.cli.teclas import BRANCO, ESC, VERDE

CAMINHO = "src.presentation.cli.viewer"


class Cv2Duble:
    FONT_HERSHEY_SIMPLEX = 0
    WINDOW_NORMAL = 16

    def __init__(self) -> None:
        self.janelas_criadas: list[tuple[str, int]] = []
        self.redimensionamentos: list[tuple[str, int, int]] = []
        self.textos: list[tuple[str, tuple[int, int], tuple[int, int, int]]] = []
        self.exibicoes: list[str] = []
        self.frames_exibidos: list[Any] = []
        self.janelas_fechadas: list[str] = []
        self.teclas: list[int] = []

    def putText(
        self,
        frame: Any,
        texto: str,
        origem: tuple[int, int],
        fonte: Any,
        escala: float,
        cor: tuple[int, int, int],
        espessura: int,
    ) -> None:
        self.textos.append((texto, origem, cor))
        frame[0, 0] = (255, 1, 2)

    def imshow(self, titulo: str, frame: Any) -> None:
        self.exibicoes.append(titulo)
        self.frames_exibidos.append(frame)

    def waitKey(self, atraso: int) -> int:
        return self.teclas.pop(0) if self.teclas else -1

    def namedWindow(self, titulo: str, flag: int) -> None:
        self.janelas_criadas.append((titulo, flag))

    def resizeWindow(self, titulo: str, largura: int, altura: int) -> None:
        self.redimensionamentos.append((titulo, largura, altura))

    def destroyWindow(self, titulo: str) -> None:
        self.janelas_fechadas.append(titulo)


@pytest.fixture
def cv2_duble() -> Iterator[Cv2Duble]:
    falso = Cv2Duble()
    modulo = types.ModuleType("cv2")
    modulo.FONT_HERSHEY_SIMPLEX = Cv2Duble.FONT_HERSHEY_SIMPLEX  # type: ignore[attr-defined]
    modulo.WINDOW_NORMAL = Cv2Duble.WINDOW_NORMAL  # type: ignore[attr-defined]
    for nome in (
        "putText",
        "imshow",
        "waitKey",
        "destroyWindow",
        "namedWindow",
        "resizeWindow",
    ):
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


def montar(titulo: str = "Teste") -> Any:
    return importlib.import_module(CAMINHO).JanelaDeVideo(titulo)


def frame_sintetico() -> np.ndarray:
    return np.zeros((8, 8, 3), dtype=np.uint8)


def test_mostrar_devolve_a_tecla_pressionada(cv2_duble: Cv2Duble) -> None:
    cv2_duble.teclas = [ESC]

    with montar() as janela:
        assert janela.mostrar(frame_sintetico(), []) == ESC


def test_tecla_e_mascarada_para_um_byte(cv2_duble: Cv2Duble) -> None:
    """waitKey devolve mais que 8 bits em algumas plataformas."""
    cv2_duble.teclas = [0xFF00 | ESC]

    with montar() as janela:
        assert janela.mostrar(frame_sintetico(), []) == ESC


def test_linhas_sao_desenhadas_em_ordem_e_espacadas(cv2_duble: Cv2Duble) -> None:
    cv2_duble.teclas = [-1]

    with montar() as janela:
        janela.mostrar(frame_sintetico(), [("primeira", VERDE), ("segunda", BRANCO)])

    textos = [t for t, _, _ in cv2_duble.textos]
    alturas = [origem[1] for _, origem, _ in cv2_duble.textos]

    assert textos == ["primeira", "segunda"]
    assert alturas[1] > alturas[0]


def test_cor_recebida_e_a_cor_usada(cv2_duble: Cv2Duble) -> None:
    cv2_duble.teclas = [-1]

    with montar() as janela:
        janela.mostrar(frame_sintetico(), [("verde", VERDE)])

    assert cv2_duble.textos[0][2] == VERDE


def test_frame_e_exibido_com_o_titulo_da_janela(cv2_duble: Cv2Duble) -> None:
    cv2_duble.teclas = [-1]

    with montar("Reconhecimento") as janela:
        janela.mostrar(frame_sintetico(), [])

    assert cv2_duble.exibicoes == ["Reconhecimento"]


def test_janela_e_fechada_na_saida(cv2_duble: Cv2Duble) -> None:
    with montar("Cadastro facial"):
        pass

    assert cv2_duble.janelas_fechadas == ["Cadastro facial"]


def test_janela_e_fechada_quando_o_corpo_levanta(cv2_duble: Cv2Duble) -> None:
    with pytest.raises(RuntimeError), montar("Cadastro facial"):
        raise RuntimeError("erro no laco")

    assert cv2_duble.janelas_fechadas == ["Cadastro facial"]


def test_sem_linhas_nada_e_desenhado(cv2_duble: Cv2Duble) -> None:
    cv2_duble.teclas = [-1]

    with montar() as janela:
        janela.mostrar(frame_sintetico(), [])

    assert cv2_duble.textos == []


def test_janela_e_criada_redimensionavel(cv2_duble: Cv2Duble) -> None:
    """Com WINDOW_AUTOSIZE, maximizar so aumenta a moldura: o video fica
    no tamanho nativo, encolhido num canto."""
    with montar("Cadastro facial"):
        pass

    assert cv2_duble.janelas_criadas == [("Cadastro facial", Cv2Duble.WINDOW_NORMAL)]


def test_janela_abre_no_tamanho_pedido(cv2_duble: Cv2Duble) -> None:
    modulo = importlib.import_module(CAMINHO)
    with modulo.JanelaDeVideo("Teste", largura=1024, altura=576):
        pass

    assert cv2_duble.redimensionamentos == [("Teste", 1024, 576)]


def test_overlay_e_desenhado_em_copia_do_frame(cv2_duble: Cv2Duble) -> None:
    cv2_duble.teclas = [-1]
    original = frame_sintetico()
    pixels_originais = original.copy()

    with montar() as janela:
        janela.mostrar(original, [("orientacao", VERDE)])

    np.testing.assert_array_equal(original, pixels_originais)
    assert cv2_duble.frames_exibidos[0] is not original
    assert tuple(cv2_duble.frames_exibidos[0][0, 0]) == (255, 1, 2)
