"""Fase 5 -- traducao de falhas do DeepFace em erros de dominio.

O DeepFace nao esta instalado neste ambiente (exige Python 3.12/3.13), mas a
logica que importa aqui nao e a da biblioteca: e a do adaptador. Um modulo
duble e injetado em sys.modules antes do import, o que permite exercitar
cada caminho de erro -- justamente o que o `except Exception: continue` do
prototipo tornava impossivel de verificar (problema A6).
"""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
    RostoMuitoPequeno,
)
from src.domain.services.qualidade_captura import ParametrosQualidade

CAMINHO = "src.infrastructure.face_recognition.deepface_adapter"


class DeepFaceDuble:
    """Substitui a API do DeepFace usada pelo adaptador."""

    def __init__(self) -> None:
        self.faces: list[dict[str, Any]] = []
        self.representacoes: list[dict[str, Any]] = []
        self.erro_extract: Exception | None = None
        self.erro_represent: Exception | None = None
        self.extracoes = 0
        self.representacoes_chamadas = 0
        self.argumentos_represent: dict[str, Any] | None = None
        self.modelos_aquecidos: list[str] = []
        self.erro_build: Exception | None = None

    def build_model(self, model_name: str) -> object:
        self.modelos_aquecidos.append(model_name)
        if self.erro_build is not None:
            raise self.erro_build
        return object()

    def extract_faces(self, **_kwargs: Any) -> list[dict[str, Any]]:
        self.extracoes += 1
        if self.erro_extract is not None:
            raise self.erro_extract
        return self.faces

    def represent(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.representacoes_chamadas += 1
        self.argumentos_represent = kwargs
        if self.erro_represent is not None:
            raise self.erro_represent
        return self.representacoes


@pytest.fixture
def duble() -> Iterator[DeepFaceDuble]:
    falso = DeepFaceDuble()
    modulo = types.ModuleType("deepface")
    modulo.DeepFace = falso  # type: ignore[attr-defined]

    original = sys.modules.get("deepface")
    sys.modules["deepface"] = modulo
    sys.modules.pop(CAMINHO, None)
    try:
        yield falso
    finally:
        sys.modules.pop(CAMINHO, None)
        if original is None:
            sys.modules.pop("deepface", None)
        else:
            sys.modules["deepface"] = original


def montar(
    duble: DeepFaceDuble,
    anti_spoofing: bool = True,
    qualidade: ParametrosQualidade | None = None,
    *,
    strict: bool = False,
    sanitizar: bool = False,
) -> Any:
    modulo = importlib.import_module(CAMINHO)
    return modulo.DeepFaceAdapter(
        modelo="Facenet512",
        detector="opencv",
        anti_spoofing=anti_spoofing,
        qualidade=qualidade,
        strict_resultado_antispoofing=strict,
        sanitizar_erros=sanitizar,
    )


def face_sintetica(
    is_real: bool = True,
    score: float = 0.9,
    *,
    facial_area: Any = None,
    pixels: np.ndarray | None = None,
) -> dict[str, Any]:
    face = (
        np.full((8, 8, 3), 0.5, dtype=np.float32)
        if pixels is None
        else pixels.astype(np.float32) / 255.0
    )
    resultado = {
        "face": face,
        "is_real": is_real,
        "antispoof_score": score,
    }
    if facial_area is not None:
        resultado["facial_area"] = facial_area
    return resultado


def face_nitida(
    largura: int = 80, altura: int = 80, *, is_real: bool = True
) -> dict[str, Any]:
    padrao = np.indices((8, 8)).sum(axis=0) % 2 * 255
    pixels = np.repeat(padrao[:, :, None], 3, axis=2).astype(np.uint8)
    return face_sintetica(
        is_real=is_real,
        facial_area={"w": largura, "h": altura},
        pixels=pixels,
    )


# -- extrair_face_unica ----------------------------------------------------


def test_recorte_volta_em_uint8_bgr(duble: DeepFaceDuble) -> None:
    """cv2.imwrite espera BGR uint8; o DeepFace devolve RGB float [0, 1]."""
    duble.faces = [face_sintetica()]

    recorte = montar(duble).extrair_face_unica(object())

    assert recorte.dtype == np.uint8
    assert recorte.max() <= 255
    assert recorte.shape == (8, 8, 3)


def test_ausencia_de_rosto_vira_erro_de_dominio(duble: DeepFaceDuble) -> None:
    duble.erro_extract = ValueError("Face could not be detected in the image")

    with pytest.raises(NenhumRostoDetectado):
        montar(duble).extrair_face_unica(object())


def test_varios_rostos_viram_erro_de_dominio(duble: DeepFaceDuble) -> None:
    duble.faces = [face_sintetica(), face_sintetica()]

    with pytest.raises(MultiplosRostosDetectados) as capturado:
        montar(duble).extrair_face_unica(object())

    assert capturado.value.quantidade == 2


def test_falha_de_infraestrutura_nao_vira_sem_rosto(duble: DeepFaceDuble) -> None:
    """O ponto do problema A6: pesos ausentes nao podem virar 'sem rosto'."""
    duble.erro_extract = OSError("weights file not found")

    with pytest.raises(ModeloIndisponivel):
        montar(duble).extrair_face_unica(object())


def test_valueerror_que_nao_e_sobre_rosto_vira_modelo_indisponivel(
    duble: DeepFaceDuble,
) -> None:
    duble.erro_extract = ValueError("invalid detector backend 'xyz'")

    with pytest.raises(ModeloIndisponivel):
        montar(duble).extrair_face_unica(object())


# -- gerar_embedding -------------------------------------------------------


def test_embedding_sai_normalizado(duble: DeepFaceDuble) -> None:
    """represent() nao normaliza; o adaptador entrega o invariante pronto."""
    duble.faces = [face_sintetica()]
    duble.representacoes = [{"embedding": [3.0, 4.0]}]

    embedding = montar(duble).gerar_embedding(object())

    assert float(np.linalg.norm(embedding.vetor)) == pytest.approx(1.0)
    assert embedding.modelo == "Facenet512"


def test_embedding_registra_o_modelo_que_o_gerou(duble: DeepFaceDuble) -> None:
    duble.faces = [face_sintetica()]
    duble.representacoes = [{"embedding": list(range(1, 513))}]

    embedding = montar(duble).gerar_embedding(object())

    assert embedding.dimensao == 512
    assert embedding.modelo == "Facenet512"


def test_sem_rosto_nao_chega_a_gerar_embedding(duble: DeepFaceDuble) -> None:
    duble.erro_extract = ValueError("Face could not be detected in the image")

    with pytest.raises(NenhumRostoDetectado):
        montar(duble).gerar_embedding(object())


@pytest.mark.parametrize("qualidade_ligada", [False, True])
def test_varias_pessoas_no_frame_viram_ambiguidade(
    duble: DeepFaceDuble, qualidade_ligada: bool
) -> None:
    duble.faces = [face_sintetica(), face_sintetica()]
    parametros = ParametrosQualidade() if qualidade_ligada else None

    with pytest.raises(MultiplosRostosDetectados):
        montar(duble, qualidade=parametros).gerar_embedding(object())

    assert duble.representacoes_chamadas == 0


def test_resposta_vazia_do_modelo_vira_nenhum_rosto(duble: DeepFaceDuble) -> None:
    duble.faces = [face_sintetica()]
    duble.representacoes = []

    with pytest.raises(NenhumRostoDetectado):
        montar(duble).gerar_embedding(object())


@pytest.mark.parametrize("qualidade_ligada", [False, True])
def test_falha_do_modelo_ao_gerar_embedding_e_propagada(
    duble: DeepFaceDuble, qualidade_ligada: bool
) -> None:
    duble.faces = [face_nitida() if qualidade_ligada else face_sintetica()]
    duble.erro_represent = RuntimeError("CUDA out of memory")
    parametros = ParametrosQualidade() if qualidade_ligada else None

    with pytest.raises(ModeloIndisponivel):
        montar(duble, qualidade=parametros).gerar_embedding(object())

    assert duble.representacoes_chamadas == 1


# -- anti-spoofing (Fase 6, problema A7) -----------------------------------


def test_foto_impressa_e_recusada_no_cadastro(duble: DeepFaceDuble) -> None:
    """Um controle de presenca burlavel com uma foto nao controla nada."""
    duble.faces = [face_sintetica(is_real=False, score=0.12)]

    with pytest.raises(PossivelFraude) as capturado:
        montar(duble).extrair_face_unica(object())

    assert capturado.value.pontuacao == pytest.approx(0.12)


def test_foto_impressa_e_recusada_no_reconhecimento(duble: DeepFaceDuble) -> None:
    """A verificacao vale nos DOIS caminhos, nao so no cadastro."""
    duble.faces = [face_sintetica(is_real=False, score=0.05)]
    duble.representacoes = [{"embedding": [1.0, 0.0]}]

    with pytest.raises(PossivelFraude):
        montar(duble).gerar_embedding(object())


def test_fraude_e_distinta_de_ausencia_de_rosto(duble: DeepFaceDuble) -> None:
    """Ha um rosto -- e por isso o operador merece outra mensagem."""
    duble.faces = [face_sintetica(is_real=False)]

    with pytest.raises(PossivelFraude) as capturado:
        montar(duble).extrair_face_unica(object())

    assert not isinstance(capturado.value, NenhumRostoDetectado)


def test_rosto_real_passa(duble: DeepFaceDuble) -> None:
    duble.faces = [face_sintetica(is_real=True, score=0.97)]

    recorte = montar(duble).extrair_face_unica(object())

    assert recorte.dtype == np.uint8


def test_resultado_antispoofing_ausente_falha_fechado_no_worker_web(
    duble: DeepFaceDuble,
) -> None:
    face = face_sintetica()
    face.pop("is_real")
    duble.faces = [face]

    with pytest.raises(ModeloIndisponivel, match="anti-spoofing"):
        montar(duble, strict=True).extrair_face_unica(object())


def test_resultado_antispoofing_invalido_falha_fechado_no_worker_web(
    duble: DeepFaceDuble,
) -> None:
    face = face_sintetica()
    face["is_real"] = "true"
    duble.faces = [face]

    with pytest.raises(ModeloIndisponivel, match="anti-spoofing"):
        montar(duble, strict=True).extrair_face_unica(object())


def test_cli_preserva_resultado_legado_quando_is_real_estiver_ausente(
    duble: DeepFaceDuble,
) -> None:
    face = face_sintetica()
    face.pop("is_real")
    duble.faces = [face]

    assert montar(duble).extrair_face_unica(object()).dtype == np.uint8


def test_preaquecer_web_exige_pesos_locais_antes_de_carregar_modelos(
    duble: DeepFaceDuble, tmp_path: Path
) -> None:
    with pytest.raises(ModeloIndisponivel, match="ausentes"):
        montar(duble, strict=True, sanitizar=True).preaquecer_para_web(tmp_path)

    assert duble.modelos_aquecidos == []


def test_preaquecer_web_carrega_facetnet_e_minifasnet_sem_download(
    duble: DeepFaceDuble, tmp_path: Path
) -> None:
    for nome in (
        "facenet512_weights.h5",
        "2.7_80x80_MiniFASNetV2.pth",
        "4_0_0_80x80_MiniFASNetV1SE.pth",
    ):
        (tmp_path / nome).write_bytes(b"synthetic model sentinel")

    montar(duble, strict=True, sanitizar=True).preaquecer_para_web(tmp_path)

    assert duble.modelos_aquecidos == ["Facenet512", "Fasnet"]


def test_worker_nao_expoe_detalhe_de_falha_do_deepface(
    duble: DeepFaceDuble, caplog: pytest.LogCaptureFixture
) -> None:
    duble.erro_extract = RuntimeError("private-image-path-and-runtime-secret")

    with pytest.raises(ModeloIndisponivel, match="Falha técnica") as erro:
        montar(duble, sanitizar=True).extrair_face_unica(object())

    assert "private-image-path-and-runtime-secret" not in str(erro.value)
    assert "private-image-path-and-runtime-secret" not in caplog.text


def test_com_anti_spoofing_desligado_a_verificacao_nao_ocorre(
    duble: DeepFaceDuble,
) -> None:
    """A flag existe para desenvolvimento; o padrao e ligado."""
    duble.faces = [face_sintetica(is_real=False, score=0.01)]

    recorte = montar(duble, anti_spoofing=False).extrair_face_unica(object())

    assert recorte.dtype == np.uint8


def test_preparar_cadastro_detecta_e_representa_uma_vez_a_mesma_face(
    duble: DeepFaceDuble,
) -> None:
    duble.faces = [face_nitida()]
    duble.representacoes = [{"embedding": [3.0, 4.0]}]

    preparada = montar(duble, qualidade=ParametrosQualidade()).preparar_cadastro(
        object()
    )

    assert duble.extracoes == 1
    assert duble.representacoes_chamadas == 1
    assert duble.argumentos_represent is not None
    assert duble.argumentos_represent["img_path"] is preparada.imagem
    assert preparada.imagem.dtype == np.uint8
    assert float(np.linalg.norm(preparada.embedding.vetor)) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "metodo", ["extrair_face_unica", "gerar_embedding", "preparar_cadastro"]
)
def test_todos_os_metodos_publicos_aplicam_qualidade_antes_de_representar(
    duble: DeepFaceDuble, metodo: str
) -> None:
    duble.faces = [face_nitida(largura=79)]
    adaptador = montar(duble, qualidade=ParametrosQualidade())

    with pytest.raises(RostoMuitoPequeno):
        getattr(adaptador, metodo)(object())

    assert duble.extracoes == 1
    assert duble.representacoes_chamadas == 0


@pytest.mark.parametrize(
    "area",
    [None, {}, {"w": 0, "h": 80}, {"w": "80", "h": 80}, {"w": 80, "h": True}],
)
def test_metadados_de_area_facial_invalidos_falham_com_politica_ligada(
    duble: DeepFaceDuble, area: Any
) -> None:
    duble.faces = [face_sintetica(facial_area=area)]
    adaptador = montar(duble, qualidade=ParametrosQualidade())

    with pytest.raises(ModeloIndisponivel, match="facial_area"):
        adaptador.preparar_cadastro(object())

    assert duble.extracoes == 1
    assert duble.representacoes_chamadas == 0


def test_metadados_nao_sao_obrigatorios_com_politica_desligada(
    duble: DeepFaceDuble,
) -> None:
    duble.faces = [face_sintetica()]
    duble.representacoes = [{"embedding": [1.0, 0.0]}]

    embedding = montar(duble).gerar_embedding(object())

    assert embedding.modelo == "Facenet512"
    assert duble.extracoes == 1
    assert duble.representacoes_chamadas == 1


@pytest.mark.parametrize("qualidade_ligada", [False, True])
def test_antispoofing_continua_recusando_captura_com_qualidade(
    duble: DeepFaceDuble, qualidade_ligada: bool
) -> None:
    parametros = ParametrosQualidade() if qualidade_ligada else None
    duble.faces = [face_nitida(is_real=False)]

    with pytest.raises(PossivelFraude):
        montar(duble, qualidade=parametros).preparar_cadastro(object())

    assert duble.representacoes_chamadas == 0


def test_qualidade_desligada_preserva_embedding_de_recorte_plano(
    duble: DeepFaceDuble,
) -> None:
    duble.faces = [face_sintetica()]
    duble.representacoes = [{"embedding": [1.0, 0.0]}]

    montar(duble).gerar_embedding(object())

    assert duble.representacoes_chamadas == 1
