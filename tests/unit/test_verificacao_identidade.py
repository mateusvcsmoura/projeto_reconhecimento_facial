from __future__ import annotations

import inspect
from math import sqrt

import numpy as np
import pytest

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.services.verificacao_identidade import (
    PoliticaVerificacaoIdentidade,
    ReferenciaIdentidade,
    VerificarIdentidade,
)


def _embedding(distancia: float, *, modelo: str = "Facenet512") -> FaceEmbedding:
    similaridade = 1.0 - distancia
    valores = np.zeros(512, dtype=np.float32)
    valores[0] = similaridade
    valores[1] = sqrt(max(0.0, 1.0 - similaridade**2))
    return FaceEmbedding.de_valores(valores, modelo)


def _referencias(
    distancias: tuple[float, float, float],
    *,
    alunos: tuple[int, int, int] = (12, 12, 12),
    conjuntos: tuple[int, int, int] = (34, 34, 34),
    versoes: tuple[int, int, int] = (2, 2, 2),
    modelos: tuple[str, str, str] = ("Facenet512",) * 3,
    dimensoes: tuple[int, int, int] = (512, 512, 512),
) -> tuple[ReferenciaIdentidade, ...]:
    referencias: list[ReferenciaIdentidade] = []
    for ordinal, (distancia, aluno, conjunto, versao, modelo, dimensao) in enumerate(
        zip(distancias, alunos, conjuntos, versoes, modelos, dimensoes, strict=True),
        start=1,
    ):
        embedding = _embedding(distancia, modelo=modelo)
        if dimensao != 512:
            embedding = FaceEmbedding.de_valores([1.0, 0.5], modelo)
        referencias.append(
            ReferenciaIdentidade(
                aluno_id=aluno,
                conjunto_id=conjunto,
                versao=versao,
                ordinal=ordinal,
                embedding=embedding,
            )
        )
    return tuple(referencias)


def _executar(
    distancias: tuple[float, float, float],
    *,
    referencias: tuple[ReferenciaIdentidade, ...] | None = None,
    consulta: FaceEmbedding | None = None,
    politica: PoliticaVerificacaoIdentidade | None = None,
    alunos: tuple[int, int, int] = (12, 12, 12),
    conjuntos: tuple[int, int, int] = (34, 34, 34),
    versoes: tuple[int, int, int] = (2, 2, 2),
    modelos: tuple[str, str, str] = ("Facenet512",) * 3,
    dimensoes: tuple[int, int, int] = (512, 512, 512),
):
    refs = (
        referencias
        if referencias is not None
        else _referencias(
            distancias,
            alunos=alunos,
            conjuntos=conjuntos,
            versoes=versoes,
            modelos=modelos,
            dimensoes=dimensoes,
        )
    )
    regra = politica or PoliticaVerificacaoIdentidade(
        aluno_id=12, conjunto_id=34, versao_referencia=2
    )
    return VerificarIdentidade().executar(consulta or _embedding(0.0), refs, regra)


@pytest.mark.parametrize(
    ("distancias", "esperado", "mediana"),
    [
        ((0.20, 0.29, 0.80), True, 0.29),
        ((0.20, 0.31, 0.80), False, 0.31),
    ],
)
def test_verifica_mediana_das_tres_referencias(
    distancias: tuple[float, float, float], esperado: bool, mediana: float
) -> None:
    decisao = _executar(distancias)

    assert decisao.identidade_ok is esperado
    assert decisao.distancia_mediana == pytest.approx(mediana, abs=1e-6)
    assert decisao.versao_referencia == 2
    assert decisao.politica == "mediana_3_coseno_0_30_v1"


def test_limiar_0_30_inclusivo() -> None:
    decisao = _executar((0.30, 0.30, 0.30))

    assert decisao.identidade_ok is True
    assert decisao.distancia_mediana == pytest.approx(0.30, abs=1e-6)


def test_referencia_de_outro_aluno_ou_versao_recusa_sem_busca_global() -> None:
    referencias = _referencias((0.1, 0.1, 0.1), alunos=(12, 99, 12))
    decisao = _executar((0.1, 0.1, 0.1), referencias=referencias)

    assert decisao.identidade_ok is False
    assert decisao.motivo_tecnico == "referencias_incompativeis"
    assert inspect.signature(VerificarIdentidade).parameters == {}


def test_referencias_com_versao_de_conjunto_trocada_recusam() -> None:
    decisao = _executar((0.1, 0.1, 0.1), versoes=(2, 3, 2))

    assert decisao.identidade_ok is False
    assert decisao.motivo_tecnico == "referencias_incompativeis"


def test_referencias_com_modelo_ou_dimensao_incompativel_recusam() -> None:
    decisao_modelo = _executar(
        (0.1, 0.1, 0.1), modelos=("VGG-Face", "Facenet512", "Facenet512")
    )
    decisao_dimensao = _executar((0.1, 0.1, 0.1), dimensoes=(512, 128, 512))

    assert decisao_modelo.identidade_ok is False
    assert decisao_modelo.motivo_tecnico == "referencias_incompativeis"
    assert decisao_dimensao.identidade_ok is False
    assert decisao_dimensao.motivo_tecnico == "referencias_incompativeis"


def test_quantidade_incorreta_de_referencias_recusa() -> None:
    decisao = _executar((0.1, 0.1, 0.1), referencias=_referencias((0.1, 0.1, 0.1))[:2])

    assert decisao.identidade_ok is False
    assert decisao.motivo_tecnico == "referencias_incompativeis"


def test_embedding_nao_finito_recusa_sem_expor_vetor() -> None:
    referencias = list(_referencias((0.1, 0.1, 0.1)))
    referencias[1].embedding.vetor[0] = np.nan
    decisao = _executar((0.1, 0.1, 0.1), referencias=tuple(referencias))

    assert decisao.identidade_ok is False
    assert decisao.motivo_tecnico == "referencias_incompativeis"
    assert not hasattr(decisao, "embedding")
    assert not hasattr(decisao, "foto")
