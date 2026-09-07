"""Fase 5 -- o vetor que representa um rosto."""

from __future__ import annotations

import numpy as np
import pytest

from src.domain.entities.face_embedding import (
    DTYPE,
    EmbeddingInvalido,
    FaceEmbedding,
)

MODELO = "Facenet512"


def test_vetor_e_normalizado_na_construcao() -> None:
    """DeepFace.represent() nao normaliza; a entidade garante o invariante."""
    embedding = FaceEmbedding.de_valores([3.0, 4.0], MODELO)

    assert float(np.linalg.norm(embedding.vetor)) == pytest.approx(1.0)
    assert embedding.vetor.tolist() == pytest.approx([0.6, 0.8])


def test_escala_nao_muda_o_vetor_resultante() -> None:
    pequeno = FaceEmbedding.de_valores([1.0, 2.0, 3.0], MODELO)
    grande = FaceEmbedding.de_valores([100.0, 200.0, 300.0], MODELO)

    assert pequeno.vetor.tolist() == pytest.approx(grande.vetor.tolist())


def test_dimensao_reflete_o_tamanho_do_vetor() -> None:
    assert FaceEmbedding.de_valores(np.ones(512), MODELO).dimensao == 512


def test_round_trip_em_bytes_preserva_o_vetor() -> None:
    original = FaceEmbedding.de_valores(np.random.rand(512), MODELO)

    recuperado = FaceEmbedding.de_bytes(original.para_bytes(), MODELO)

    assert recuperado.vetor.tolist() == pytest.approx(original.vetor.tolist())
    assert recuperado.modelo == MODELO


def test_bytes_usam_float32_little_endian() -> None:
    """Formato canonico: 4 bytes por dimensao, portavel entre maquinas."""
    embedding = FaceEmbedding.de_valores(np.ones(512), MODELO)

    assert len(embedding.para_bytes()) == 512 * 4
    assert np.dtype(DTYPE).itemsize == 4


def test_vetor_vazio_e_rejeitado() -> None:
    with pytest.raises(EmbeddingInvalido, match="vazio"):
        FaceEmbedding.de_valores([], MODELO)


def test_vetor_de_norma_zero_e_rejeitado() -> None:
    with pytest.raises(EmbeddingInvalido, match="norma zero"):
        FaceEmbedding.de_valores([0.0, 0.0, 0.0], MODELO)


def test_vetor_com_nan_e_rejeitado() -> None:
    with pytest.raises(EmbeddingInvalido, match="NaN"):
        FaceEmbedding.de_valores([1.0, float("nan")], MODELO)


def test_distancia_de_si_mesmo_e_zero() -> None:
    embedding = FaceEmbedding.de_valores([1.0, 2.0, 3.0], MODELO)
    assert embedding.distancia_cosseno(embedding) == pytest.approx(0.0, abs=1e-6)


def test_distancia_entre_ortogonais_e_um() -> None:
    a = FaceEmbedding.de_valores([1.0, 0.0], MODELO)
    b = FaceEmbedding.de_valores([0.0, 1.0], MODELO)
    assert a.distancia_cosseno(b) == pytest.approx(1.0)


def test_modelos_diferentes_nao_sao_comparaveis() -> None:
    """Comparar vetores de modelos distintos identificaria a pessoa errada."""
    a = FaceEmbedding.de_valores([1.0, 0.0], "Facenet512")
    b = FaceEmbedding.de_valores([1.0, 0.0], "ArcFace")

    with pytest.raises(EmbeddingInvalido, match="modelos diferentes"):
        a.distancia_cosseno(b)
