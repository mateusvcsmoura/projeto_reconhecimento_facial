"""Fase 5 -- traducao de falhas do DeepFace em erros de dominio.

O DeepFace nao esta instalado neste ambiente (exige Python 3.10/3.11), mas a
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
from typing import Any

import numpy as np
import pytest

from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
)

CAMINHO = "src.infrastructure.face_recognition.deepface_adapter"


class DeepFaceDuble:
    """Substitui a API do DeepFace usada pelo adaptador."""

    def __init__(self) -> None:
        self.faces: list[dict[str, Any]] = []
        self.representacoes: list[dict[str, Any]] = []
        self.erro_extract: Exception | None = None
        self.erro_represent: Exception | None = None

    def extract_faces(self, **_kwargs: Any) -> list[dict[str, Any]]:
        if self.erro_extract is not None:
            raise self.erro_extract
        return self.faces

    def represent(self, **_kwargs: Any) -> list[dict[str, Any]]:
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


def montar(duble: DeepFaceDuble) -> Any:
    modulo = importlib.import_module(CAMINHO)
    return modulo.DeepFaceAdapter(modelo="Facenet512", detector="opencv")


def face_sintetica() -> dict[str, Any]:
    return {"face": np.full((8, 8, 3), 0.5, dtype=np.float32)}


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
    duble.representacoes = [{"embedding": [3.0, 4.0]}]

    embedding = montar(duble).gerar_embedding(object())

    assert float(np.linalg.norm(embedding.vetor)) == pytest.approx(1.0)
    assert embedding.modelo == "Facenet512"


def test_embedding_registra_o_modelo_que_o_gerou(duble: DeepFaceDuble) -> None:
    duble.representacoes = [{"embedding": list(range(1, 513))}]

    embedding = montar(duble).gerar_embedding(object())

    assert embedding.dimensao == 512
    assert embedding.modelo == "Facenet512"


def test_resposta_vazia_vira_nenhum_rosto(duble: DeepFaceDuble) -> None:
    duble.representacoes = []

    with pytest.raises(NenhumRostoDetectado):
        montar(duble).gerar_embedding(object())


def test_varias_representacoes_viram_ambiguidade(duble: DeepFaceDuble) -> None:
    duble.representacoes = [{"embedding": [1.0, 0.0]}, {"embedding": [0.0, 1.0]}]

    with pytest.raises(MultiplosRostosDetectados):
        montar(duble).gerar_embedding(object())


def test_falha_do_modelo_ao_gerar_embedding_e_propagada(
    duble: DeepFaceDuble,
) -> None:
    duble.erro_represent = RuntimeError("CUDA out of memory")

    with pytest.raises(ModeloIndisponivel):
        montar(duble).gerar_embedding(object())
