"""Avaliacao do modelo de reconhecimento facial.

Isto NAO e teste de software. Teste de software verifica se o pipeline faz
o que promete; avaliacao de modelo mede se o modelo ACERTA -- e sao coisas
diferentes (instructions/03-qa.md, secao 4).

Serve para responder com dado uma pergunta que hoje e respondida por
heranca: quanto deve valer FACE_THRESHOLD?

Estrutura esperada do conjunto:

    dataset/
      pessoa-1/  foto-a.jpg  foto-b.jpg  ...
      pessoa-2/  foto-a.jpg  ...

Pares GENUINOS saem de dentro de cada pasta; IMPOSTORES, entre pastas
distintas.

Uso:
    python -m scripts.evaluate_model --dataset ./avaliacao/lfw-subset

Requisitos: Python 3.10/3.11 com DeepFace instalado.

NUNCA versione o conjunto de imagens. Use um dataset publico baixado sob
demanda (LFW, por exemplo) ou imagens locais em storage/ -- jamais no Git.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.metricas import (
    area_sob_a_curva,
    eer,
    far_frr,
    limiar_para_far_maximo,
)
from src.config.logging import configurar_logging
from src.config.settings import get_settings
from src.domain.entities.face_embedding import FaceEmbedding

EXTENSOES = {".jpg", ".jpeg", ".png"}


def carregar_embeddings(
    dataset: Path, provider: object
) -> dict[str, list[FaceEmbedding]]:
    """Um embedding por imagem, agrupado por pessoa."""
    por_pessoa: dict[str, list[FaceEmbedding]] = {}

    for pasta in sorted(p for p in dataset.iterdir() if p.is_dir()):
        imagens = [i for i in sorted(pasta.iterdir()) if i.suffix.lower() in EXTENSOES]
        vetores = []
        for imagem in imagens:
            try:
                vetores.append(provider.gerar_embedding(str(imagem)))  # type: ignore[attr-defined]
            except Exception as erro:
                print(f"  ignorada: {imagem.name} ({type(erro).__name__})")
        if vetores:
            por_pessoa[pasta.name] = vetores

    return por_pessoa


def montar_pares(
    por_pessoa: dict[str, list[FaceEmbedding]],
) -> tuple[np.ndarray, np.ndarray]:
    """Distancias dos pares genuinos e dos impostores."""
    genuinas: list[float] = []
    impostoras: list[float] = []

    for vetores in por_pessoa.values():
        for a, b in itertools.combinations(vetores, 2):
            genuinas.append(a.distancia_cosseno(b))

    pessoas = list(por_pessoa)
    for nome_a, nome_b in itertools.combinations(pessoas, 2):
        for a in por_pessoa[nome_a]:
            for b in por_pessoa[nome_b]:
                impostoras.append(a.distancia_cosseno(b))

    return np.array(genuinas), np.array(impostoras)


def relatar(genuinas: np.ndarray, impostoras: np.ndarray, limiar_atual: float) -> None:
    print(f"\nPares genuinos : {genuinas.size}")
    print(f"Pares impostores: {impostoras.size}")
    print(
        f"\nDistancia genuina  -- media {genuinas.mean():.4f} "
        f"| min {genuinas.min():.4f} | max {genuinas.max():.4f}"
    )
    print(
        f"Distancia impostora -- media {impostoras.mean():.4f} "
        f"| min {impostoras.min():.4f} | max {impostoras.max():.4f}"
    )
    print(f"\nAUC: {area_sob_a_curva(genuinas, impostoras):.4f}")

    ponto_eer = eer(genuinas, impostoras)
    print(
        f"EER: {(ponto_eer.far + ponto_eer.frr) / 2:.4f} "
        f"no limiar {ponto_eer.limiar:.4f}"
    )

    far_atual, frr_atual = far_frr(genuinas, impostoras, limiar_atual)
    print(
        f"\nFACE_THRESHOLD atual ({limiar_atual:.2f}): "
        f"FAR {far_atual:.4f} | FRR {frr_atual:.4f}"
    )

    print("\nLimiar sugerido por teto de FAR:")
    print(f"{'FAR maximo':>11} | {'limiar':>8} | {'FAR':>7} | {'FRR':>7}")
    print("-" * 42)
    for teto in (0.0, 0.001, 0.01, 0.05):
        ponto = limiar_para_far_maximo(genuinas, impostoras, teto)
        if ponto is None:
            print(f"{teto:>11.3f} |  (nenhum limiar atinge este teto)")
            continue
        print(
            f"{teto:>11.3f} | {ponto.limiar:>8.4f} | "
            f"{ponto.far:>7.4f} | {ponto.frr:>7.4f}"
        )

    print(
        "\nPara controle de presenca, escolha pelo teto de FAR: recusar um "
        "aluno legitimo\ncusta uma segunda tentativa; aceitar um impostor "
        "corrompe o registro oficial.\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avaliacao FAR/FRR do modelo")
    parser.add_argument("--dataset", type=Path, required=True)
    args = parser.parse_args(argv)

    settings = get_settings()
    configurar_logging("WARNING")

    if not args.dataset.is_dir():
        print(f"ERRO: diretorio nao encontrado: {args.dataset}", file=sys.stderr)
        return 2

    try:
        from src.infrastructure.face_recognition.deepface_adapter import (
            DeepFaceAdapter,
        )
    except ImportError as exc:
        print(f"ERRO: DeepFace indisponivel: {exc}", file=sys.stderr)
        print("Use um Python 3.10 ou 3.11 com as dependencias.", file=sys.stderr)
        return 2

    # Anti-spoofing desligado aqui: o conjunto de avaliacao e composto de
    # fotografias, e recusa-las derrotaria a propria medicao.
    provider = DeepFaceAdapter(
        modelo=settings.face_model,
        detector=settings.face_detector,
        anti_spoofing=False,
    )

    print(f"Modelo: {settings.face_model} | detector: {settings.face_detector}")
    print(f"Lendo {args.dataset}...")

    por_pessoa = carregar_embeddings(args.dataset, provider)
    if len(por_pessoa) < 2:
        print("ERRO: sao necessarias ao menos 2 pessoas.", file=sys.stderr)
        return 2

    genuinas, impostoras = montar_pares(por_pessoa)
    if genuinas.size == 0:
        print(
            "ERRO: nenhum par genuino. Cada pessoa precisa de 2+ imagens.",
            file=sys.stderr,
        )
        return 2

    relatar(genuinas, impostoras, settings.face_threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
