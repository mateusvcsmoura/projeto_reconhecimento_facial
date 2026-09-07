"""Fase 5 -- escolha da identidade. Regra pura, sem IO e sem modelo de IA."""

from __future__ import annotations

import numpy as np
import pytest

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.services.matcher import (
    MatrizDeReferencia,
    ModeloIncompativel,
)

MODELO = "Facenet512"
LIMIAR = 0.30


def emb(valores: list[float], modelo: str = MODELO) -> FaceEmbedding:
    return FaceEmbedding.de_valores(valores, modelo)


def test_referencia_vazia_nao_identifica_ninguem() -> None:
    referencia = MatrizDeReferencia.de_embeddings([])

    assert len(referencia) == 0
    assert referencia.melhor_candidato(emb([1.0, 0.0]), LIMIAR) is None


def test_identifica_o_unico_candidato_proximo() -> None:
    referencia = MatrizDeReferencia.de_embeddings([(7, emb([1.0, 0.0]))])

    resultado = referencia.melhor_candidato(emb([1.0, 0.01]), LIMIAR)

    assert resultado is not None
    assert resultado.aluno_id == 7


def test_escolhe_o_MELHOR_candidato_e_nao_o_primeiro() -> None:
    """Problema A18.

    O prototipo aceitava o primeiro aluno que passasse no limiar. Aqui o
    aluno 1 passa no limiar, mas o aluno 2 esta mais perto -- e a presenca
    tem de ser do aluno 2.
    """
    consulta = emb([1.0, 0.20, 0.0])
    referencia = MatrizDeReferencia.de_embeddings(
        [
            (1, emb([1.0, 0.0, 0.0])),
            (2, emb([1.0, 0.20, 0.0])),
            (3, emb([0.0, 0.0, 1.0])),
        ]
    )

    # O aluno 1 sozinho seria aceito: ele esta abaixo do limiar.
    apenas_o_primeiro = MatrizDeReferencia.de_embeddings([(1, emb([1.0, 0.0, 0.0]))])
    assert apenas_o_primeiro.melhor_candidato(consulta, LIMIAR) is not None

    resultado = referencia.melhor_candidato(consulta, LIMIAR)

    assert resultado is not None
    assert resultado.aluno_id == 2
    assert resultado.distancia == pytest.approx(0.0, abs=1e-6)


def test_ninguem_abaixo_do_limiar_devolve_none() -> None:
    referencia = MatrizDeReferencia.de_embeddings([(1, emb([1.0, 0.0]))])

    assert referencia.melhor_candidato(emb([0.0, 1.0]), LIMIAR) is None


def test_limiar_e_inclusivo_na_fronteira() -> None:
    referencia = MatrizDeReferencia.de_embeddings([(1, emb([1.0, 0.0]))])
    consulta = emb([1.0, 0.0])

    assert referencia.melhor_candidato(consulta, 0.0000001) is not None


def test_a_distancia_devolvida_e_util_ao_operador() -> None:
    referencia = MatrizDeReferencia.de_embeddings([(1, emb([1.0, 0.0]))])

    resultado = referencia.melhor_candidato(emb([1.0, 0.0]), LIMIAR)

    assert resultado is not None
    assert 0.0 <= resultado.distancia <= 2.0


def test_referencia_com_modelos_misturados_e_recusada() -> None:
    with pytest.raises(ModeloIncompativel, match="mistura modelos"):
        MatrizDeReferencia.de_embeddings(
            [
                (1, emb([1.0, 0.0], "Facenet512")),
                (2, emb([1.0, 0.0], "ArcFace")),
            ]
        )


def test_consulta_de_outro_modelo_e_recusada() -> None:
    """Silenciosamente comparavel seria pior: identificaria a pessoa errada."""
    referencia = MatrizDeReferencia.de_embeddings([(1, emb([1.0, 0.0]))])

    with pytest.raises(ModeloIncompativel, match="nao sao"):
        referencia.melhor_candidato(emb([1.0, 0.0], "ArcFace"), LIMIAR)


def test_consulta_de_dimensao_diferente_e_recusada() -> None:
    referencia = MatrizDeReferencia.de_embeddings([(1, emb([1.0, 0.0, 0.0]))])

    with pytest.raises(ModeloIncompativel, match="dimensao"):
        referencia.melhor_candidato(emb([1.0, 0.0]), LIMIAR)


def test_resultado_bate_com_o_calculo_ingenuo() -> None:
    """A versao vetorizada nao pode divergir do laco obvio."""
    rng = np.random.default_rng(seed=42)
    pares = [(i, FaceEmbedding.de_valores(rng.random(512), MODELO)) for i in range(50)]
    consulta = FaceEmbedding.de_valores(rng.random(512), MODELO)

    referencia = MatrizDeReferencia.de_embeddings(pares)
    vetorizado = referencia.melhor_candidato(consulta, limiar=2.0)

    ingenuo = min(
        ((i, consulta.distancia_cosseno(e)) for i, e in pares), key=lambda p: p[1]
    )

    assert vetorizado is not None
    assert vetorizado.aluno_id == ingenuo[0]
    assert vetorizado.distancia == pytest.approx(ingenuo[1], abs=1e-5)


def test_escala_ate_centenas_de_alunos() -> None:
    rng = np.random.default_rng(seed=7)
    pares = [
        (i, FaceEmbedding.de_valores(rng.random(512), MODELO)) for i in range(500)
    ]
    referencia = MatrizDeReferencia.de_embeddings(pares)

    resultado = referencia.melhor_candidato(pares[321][1], LIMIAR)

    assert resultado is not None
    assert resultado.aluno_id == 321
