"""Embedding facial -- o vetor que representa um rosto.

Invariante da classe: o vetor esta sempre L2-normalizado. Isso importa
porque `DeepFace.represent()` NAO devolve vetor normalizado, e a distancia
cosseno so vira um simples `1 - produto_escalar` depois da normalizacao.
Normalizar na construcao garante que nenhum caminho de codigo compare
vetores em escalas diferentes.

O dominio depende de numpy. E uma biblioteca numerica, nao infraestrutura:
nao amarra o sistema a webcam, a modelo de IA nem a banco. A alternativa --
laco Python sobre 512 floats por aluno, a cada ciclo de video -- seria
lenta o suficiente para reintroduzir o problema que esta fase resolve.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# float32 little-endian: formato canonico do vetor em bytes, usado tanto na
# coluna BYTEA quanto por qualquer exportacao futura.
DTYPE = "<f4"


class EmbeddingInvalido(ValueError):
    """Vetor vazio, com NaN, ou de norma zero."""


@dataclass(frozen=True, slots=True)
class FaceEmbedding:
    vetor: np.ndarray
    modelo: str

    @property
    def dimensao(self) -> int:
        return int(self.vetor.shape[0])

    def para_bytes(self) -> bytes:
        return self.vetor.astype(DTYPE).tobytes()

    def distancia_cosseno(self, outro: FaceEmbedding) -> float:
        """Distancia cosseno entre dois vetores ja normalizados.

        Mesma convencao do DeepFace: 1 - similaridade. Zero e identico.
        """
        if self.modelo != outro.modelo:
            raise EmbeddingInvalido(
                f"Embeddings de modelos diferentes nao sao comparaveis: "
                f"{self.modelo!r} e {outro.modelo!r}."
            )
        return float(1.0 - np.dot(self.vetor, outro.vetor))

    @classmethod
    def de_valores(cls, valores: object, modelo: str) -> FaceEmbedding:
        """Constroi a partir de qualquer sequencia numerica, normalizando."""
        vetor = np.asarray(valores, dtype=DTYPE).ravel()

        if vetor.size == 0:
            raise EmbeddingInvalido("Vetor de embedding vazio.")
        if not np.all(np.isfinite(vetor)):
            raise EmbeddingInvalido("Vetor de embedding contem NaN ou infinito.")

        norma = float(np.linalg.norm(vetor))
        if norma == 0.0:
            raise EmbeddingInvalido("Vetor de embedding tem norma zero.")

        return cls(vetor=(vetor / norma).astype(DTYPE), modelo=modelo)

    @classmethod
    def de_bytes(cls, dados: bytes, modelo: str) -> FaceEmbedding:
        return cls.de_valores(np.frombuffer(dados, dtype=DTYPE), modelo)
