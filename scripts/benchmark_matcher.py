"""Mede o custo da comparacao por embeddings, variando o numero de alunos.

O que este benchmark mostra e o que ele NAO mostra:

  * mostra: o custo da comparacao em si, que e o que a Fase 5 mudou --
    de ate 2N inferencias Facenet512 por ciclo para uma multiplicacao
    matriz-vetor;
  * nao mostra: o custo da inferencia. Esse e o mesmo de antes, so que
    agora acontece UMA vez por ciclo em vez de 2N.

Nao requer DeepFace: opera sobre vetores sinteticos de 512 dimensoes.

    python -m scripts.benchmark_matcher
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.domain.entities.face_embedding import FaceEmbedding  # noqa: E402
from src.domain.services.matcher import MatrizDeReferencia  # noqa: E402

MODELO = "Facenet512"
DIMENSAO = 512
TAMANHOS = (10, 50, 200, 1000)
REPETICOES = 2000

# Custo tipico de uma inferencia Facenet512 em CPU. Serve apenas para
# dimensionar a ordem de grandeza do desenho antigo; nao e medicao.
CUSTO_INFERENCIA_MS = 80.0


def montar_referencia(n: int, rng: np.random.Generator) -> MatrizDeReferencia:
    pares = [
        (i, FaceEmbedding.de_valores(rng.random(DIMENSAO), MODELO)) for i in range(n)
    ]
    return MatrizDeReferencia.de_embeddings(pares)


def main() -> int:
    rng = np.random.default_rng(seed=1234)
    consulta = FaceEmbedding.de_valores(rng.random(DIMENSAO), MODELO)

    print(f"Vetores de {DIMENSAO} dimensoes | {REPETICOES} repeticoes por tamanho\n")
    print(f"{'alunos':>7} | {'comparacao':>12} | {'ciclos/s':>10} | {'antes (2N inf.)':>16}")
    print("-" * 56)

    for n in TAMANHOS:
        referencia = montar_referencia(n, rng)

        referencia.melhor_candidato(consulta, 2.0)  # aquece

        inicio = time.perf_counter()
        for _ in range(REPETICOES):
            referencia.melhor_candidato(consulta, 2.0)
        decorrido = time.perf_counter() - inicio

        por_ciclo_ms = (decorrido / REPETICOES) * 1000
        ciclos_por_s = REPETICOES / decorrido
        antes_ms = 2 * n * CUSTO_INFERENCIA_MS

        print(
            f"{n:>7} | {por_ciclo_ms:>9.4f} ms | {ciclos_por_s:>10.0f} |"
            f" {antes_ms:>13.0f} ms"
        )

    print(
        "\nA coluna 'antes' e uma estimativa do desenho anterior "
        f"(2N x {CUSTO_INFERENCIA_MS:.0f} ms de inferencia), nao uma medicao."
        "\nO custo real por ciclo hoje e: uma inferencia + a coluna 'comparacao'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
