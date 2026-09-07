"""Menu e lacos interativos da CLI.

Esta camada decide *o que mostrar e quando*; nao decide regra de negocio e
nao acessa banco. Camera e janela chegam injetadas, entao o menu inteiro e
exercitavel em teste com dubles -- sem webcam e sem OpenCV instalado
(CLAUDE.md secao 7.4).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from types import TracebackType
from typing import Any, Protocol

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.domain.entities.aluno import Aluno
from src.domain.errors import ErroDeDominio, FalhaNaLeituraDaCamera
from src.domain.services.camera_provider import CameraProvider
from src.presentation.cli import prompts
from src.presentation.cli.mensagens import para_operador
from src.presentation.cli.teclas import BRANCO, ENTER, ESC, ESPACO, VERDE, VERMELHO

logger = logging.getLogger(__name__)

# Compara a cada N frames, para nao travar o video a cada quadro.
# Valor herdado do prototipo; a Fase 5 elimina a necessidade dele.
INTERVALO_DE_COMPARACAO = 8

Linha = tuple[str, tuple[int, int, int]]


class Janela(Protocol):
    """O minimo que o menu precisa de uma janela de video."""

    def __enter__(self) -> Janela: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def mostrar(self, frame: Any, linhas: list[Linha]) -> int: ...


class MenuCLI:
    def __init__(
        self,
        *,
        cadastrar_aluno: CadastrarAluno,
        reconhecer_aluno: ReconhecerAluno,
        registrar_presenca: RegistrarPresenca,
        abrir_camera: Callable[[], CameraProvider],
        abrir_janela: Callable[[str], Janela],
        ler: prompts.Leitor = input,
        escrever: Callable[[str], None] = print,
    ) -> None:
        self._cadastrar_aluno = cadastrar_aluno
        self._reconhecer_aluno = reconhecer_aluno
        self._registrar_presenca = registrar_presenca
        self._abrir_camera = abrir_camera
        self._abrir_janela = abrir_janela
        self._ler = ler
        self._escrever = escrever

    # -- laco principal ---------------------------------------------------

    def executar(self) -> None:
        acoes: dict[str, Callable[[], None]] = {
            "1": self.cadastrar,
            "2": self.reconhecer,
        }

        while True:
            self._mostrar_menu()
            opcao = prompts.perguntar_opcao({"1", "2", "3"}, self._ler)

            if opcao == "3":
                self._escrever("Encerrando...")
                return

            if opcao is None:
                self._escrever("Opcao invalida.")
                continue

            try:
                acoes[opcao]()
            except ErroDeDominio as erro:
                # Erro esperado: vira mensagem, o menu continua de pe.
                logger.warning("Operacao interrompida: %s", type(erro).__name__)
                self._escrever(f"ERRO: {para_operador(erro)}")

    def _mostrar_menu(self) -> None:
        self._escrever("\n==============================")
        self._escrever(" SISTEMA DE RECONHECIMENTO")
        self._escrever("==============================")
        self._escrever("1 - Cadastrar aluno")
        self._escrever("2 - Reconhecer aluno")
        self._escrever("3 - Sair")

    # -- cadastro ---------------------------------------------------------

    def cadastrar(self) -> None:
        self._escrever("\n=== CADASTRO DE ALUNO ===")

        nome = prompts.perguntar("Nome do aluno: ", self._ler)
        matricula = prompts.perguntar("Matricula: ", self._ler)

        # Valida ANTES de acender a camera: nao faz sentido pedir o rosto do
        # aluno para so entao descobrir que a matricula esta duplicada.
        matricula, nome = self._cadastrar_aluno.validar_identificacao(matricula, nome)

        self._escrever("\nPosicione o rosto dentro da camera.")
        self._escrever("ESPACO captura | ESC cancela.")

        imagem = self._capturar_rosto()
        if imagem is None:
            self._escrever("Cadastro cancelado.")
            return

        aluno = self._cadastrar_aluno.executar(matricula, nome, imagem)

        self._escrever("\nCADASTRO REALIZADO COM SUCESSO!")
        self._escrever(f"Aluno: {aluno.nome}")
        self._escrever(f"Matricula: {aluno.matricula}")

    def _capturar_rosto(self) -> Any | None:
        """Devolve o frame capturado, ou None se o operador cancelar."""
        instrucoes: list[Linha] = [("ESPACO = capturar | ESC = cancelar", VERDE)]

        with (
            self._abrir_camera() as camera,
            self._abrir_janela("Cadastro facial") as janela,
        ):
            while True:
                try:
                    frame = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    logger.error("Leitura da camera falhou: %s", erro)
                    self._escrever(f"ERRO: {para_operador(erro)}")
                    return None

                tecla = janela.mostrar(frame, instrucoes)

                if tecla == ESC:
                    return None
                if tecla == ESPACO:
                    return frame

    # -- reconhecimento ---------------------------------------------------

    def reconhecer(self) -> None:
        candidatos = self._reconhecer_aluno.candidatos()
        if not candidatos:
            self._escrever("Nenhum aluno com foto de referencia disponivel.")
            return

        self._escrever("\n=== RECONHECIMENTO FACIAL ===")
        self._escrever("Olhe para a camera.")
        self._escrever("ENTER registra a presenca | ESC sai.")

        self._laco_de_reconhecimento(candidatos)

    def _laco_de_reconhecimento(self, candidatos: list[Aluno]) -> None:
        rodape: Linha = ("ENTER = registrar | ESC = sair", BRANCO)
        reconhecido: Aluno | None = None
        situacao = "Procurando..."
        contador = 0

        with (
            self._abrir_camera() as camera,
            self._abrir_janela("Reconhecimento") as janela,
        ):
            while True:
                try:
                    frame = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    logger.error("Leitura da camera falhou: %s", erro)
                    self._escrever(f"ERRO: {para_operador(erro)}")
                    return

                contador += 1
                if contador % INTERVALO_DE_COMPARACAO == 0:
                    reconhecido = self._reconhecer_aluno.identificar(frame, candidatos)
                    situacao = (
                        f"Reconhecido: {reconhecido.nome}"
                        if reconhecido
                        else "Rosto nao reconhecido"
                    )

                cor = VERDE if reconhecido else VERMELHO
                tecla = janela.mostrar(frame, [(situacao, cor), rodape])

                if tecla == ESC:
                    return
                if tecla == ENTER and reconhecido is not None:
                    self._registrar(reconhecido)

    def _registrar(self, aluno: Aluno) -> None:
        if self._registrar_presenca.executar(aluno.id):
            self._escrever(f"Presenca registrada: {aluno.nome}")
        else:
            self._escrever(f"Presenca ja registrada hoje: {aluno.nome}")
