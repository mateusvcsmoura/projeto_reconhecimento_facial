"""Fase 7 -- janela de video, com cv2 dublado."""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from src.domain.services.facial_landmarks import PontoFacial, ResultadoLandmarks
from src.presentation.cli.teclas import BRANCO, ESC, VERDE

CAMINHO = "src.presentation.cli.viewer"


class Cv2Duble:
    FONT_HERSHEY_SIMPLEX = 0
    WINDOW_NORMAL = 16
    LINE_8 = 8

    def __init__(self) -> None:
        self.janelas_criadas: list[tuple[str, int]] = []
        self.redimensionamentos: list[tuple[str, int, int]] = []
        self.textos: list[tuple[str, tuple[int, int], tuple[int, int, int]]] = []
        self.exibicoes: list[str] = []
        self.frames_exibidos: list[Any] = []
        self.janelas_fechadas: list[str] = []
        self.teclas: list[int] = []
        self.desenhos: list[tuple[str, str]] = []
        self.erro_redimensionamento: Exception | None = None

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
        self.desenhos.append(("texto", texto))
        frame[0, 0] = (255, 1, 2)

    def line(
        self,
        _frame: Any,
        _inicio: tuple[int, int],
        _fim: tuple[int, int],
        _cor: tuple[int, int, int],
        _espessura: int,
        _tipo_linha: int,
    ) -> None:
        self.desenhos.append(("linha", ""))

    def circle(
        self,
        _frame: Any,
        _centro: tuple[int, int],
        _raio: int,
        _cor: tuple[int, int, int],
        _espessura: int,
        _tipo_linha: int,
    ) -> None:
        self.desenhos.append(("ponto", ""))

    def imshow(self, titulo: str, frame: Any) -> None:
        self.exibicoes.append(titulo)
        self.frames_exibidos.append(frame)

    def waitKey(self, atraso: int) -> int:
        return self.teclas.pop(0) if self.teclas else -1

    def namedWindow(self, titulo: str, flag: int) -> None:
        self.janelas_criadas.append((titulo, flag))

    def resizeWindow(self, titulo: str, largura: int, altura: int) -> None:
        if self.erro_redimensionamento is not None:
            raise self.erro_redimensionamento
        self.redimensionamentos.append((titulo, largura, altura))

    def destroyWindow(self, titulo: str) -> None:
        self.janelas_fechadas.append(titulo)


@pytest.fixture
def cv2_duble() -> Iterator[Cv2Duble]:
    falso = Cv2Duble()
    modulo = types.ModuleType("cv2")
    modulo.FONT_HERSHEY_SIMPLEX = Cv2Duble.FONT_HERSHEY_SIMPLEX  # type: ignore[attr-defined]
    modulo.WINDOW_NORMAL = Cv2Duble.WINDOW_NORMAL  # type: ignore[attr-defined]
    modulo.LINE_8 = Cv2Duble.LINE_8  # type: ignore[attr-defined]
    for nome in (
        "putText",
        "line",
        "circle",
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


def montar(titulo: str = "Teste", **kwargs: Any) -> Any:
    return importlib.import_module(CAMINHO).JanelaDeVideo(titulo, **kwargs)


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


class ProviderLandmarksFalso:
    def __init__(
        self,
        resultados: list[ResultadoLandmarks] | None = None,
        erro: Exception | None = None,
        erro_ao_fechar: Exception | None = None,
    ) -> None:
        self.resultados = list(resultados or [])
        self.erro = erro
        self.erro_ao_fechar = erro_ao_fechar
        self.frames: list[Any] = []
        self.timestamps: list[int] = []
        self.fechamentos = 0

    def detectar(self, frame: Any, timestamp_ms: int) -> ResultadoLandmarks:
        self.frames.append(frame)
        self.timestamps.append(timestamp_ms)
        if self.erro is not None:
            raise self.erro
        return self.resultados.pop(0)

    def fechar(self) -> None:
        self.fechamentos += 1
        if self.erro_ao_fechar is not None:
            raise self.erro_ao_fechar


def resultado_landmarks(quantidade: int) -> ResultadoLandmarks:
    face = (PontoFacial(0.0, 0.0, 0.0), PontoFacial(1.0, 1.0, 0.0))
    return ResultadoLandmarks(
        rostos=tuple(face for _ in range(quantidade)), conexoes=((0, 1),)
    )


def test_factory_e_criada_na_sessao_e_timestamps_crescem_estritamente(
    cv2_duble: Cv2Duble,
) -> None:
    cv2_duble.teclas = [-1, -1]
    provider = ProviderLandmarksFalso([resultado_landmarks(1), resultado_landmarks(1)])
    chamadas_factory = 0

    def factory() -> ProviderLandmarksFalso:
        nonlocal chamadas_factory
        chamadas_factory += 1
        return provider

    original = frame_sintetico()
    pixels_originais = original.copy()
    janela = montar("Cadastro facial", criar_landmarks=factory, monotonic_ns=lambda: 0)
    assert chamadas_factory == 0

    with janela:
        janela.mostrar(original, [("ESPACO = capturar | ESC = cancelar", VERDE)])
        janela.mostrar(original, [("ESPACO = capturar | ESC = cancelar", VERDE)])

    assert chamadas_factory == 1
    assert len(provider.frames) == 2
    assert all(frame is original for frame in provider.frames)
    assert provider.timestamps == [0, 1]
    assert provider.fechamentos == 1
    np.testing.assert_array_equal(original, pixels_originais)
    assert cv2_duble.desenhos[0][0] in {"linha", "ponto"}
    indice_texto = next(
        i for i, item in enumerate(cv2_duble.desenhos) if item[0] == "texto"
    )
    assert all(tipo != "texto" for tipo, _ in cv2_duble.desenhos[:indice_texto])
    assert cv2_duble.textos[0][0] == "ESPACO = capturar | ESC = cancelar"
    assert cv2_duble.textos[1][0] == "Pontos faciais ativos"
    assert cv2_duble.textos[1][2] == (255, 255, 0)


@pytest.mark.parametrize(
    ("quantidade", "mensagem"),
    [
        (0, "Posicione o rosto na camera"),
        (2, "Mantenha apenas uma pessoa na camera"),
    ],
)
def test_zero_ou_dois_rostos_nao_desenham_malha(
    cv2_duble: Cv2Duble, quantidade: int, mensagem: str
) -> None:
    cv2_duble.teclas = [-1]
    provider = ProviderLandmarksFalso([resultado_landmarks(quantidade)])

    with montar("Cadastro facial", criar_landmarks=lambda: provider) as janela:
        janela.mostrar(frame_sintetico(), [])

    assert cv2_duble.desenhos == [("texto", mensagem)]
    assert cv2_duble.textos[0][2] == (0, 255, 255)


def test_falha_de_inferencia_desativa_provider_sem_reutilizar_resultado(
    cv2_duble: Cv2Duble, caplog: pytest.LogCaptureFixture
) -> None:
    cv2_duble.teclas = [-1, -1]
    provider = ProviderLandmarksFalso(erro=RuntimeError("falha sintetica"))
    janela = montar("Cadastro facial", criar_landmarks=lambda: provider)

    with janela:
        janela.mostrar(frame_sintetico(), [])
        janela.mostrar(frame_sintetico(), [])

    assert len(provider.frames) == 1
    assert provider.fechamentos == 1
    assert [texto for texto, _, _ in cv2_duble.textos] == [
        "Pontos faciais indisponiveis",
        "Pontos faciais indisponiveis",
    ]
    assert (
        sum("landmarks indisponiveis" in record.message for record in caplog.records)
        == 1
    )


def test_factory_com_falha_mantem_captura_disponivel(
    cv2_duble: Cv2Duble, caplog: pytest.LogCaptureFixture
) -> None:
    cv2_duble.teclas = [-1]

    def factory() -> ProviderLandmarksFalso:
        raise FileNotFoundError("modelo ausente")

    with montar("Cadastro facial", criar_landmarks=factory) as janela:
        tecla = janela.mostrar(frame_sintetico(), [])

    assert tecla == 255
    assert cv2_duble.janelas_fechadas == ["Cadastro facial"]
    assert [texto for texto, _, _ in cv2_duble.textos] == [
        "Pontos faciais indisponiveis"
    ]
    assert (
        sum("landmarks indisponiveis" in record.message for record in caplog.records)
        == 1
    )


def test_fechamento_do_provider_com_erro_ainda_fecha_a_janela(
    cv2_duble: Cv2Duble, caplog: pytest.LogCaptureFixture
) -> None:
    provider = ProviderLandmarksFalso(erro_ao_fechar=RuntimeError("close falhou"))

    with montar("Cadastro facial", criar_landmarks=lambda: provider):
        pass

    assert provider.fechamentos == 1
    assert cv2_duble.janelas_fechadas == ["Cadastro facial"]
    assert any("falha ao fechar" in record.message for record in caplog.records)


def test_falha_ao_redimensionar_libera_janela_e_propaga_erro(
    cv2_duble: Cv2Duble,
) -> None:
    cv2_duble.erro_redimensionamento = RuntimeError("resize falhou")

    with (
        pytest.raises(RuntimeError, match="resize falhou"),
        montar("Cadastro facial", criar_landmarks=lambda: pytest.fail()),
    ):
        pass

    assert cv2_duble.janelas_fechadas == ["Cadastro facial"]
