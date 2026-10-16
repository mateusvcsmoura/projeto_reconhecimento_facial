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
from src.application.use_cases.consultar import ListarAlunos, ListarPresencasDoDia
from src.application.use_cases.excluir_aluno import ExcluirAluno
from src.application.use_cases.gerenciar_turmas import GerenciarTurmas
from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.config.logging import configurar_logging
from src.config.settings import Settings, get_settings
from src.domain.entities.turma import Turma
from src.domain.errors import ErroDeDominio
from src.domain.services.captura_automatica import ParametrosCapturaAutomatica
from src.domain.services.consistencia_temporal import ParametrosTemporais
from src.domain.services.facial_landmarks import LandmarksProvider
from src.domain.services.matcher import PoliticaAmbiguidade
from src.domain.services.qualidade_captura import ParametrosQualidade
from src.infrastructure.camera.opencv_camera import OpenCVCamera
from src.infrastructure.database.engine import criar_engine
from src.infrastructure.face_recognition.deepface_adapter import DeepFaceAdapter
from src.infrastructure.repositories.postgres_aluno_repository import (
    PostgresAlunoRepository,
)
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)
from src.infrastructure.repositories.postgres_turma_repository import (
    PostgresTurmaRepository,
)
from src.infrastructure.storage.local_image_storage import LocalImageStorage
from src.presentation.cli.menu import MenuCLI
from src.presentation.cli.turmas import TurmasCLI
from src.presentation.cli.viewer import JanelaDeVideo

logger = logging.getLogger(__name__)


def montar_menu(settings: Settings) -> TurmasCLI:
    ambiguidade: PoliticaAmbiguidade | None = None
    if settings.face_ambiguity_enabled:
        margem = settings.face_ambiguity_min_margin
        if margem is None:
            # Settings valida isto antes da composicao; o guard protege
            # construcoes artificiais sem introduzir um fallback silencioso.
            raise ValueError(
                "FACE_AMBIGUITY_MIN_MARGIN e obrigatoria quando "
                "FACE_AMBIGUITY_ENABLED=true."
            )
        ambiguidade = PoliticaAmbiguidade(margem)

    engine = criar_engine(settings.database_url)

    alunos = PostgresAlunoRepository(engine)
    presencas = PostgresPresencaRepository(engine)
    gerenciar_turmas = GerenciarTurmas(
        PostgresTurmaRepository(engine), settings.timezone
    )
    storage = LocalImageStorage(settings.storage_dir)
    qualidade = (
        ParametrosQualidade(
            min_face_px=settings.face_quality_min_face_px,
            min_brightness=settings.face_quality_min_brightness,
            max_brightness=settings.face_quality_max_brightness,
            min_sharpness=settings.face_quality_min_sharpness,
        )
        if settings.face_quality_enabled
        else None
    )
    temporal = (
        ParametrosTemporais(
            min_observacoes=settings.face_temporal_min_observations,
            janela_segundos=settings.face_temporal_window_seconds,
            validade_segundos=settings.face_temporal_max_age_seconds,
        )
        if settings.face_temporal_enabled
        else None
    )
    captura_automatica = (
        ParametrosCapturaAutomatica(
            espera_segundos=settings.face_auto_capture_wait_seconds,
            intervalo_amostragem_segundos=settings.face_auto_capture_sample_seconds,
            idade_maxima_segundos=settings.face_auto_capture_max_age_seconds,
        )
        if settings.face_auto_capture_enabled
        else None
    )
    reconhecimento = DeepFaceAdapter(
        modelo=settings.face_model,
        detector=settings.face_detector,
        anti_spoofing=settings.face_anti_spoofing,
        qualidade=qualidade,
    )

    if not settings.face_anti_spoofing:
        logger.warning(
            "Anti-spoofing DESLIGADO: o sistema aceita foto impressa ou tela "
            "no lugar da pessoa. Use apenas em desenvolvimento."
        )

    def abrir_janela(titulo: str) -> JanelaDeVideo:
        if not settings.face_landmarks_enabled or titulo != "Cadastro facial":
            return JanelaDeVideo(titulo)

        def criar_landmarks() -> LandmarksProvider:
            # Import e inicializacao ficam adiados ate a sessao de cadastro.
            from src.infrastructure.face_recognition.mediapipe_landmarks import (
                MediaPipeLandmarks,
            )

            return MediaPipeLandmarks(
                settings.face_landmarks_model_path,
                python_executable=settings.face_landmarks_python_path,
            )

        return JanelaDeVideo(titulo, criar_landmarks=criar_landmarks)

    cadastrar_aluno = CadastrarAluno(alunos, reconhecimento, storage, settings.timezone)
    reconhecer_aluno = ReconhecerAluno(
        alunos,
        reconhecimento,
        modelo=settings.face_model,
        limiar=settings.face_threshold,
        ambiguidade=ambiguidade,
    )
    registrar_presenca = RegistrarPresenca(presencas, settings.timezone)
    excluir_aluno = ExcluirAluno(alunos, storage)
    listar_alunos = ListarAlunos(alunos, settings.face_model)
    listar_presencas = ListarPresencasDoDia(presencas, settings.timezone)

    def abrir_turma(turma: Turma) -> None:
        if turma.id is None:
            raise ValueError("A selecao exige uma turma persistida.")
        menu_turma = MenuCLI(
            cadastrar_aluno=cadastrar_aluno,
            reconhecer_aluno=reconhecer_aluno,
            registrar_presenca=registrar_presenca,
            excluir_aluno=excluir_aluno,
            listar_alunos=listar_alunos,
            listar_presencas=listar_presencas,
            turma=turma,
            gerenciar_turmas=gerenciar_turmas,
            limiar=settings.face_threshold,
            abrir_camera=lambda: OpenCVCamera(
                settings.camera_index,
                largura=settings.camera_largura,
                altura=settings.camera_altura,
                backend=settings.camera_backend,
            ),
            abrir_janela=abrir_janela,
            temporal=temporal,
            captura_automatica=captura_automatica,
        )
        menu_turma.executar()

    return TurmasCLI(
        gerenciar_turmas=gerenciar_turmas,
        listar_presencas=listar_presencas,
        excluir_aluno=excluir_aluno,
        abrir_turma=abrir_turma,
        preaquecer=cadastrar_aluno.preaquecer,
    )


def _preaquecer(menu: TurmasCLI, modelo: str) -> None:
    """Carrega o modelo antes de abrir a camera.

    Na primeira execucao o DeepFace baixa os pesos, o que leva minutos. Sem
    isto, a espera acontece com a camera ja aberta e o aluno parado na
    frente dela, sem nenhuma explicacao na tela.
    """
    print(f"Carregando o modelo {modelo}...")
    print("Na primeira execucao os pesos sao baixados; pode demorar.")
    try:
        menu.preaquecer()
    except ErroDeDominio as erro:
        # Nao e fatal: o operador ainda pode listar alunos e presencas.
        print(f"AVISO: {erro}")
        print("As funcoes de camera ficarao indisponiveis.")
    else:
        print("Modelo pronto.")


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
        menu = montar_menu(settings)
        _preaquecer(menu, settings.face_model)
        menu.executar()
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
