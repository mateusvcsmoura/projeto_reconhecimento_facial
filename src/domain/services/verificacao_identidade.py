"""Verificação fechada 1:1 contra exatamente três referências da matrícula.

O serviço é puro: recebe somente a consulta e o conjunto já selecionado para
uma identidade. Não acessa repositórios nem procura outros alunos.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isclose, isfinite
from statistics import median

import numpy as np

from src.domain.entities.face_embedding import FaceEmbedding

MODELO_WEB = "Facenet512"
DIMENSAO_EMBEDDING = 512
LIMIAR_VERIFICACAO = 0.30
POLITICA_VERIFICACAO = "mediana_3_coseno_0_30_v1"
_TOLERANCIA_FLOAT32 = 1e-7


@dataclass(frozen=True, slots=True)
class PoliticaVerificacaoIdentidade:
    """Alvo autorizado pelo caso de uso e versão fixa da regra 1:1."""

    aluno_id: int
    conjunto_id: int
    versao_referencia: int

    def __post_init__(self) -> None:
        for nome, valor in (
            ("aluno_id", self.aluno_id),
            ("conjunto_id", self.conjunto_id),
            ("versao_referencia", self.versao_referencia),
        ):
            if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
                raise ValueError(f"{nome} deve ser um inteiro positivo.")


@dataclass(frozen=True, slots=True)
class ReferenciaIdentidade:
    """Uma referência ativa e ordinal de um único conjunto versionado."""

    aluno_id: int
    conjunto_id: int
    versao: int
    ordinal: int
    embedding: FaceEmbedding


@dataclass(frozen=True, slots=True)
class DecisaoIdentidade:
    """Decisão interna sem imagem, embedding ou identificador pessoal."""

    identidade_ok: bool
    distancia_mediana: float | None
    versao_referencia: int
    politica: str
    limiar: float
    motivo_tecnico: str | None


class VerificarIdentidade:
    """Compara uma face somente com as três referências já selecionadas."""

    def executar(
        self,
        consulta: FaceEmbedding,
        referencias: Sequence[ReferenciaIdentidade],
        politica: PoliticaVerificacaoIdentidade,
    ) -> DecisaoIdentidade:
        if not isinstance(politica, PoliticaVerificacaoIdentidade):
            raise ValueError("A política de verificação é inválida.")

        invalidas = DecisaoIdentidade(
            identidade_ok=False,
            distancia_mediana=None,
            versao_referencia=politica.versao_referencia,
            politica=POLITICA_VERIFICACAO,
            limiar=LIMIAR_VERIFICACAO,
            motivo_tecnico="referencias_incompativeis",
        )
        if not self._embedding_valido(consulta):
            return DecisaoIdentidade(
                identidade_ok=False,
                distancia_mediana=None,
                versao_referencia=politica.versao_referencia,
                politica=POLITICA_VERIFICACAO,
                limiar=LIMIAR_VERIFICACAO,
                motivo_tecnico="consulta_invalida",
            )
        if (
            consulta.modelo != MODELO_WEB
            or not isinstance(referencias, Sequence)
            or len(referencias) != 3
        ):
            return invalidas

        ordinais: set[int] = set()
        distancias: list[float] = []
        for referencia in referencias:
            if not isinstance(referencia, ReferenciaIdentidade):
                return invalidas
            if (
                any(
                    isinstance(valor, bool) or not isinstance(valor, int)
                    for valor in (
                        referencia.aluno_id,
                        referencia.conjunto_id,
                        referencia.versao,
                        referencia.ordinal,
                    )
                )
                or referencia.aluno_id != politica.aluno_id
                or referencia.conjunto_id != politica.conjunto_id
                or referencia.versao != politica.versao_referencia
                or referencia.ordinal not in (1, 2, 3)
                or referencia.ordinal in ordinais
                or not self._embedding_valido(referencia.embedding)
                or referencia.embedding.modelo != MODELO_WEB
            ):
                return invalidas
            ordinais.add(referencia.ordinal)
            distancia = self._distancia(consulta, referencia.embedding)
            if distancia is None:
                return invalidas
            distancias.append(distancia)

        if ordinais != {1, 2, 3}:
            return invalidas

        distancia_mediana = float(median(distancias))
        # Os vetores canônicos são float32; tolera-se apenas o arredondamento
        # de uma ULP no limite inclusivo, sem alterar o limiar operacional.
        identidade_ok = distancia_mediana <= LIMIAR_VERIFICACAO or isclose(
            distancia_mediana,
            LIMIAR_VERIFICACAO,
            rel_tol=0.0,
            abs_tol=_TOLERANCIA_FLOAT32,
        )
        return DecisaoIdentidade(
            identidade_ok=identidade_ok,
            distancia_mediana=distancia_mediana,
            versao_referencia=politica.versao_referencia,
            politica=POLITICA_VERIFICACAO,
            limiar=LIMIAR_VERIFICACAO,
            motivo_tecnico=None if identidade_ok else "identidade_nao_confirmada",
        )

    @staticmethod
    def _embedding_valido(embedding: object) -> bool:
        if not isinstance(embedding, FaceEmbedding):
            return False
        vetor = embedding.vetor
        if vetor.shape != (DIMENSAO_EMBEDDING,) or not np.all(np.isfinite(vetor)):
            return False
        norma = float(np.linalg.norm(vetor.astype(np.float64)))
        return isfinite(norma) and isclose(norma, 1.0, rel_tol=0.0, abs_tol=1e-5)

    @classmethod
    def _distancia(
        cls, consulta: FaceEmbedding, referencia: FaceEmbedding
    ) -> float | None:
        if not cls._embedding_valido(consulta) or not cls._embedding_valido(referencia):
            return None
        similaridade = float(
            np.dot(
                consulta.vetor.astype(np.float64),
                referencia.vetor.astype(np.float64),
            )
        )
        if not isfinite(similaridade):
            return None
        return 1.0 - min(1.0, max(-1.0, similaridade))
