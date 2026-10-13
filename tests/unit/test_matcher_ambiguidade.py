"""Rejeicao top-2 por identidade, com embeddings sinteticos."""

from __future__ import annotations

from itertools import permutations

import numpy as np
import pytest

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import IdentificacaoAmbigua
from src.domain.services.matcher import (
    MatrizDeReferencia,
    ModeloIncompativel,
    PoliticaAmbiguidade,
)

MODELO = "Facenet512"
LIMIAR = 0.30


def emb(valores: list[float], modelo: str = MODELO) -> FaceEmbedding:
    return FaceEmbedding.de_valores(valores, modelo)


def referencia(*pares: tuple[int, list[float]]) -> MatrizDeReferencia:
    return MatrizDeReferencia.de_embeddings(
        [(aluno_id, emb(vetor)) for aluno_id, vetor in pares]
    )


@pytest.mark.parametrize("margem", [0, 2, 0.25])
def test_politica_aceita_margem_finita_no_intervalo(margem: int | float) -> None:
    politica = PoliticaAmbiguidade(margem)

    assert politica.margem_minima == float(margem)


@pytest.mark.parametrize(
    "margem",
    [None, True, False, "0.1", -0.1, 2.1, float("nan"), float("inf"), -float("inf")],
)
def test_politica_recusa_margem_invalida(margem: object) -> None:
    with pytest.raises(ValueError):
        PoliticaAmbiguidade(margem)  # type: ignore[arg-type]


def test_argumento_ambiguidade_de_tipo_inesperado_falha_explicitamente() -> None:
    galeria = referencia((1, [1.0, 0.0]))

    with pytest.raises(ValueError, match="PoliticaAmbiguidade"):
        galeria.melhor_candidato(
            emb([1.0, 0.0]),
            LIMIAR,
            ambiguidade=object(),  # type: ignore[arg-type]
        )


def test_sem_politica_ou_fora_do_limiar_nao_calcula_concorrente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def recusar_segundo_calculo(*_args: object, **_kwargs: object) -> np.ndarray:
        pytest.fail("nao deveria construir a mascara de concorrentes")

    galeria = referencia((1, [1.0, 0.0]), (2, [0.0, 1.0]))
    clara = emb([1.0, 0.0])
    distante = emb([1.0, 1.0])
    monkeypatch.setattr(np, "fromiter", recusar_segundo_calculo)

    assert galeria.melhor_candidato(clara, LIMIAR) is not None
    assert (
        galeria.melhor_candidato(distante, 0.2, ambiguidade=PoliticaAmbiguidade(0.0))
        is None
    )


def test_politica_desligada_preserva_desempate_pela_primeira_linha() -> None:
    galeria = referencia((1, [1.0, 0.0]), (2, [1.0, 0.0]))

    resultado = galeria.melhor_candidato(emb([1.0, 0.0]), LIMIAR)

    assert resultado is not None
    assert resultado.aluno_id == 1


@pytest.mark.parametrize("ordem", [(1, 2), (2, 1)])
@pytest.mark.parametrize("margem", [0.0, 0.2])
def test_empate_de_identidades_distintas_e_recusado_em_qualquer_ordem(
    ordem: tuple[int, int], margem: float
) -> None:
    vetores = {1: [1.0, 0.0], 2: [1.0, 0.0]}
    galeria = referencia(*((aluno_id, vetores[aluno_id]) for aluno_id in ordem))

    with pytest.raises(IdentificacaoAmbigua):
        galeria.melhor_candidato(
            emb([1.0, 0.0]),
            LIMIAR,
            ambiguidade=PoliticaAmbiguidade(margem),
        )


def test_unica_identidade_e_aceita_com_politica_ativa() -> None:
    galeria = referencia((7, [1.0, 0.0]))

    resultado = galeria.melhor_candidato(
        emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.5)
    )

    assert resultado is not None
    assert resultado.aluno_id == 7


def test_gap_positivo_igual_a_margem_e_aceito_e_vizinho_acima_recusado() -> None:
    galeria = referencia((1, [1.0, 0.0]), (2, [0.0, 1.0]))
    consulta = emb([1.0, 0.0])

    aceito = galeria.melhor_candidato(
        consulta, LIMIAR, ambiguidade=PoliticaAmbiguidade(1.0)
    )
    assert aceito is not None and aceito.aluno_id == 1

    with pytest.raises(IdentificacaoAmbigua):
        galeria.melhor_candidato(
            consulta,
            LIMIAR,
            ambiguidade=PoliticaAmbiguidade(float(np.nextafter(1.0, 2.0))),
        )

    aceito_abaixo = galeria.melhor_candidato(
        consulta,
        LIMIAR,
        ambiguidade=PoliticaAmbiguidade(float(np.nextafter(1.0, 0.0))),
    )
    assert aceito_abaixo is not None


def test_gap_pequeno_recusa_mesmo_com_segundo_acima_do_limiar() -> None:
    galeria = referencia(
        (1, [0.71, float(np.sqrt(1.0 - 0.71**2))]),
        (2, [0.69, float(np.sqrt(1.0 - 0.69**2))]),
    )

    with pytest.raises(IdentificacaoAmbigua):
        galeria.melhor_candidato(
            emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.03)
        )


def test_segundo_candidato_e_outra_identidade_nao_outra_linha() -> None:
    galeria = referencia(
        (1, [1.0, 0.0]),
        (1, [1.0, 0.0]),
        (2, [0.0, 1.0]),
    )

    resultado = galeria.melhor_candidato(
        emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(1.0)
    )

    assert resultado is not None and resultado.aluno_id == 1


@pytest.mark.parametrize("politica", [None, PoliticaAmbiguidade(0.5)])
def test_matcher_faz_um_unico_produto_matricial(
    politica: PoliticaAmbiguidade | None,
) -> None:
    class ProdutoContador:
        def __init__(self, matriz: np.ndarray) -> None:
            self.matriz = matriz
            self.shape = matriz.shape
            self.chamadas = 0

        def __matmul__(self, vetor: np.ndarray) -> np.ndarray:
            self.chamadas += 1
            return self.matriz @ vetor

    galeria = referencia((1, [1.0, 0.0]), (2, [0.0, 1.0]))
    contador = ProdutoContador(galeria._matriz)
    galeria._matriz = contador  # type: ignore[assignment]

    resultado = galeria.melhor_candidato(emb([1.0, 0.0]), LIMIAR, ambiguidade=politica)

    assert resultado is not None
    assert contador.chamadas == 1


def test_terceira_identidade_empatada_com_a_melhor_tambem_e_recusada() -> None:
    galeria = referencia(
        (1, [1.0, 0.0]),
        (1, [1.0, 0.0]),
        (2, [1.0, 0.0]),
        (3, [0.0, 1.0]),
    )

    with pytest.raises(IdentificacaoAmbigua):
        galeria.melhor_candidato(
            emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.0)
        )


@pytest.mark.parametrize("ordem", list(permutations(range(3))))
def test_vencedor_unico_permuta_sem_mudar_identidade(
    ordem: tuple[int, int, int],
) -> None:
    candidatos = [
        (1, [1.0, 0.0]),
        (2, [0.0, 1.0]),
        (3, [-1.0, 0.0]),
    ]
    galeria = referencia(*(candidatos[indice] for indice in ordem))

    resultado = galeria.melhor_candidato(
        emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.5)
    )

    assert resultado is not None and resultado.aluno_id == 1


def test_mesma_identidade_repetida_sem_outro_id_nao_e_ambigua() -> None:
    galeria = referencia((1, [1.0, 0.0]), (1, [0.0, 1.0]))

    resultado = galeria.melhor_candidato(
        emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.0)
    )

    assert resultado is not None and resultado.aluno_id == 1


def test_melhor_fora_do_limiar_retorna_none_antes_da_ambiguidade() -> None:
    galeria = referencia((1, [0.0, 1.0]), (2, [0.0, 1.0]))

    assert (
        galeria.melhor_candidato(
            emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.5)
        )
        is None
    )


def test_galeria_vazia_retorna_none_com_politica_ativa() -> None:
    galeria = MatrizDeReferencia.de_embeddings([])

    assert (
        galeria.melhor_candidato(
            emb([1.0, 0.0]), LIMIAR, ambiguidade=PoliticaAmbiguidade(0.0)
        )
        is None
    )


@pytest.mark.parametrize(
    "consulta",
    [emb([1.0, 0.0], "ArcFace"), emb([1.0, 0.0, 0.0])],
    ids=["modelo", "dimensao"],
)
def test_politica_nao_muda_erros_de_modelo_ou_dimensao(
    consulta: FaceEmbedding,
) -> None:
    galeria = referencia((1, [1.0, 0.0]))

    with pytest.raises(ModeloIncompativel):
        galeria.melhor_candidato(consulta, LIMIAR, ambiguidade=PoliticaAmbiguidade(0.1))


def test_decisao_nao_modifica_consulta_ou_matriz_de_referencia() -> None:
    galeria = referencia((1, [1.0, 0.0]), (2, [0.0, 1.0]))
    consulta = emb([1.0, 0.0])
    vetor_antes = consulta.vetor.copy()
    matriz_antes = galeria._matriz.copy()

    with pytest.raises(IdentificacaoAmbigua):
        galeria.melhor_candidato(consulta, LIMIAR, ambiguidade=PoliticaAmbiguidade(1.1))

    np.testing.assert_array_equal(consulta.vetor, vetor_antes)
    np.testing.assert_array_equal(galeria._matriz, matriz_antes)
