"""Escolha da identidade a partir de embeddings.

Regra pura, sem IO: recebe vetores, devolve o melhor candidato. E aqui que
o problema A18 se resolve -- o prototipo aceitava o PRIMEIRO aluno que
passasse no limiar, o que podia atribuir a presenca ao aluno errado. A
distancia minima escolhe o vencedor; sem a politica optativa de ambiguidade,
um empate exato continua decidido pela primeira linha da referencia.

Custo: um produto matriz-vetor de N x 512. Com a politica ativa, uma reducao
linear adicional encontra a menor distancia de outra identidade, sem outro
produto ou ordenacao global.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real

import numpy as np

from src.domain.entities.face_embedding import DTYPE, FaceEmbedding
from src.domain.errors import IdentificacaoAmbigua


class ModeloIncompativel(ValueError):
    """Embeddings de modelos diferentes nao sao comparaveis."""


@dataclass(frozen=True, slots=True)
class Identificacao:
    aluno_id: int
    distancia: float


@dataclass(frozen=True, slots=True)
class PoliticaAmbiguidade:
    """Margem minima entre as duas melhores identidades distintas."""

    margem_minima: float

    def __post_init__(self) -> None:
        margem = self.margem_minima
        if isinstance(margem, bool) or not isinstance(margem, Real):
            raise ValueError("A margem minima deve ser um numero real entre 0 e 2.")

        try:
            margem_float = float(margem)
        except (OverflowError, ValueError) as exc:
            raise ValueError(
                "A margem minima deve ser finita e estar entre 0 e 2."
            ) from exc
        if not isfinite(margem_float) or not 0.0 <= margem_float <= 2.0:
            raise ValueError("A margem minima deve ser finita e estar entre 0 e 2.")

        object.__setattr__(self, "margem_minima", margem_float)


class MatrizDeReferencia:
    """Os embeddings cadastrados, prontos para comparacao vetorizada."""

    def __init__(self, ids: list[int], matriz: np.ndarray, modelo: str) -> None:
        self._ids = ids
        self._matriz = matriz
        self._modelo = modelo

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def modelo(self) -> str:
        return self._modelo

    @classmethod
    def de_embeddings(
        cls, pares: list[tuple[int, FaceEmbedding]]
    ) -> MatrizDeReferencia:
        if not pares:
            return cls([], np.empty((0, 0), dtype=DTYPE), "")

        modelos = {embedding.modelo for _, embedding in pares}
        if len(modelos) > 1:
            raise ModeloIncompativel(
                f"A referencia mistura modelos: {sorted(modelos)}. "
                "Refaca o backfill dos embeddings."
            )

        dimensoes = {embedding.dimensao for _, embedding in pares}
        if len(dimensoes) > 1:
            raise ModeloIncompativel(
                f"A referencia mistura dimensoes: {sorted(dimensoes)}."
            )

        ids = [aluno_id for aluno_id, _ in pares]
        matriz = np.vstack([embedding.vetor for _, embedding in pares])
        return cls(ids, matriz.astype(DTYPE), modelos.pop())

    def melhor_candidato(
        self,
        consulta: FaceEmbedding,
        limiar: float,
        *,
        ambiguidade: PoliticaAmbiguidade | None = None,
    ) -> Identificacao | None:
        """Devolve o candidato mais proximo no limiar, se a margem permitir.

        None significa que ninguem ficou abaixo do limiar ou nao ha referencia.
        IdentificacaoAmbigua e propagada quando a politica optativa recusa
        candidatas de identidades distintas sem separacao suficiente.
        """
        if ambiguidade is not None and not isinstance(ambiguidade, PoliticaAmbiguidade):
            raise ValueError("ambiguidade deve ser PoliticaAmbiguidade ou None.")

        if not self._ids:
            return None

        if consulta.modelo != self._modelo:
            raise ModeloIncompativel(
                f"A consulta usa {consulta.modelo!r} e a referencia usa "
                f"{self._modelo!r}. Embeddings de modelos diferentes nao sao "
                "comparaveis."
            )
        if consulta.dimensao != self._matriz.shape[1]:
            raise ModeloIncompativel(
                f"A consulta tem dimensao {consulta.dimensao} e a referencia "
                f"{self._matriz.shape[1]}."
            )

        # Ambos os lados estao L2-normalizados, entao a distancia cosseno e
        # 1 - produto escalar. Uma multiplicacao para todos os candidatos.
        distancias = 1.0 - self._matriz @ consulta.vetor

        indice = int(np.argmin(distancias))
        distancia = float(distancias[indice])

        if distancia > limiar:
            return None

        aluno_id = self._ids[indice]
        if ambiguidade is not None:
            # Um embedding repetido da mesma pessoa nao cria um concorrente.
            # A reducao encontra a menor distancia de uma identidade distinta
            # sem ordenar toda a galeria nem calcular outro produto matricial.
            concorrentes = np.fromiter(
                (identidade != aluno_id for identidade in self._ids),
                dtype=np.bool_,
                count=len(self._ids),
            )
            if concorrentes.any():
                segunda_distancia = float(np.min(distancias[concorrentes]))
                gap = segunda_distancia - distancia
                if gap <= 0.0 or gap < ambiguidade.margem_minima:
                    raise IdentificacaoAmbigua()

        return Identificacao(aluno_id=aluno_id, distancia=distancia)
