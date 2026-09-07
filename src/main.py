"""Ponto de entrada e composition root.

Unico lugar do sistema que conhece as implementacoes concretas. Todo o
resto conversa por contratos, e por isso e testavel sem webcam, sem GPU e
sem PostgreSQL real.

    python -m src.main

O schema NAO e criado aqui. Migrations sao comando explicito
(`alembic upgrade head`), como manda o CLAUDE.md secao 4.
"""

from __future__ import annotations

import logging
import sys

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.excluir_aluno import ExcluirAluno
from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.config.logging import configurar_logging
from src.config.settings import Settings, get_settings
from src.domain.errors import ErroDeDominio
from src.infrastructure.camera.opencv_camera import OpenCVCamera
from src.infrastructure.database.engine import criar_engine
from src.infrastructure.face_recognition.deepface_adapter import DeepFaceAdapter
from src.infrastructure.repositories.postgres_aluno_repository import (
    PostgresAlunoRepository,
)
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)
from src.infrastructure.storage.local_image_storage import LocalImageStorage
from src.presentation.cli.menu import MenuCLI
from src.presentation.cli.viewer import JanelaDeVideo

logger = logging.getLogger(__name__)


def montar_menu(settings: Settings) -> MenuCLI:
    engine = criar_engine(settings.database_url)

    alunos = PostgresAlunoRepository(engine)
    presencas = PostgresPresencaRepository(engine)
    storage = LocalImageStorage(settings.storage_dir)
    reconhecimento = DeepFaceAdapter(
        modelo=settings.face_model,
        detector=settings.face_detector,
        anti_spoofing=settings.face_anti_spoofing,
    )

    if not settings.face_anti_spoofing:
        logger.warning(
            "Anti-spoofing DESLIGADO: o sistema aceita foto impressa ou tela "
            "no lugar da pessoa. Use apenas em desenvolvimento."
        )

    return MenuCLI(
        cadastrar_aluno=CadastrarAluno(
            alunos, reconhecimento, storage, settings.timezone
        ),
        reconhecer_aluno=ReconhecerAluno(
            alunos,
            reconhecimento,
            modelo=settings.face_model,
            limiar=settings.face_threshold,
        ),
        registrar_presenca=RegistrarPresenca(presencas, settings.timezone),
        excluir_aluno=ExcluirAluno(alunos, storage),
        abrir_camera=lambda: OpenCVCamera(settings.camera_index),
        abrir_janela=JanelaDeVideo,
    )


def main() -> int:
    try:
        settings = get_settings()
    except Exception as exc:
        # Sem configuracao valida nao ha o que executar. Falhar aqui, alto e
        # claro, e melhor do que um default silencioso apontando para o
        # banco errado.
        print(f"ERRO DE CONFIGURACAO: {exc}", file=sys.stderr)
        print("Copie .env.example para .env e ajuste DATABASE_URL.", file=sys.stderr)
        return 2

    configurar_logging(settings.log_level)
    logger.info("Iniciando aplicacao (ambiente de log=%s)", settings.log_level)

    try:
        montar_menu(settings).executar()
    except ErroDeDominio as erro:
        logger.error("Encerrado por erro de dominio: %s", type(erro).__name__)
        print(f"ERRO: {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrompido pelo operador.")
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
