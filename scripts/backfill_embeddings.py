"""Calcula os embeddings faltantes a partir das imagens ja armazenadas.

    imagem em STORAGE_DIR  ->  inferencia  ->  coluna embedding

Necessario porque a migration 0002 criou as colunas como NULL: alunos
cadastrados antes da Fase 5 tem foto, mas nao tem vetor, e por isso ficam
invisiveis ao reconhecimento.

Tambem e o caminho de troca de modelo: mudar FACE_MODEL invalida todos os
embeddings existentes (vetores de modelos diferentes nao sao comparaveis),
e este script os recalcula.

Uso:
    # simulacao (padrao) -- nao grava nada
    python -m scripts.backfill_embeddings

    # execucao real
    python -m scripts.backfill_embeddings --apply

Requer um ambiente com DeepFace instalado (Python 3.12 ou 3.13).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config.logging import configurar_logging
from src.config.settings import get_settings
from src.domain.errors import ErroDeDominio
from src.infrastructure.database import models
from src.infrastructure.database.engine import criar_engine, sessao

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill de embeddings faciais a partir das imagens"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="efetiva a gravacao (sem esta flag, apenas simula)",
    )
    parser.add_argument(
        "--refazer",
        action="store_true",
        help="recalcula tambem quem ja tem embedding do modelo atual",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configurar_logging(settings.log_level)

    # Importado aqui, e nao no topo: assim `--help` funciona em ambientes
    # sem DeepFace, e a mensagem de erro aponta o problema real.
    try:
        from src.infrastructure.face_recognition.deepface_adapter import (
            DeepFaceAdapter,
        )
    except ImportError as exc:
        print(f"ERRO: DeepFace indisponivel neste ambiente: {exc}", file=sys.stderr)
        print(
            "Use um Python 3.12 ou 3.13 com as dependencias instaladas.",
            file=sys.stderr,
        )
        return 2

    from src.infrastructure.storage.local_image_storage import LocalImageStorage

    reconhecimento = DeepFaceAdapter(
        modelo=settings.face_model, detector=settings.face_detector
    )
    storage = LocalImageStorage(settings.storage_dir)
    engine = criar_engine(settings.database_url)

    calculados = 0
    sem_imagem = 0
    falharam = 0

    with sessao(engine) as session:
        consulta = select(models.Aluno).order_by(models.Aluno.id)
        if not args.refazer:
            consulta = consulta.where(
                (models.Aluno.embedding.is_(None))
                | (models.Aluno.embedding_modelo != settings.face_model)
            )

        alunos = session.scalars(consulta).all()
        print(f"Alunos a processar: {len(alunos)}")

        for aluno in alunos:
            if not aluno.foto_arquivo or not storage.existe(aluno.foto_arquivo):
                sem_imagem += 1
                logger.warning(
                    "Aluno sem imagem utilizavel (id=%s) -- precisa refazer o "
                    "cadastro presencialmente",
                    aluno.id,
                )
                continue

            caminho = storage.caminho_absoluto(aluno.foto_arquivo)
            try:
                embedding = reconhecimento.gerar_embedding(caminho)
            except ErroDeDominio as erro:
                falharam += 1
                logger.error(
                    "Falha ao gerar embedding (id=%s): %s",
                    aluno.id,
                    type(erro).__name__,
                )
                continue

            aluno.embedding = embedding.para_bytes()
            aluno.embedding_modelo = embedding.modelo
            aluno.embedding_dim = embedding.dimensao
            calculados += 1

        if not args.apply:
            session.rollback()

    modo = "APLICADO" if args.apply else "SIMULACAO (nada foi gravado)"
    print(f"\n=== BACKFILL DE EMBEDDINGS -- {modo} ===")
    print(f"Modelo: {settings.face_model}")
    print(f"Calculados: {calculados} | sem imagem: {sem_imagem} | falharam: {falharam}")
    if not args.apply:
        print("Repita com --apply para efetivar.\n")

    return 1 if falharam else 0


if __name__ == "__main__":
    raise SystemExit(main())
