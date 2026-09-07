"""Escolha da identidade a partir de embeddings.

Regra pura, sem IO: recebe vetores, devolve o melhor candidato. E aqui que
o problema A18 se resolve -- o prototipo aceitava o PRIMEIRO aluno que
passasse no limiar, o que atribui a presenca ao aluno errado sempre que
dois candidatos ficam proximos. Com a distancia em maos, escolhe-se o
MENOR, e o empate deixa de ser decidido pela ordem alfabetica da consulta.

Custo: um produto matriz-vetor de N x 512. Para dezenas ou centenas de
alunos, microssegundos -- contra as ate 2N inferencias Facenet512 por ciclo
que o desenho anterior exigia (problema A5).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.domain.entities.face_embedding import DTYPE, FaceEmbedding


class ModeloIncompativel(ValueError):
    """Embeddings de modelos diferentes nao sao comparaveis."""


@dataclass(frozen=True, slots=True)
class Identificacao:
    aluno_id: int
    distancia: float


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
        self, consulta: FaceEmbedding, limiar: float
    ) -> Identificacao | None:
        """Devolve o candidato de MENOR distancia abaixo do limiar.

        None significa: ninguem ficou abaixo do limiar, ou nao ha referencia.
        """
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

        return Identificacao(aluno_id=self._ids[indice], distancia=distancia)
