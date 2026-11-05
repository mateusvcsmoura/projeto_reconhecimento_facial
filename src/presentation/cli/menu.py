"""Menu e lacos interativos da CLI.

Esta camada decide *o que mostrar e quando*; nao decide regra de negocio e
nao acessa banco. Camera e janela chegam injetadas, entao o menu inteiro e
exercitavel em teste com dubles -- sem webcam e sem OpenCV instalado.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from time import monotonic
from types import TracebackType
from typing import Any, Protocol

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.consultar import (
    ListarAlunos,
    ListarPresencasDoDia,
)
from src.application.use_cases.excluir_aluno import ExcluirAluno
from src.application.use_cases.gerenciar_turmas import GerenciarTurmas
from src.application.use_cases.reconhecer_aluno import (
    ReconhecerAluno,
    Reconhecimento,
)
from src.application.use_cases.registrar_presenca import RegistrarPresenca
from src.domain.entities.aluno import Aluno
from src.domain.entities.turma import Turma
from src.domain.errors import (
    AlunoSemConsentimento,
    DadosInvalidos,
    ErroDeDominio,
    FalhaNaLeituraDaCamera,
    IdentificacaoAmbigua,
    QualidadeCapturaInsuficiente,
)
from src.domain.services.camera_provider import CameraProvider
from src.domain.services.captura_automatica import ParametrosCapturaAutomatica
from src.domain.services.consistencia_temporal import (
    ConfirmadorTemporal,
    EstadoTemporal,
    ParametrosTemporais,
)
from src.domain.services.matcher import MatrizDeReferencia
from src.presentation.cli import prompts
from src.presentation.cli.captura_automatica import CapturaAutomaticaCLI
from src.presentation.cli.confianca import rotulo_de_estado
from src.presentation.cli.mensagens import para_operador
from src.presentation.cli.teclas import AMARELO, BRANCO, ENTER, ESC, ESPACO, VERDE

logger = logging.getLogger(__name__)

# Compara a cada N frames. Com o embedding persistido o custo por ciclo
# caiu de ate 2N inferencias para uma, mas essa uma ainda e cara o bastante
# para nao caber em todo quadro.
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
        excluir_aluno: ExcluirAluno,
        listar_alunos: ListarAlunos,
        listar_presencas: ListarPresencasDoDia,
        turma: Turma,
        gerenciar_turmas: GerenciarTurmas,
        limiar: float,
        abrir_camera: Callable[[], CameraProvider],
        abrir_janela: Callable[[str], Janela],
        ler: prompts.Leitor = input,
        escrever: Callable[[str], None] = print,
        temporal: ParametrosTemporais | None = None,
        captura_automatica: ParametrosCapturaAutomatica | None = None,
        relogio: Callable[[], float] = monotonic,
    ) -> None:
        self._cadastrar_aluno = cadastrar_aluno
        self._reconhecer_aluno = reconhecer_aluno
        self._registrar_presenca = registrar_presenca
        self._excluir_aluno = excluir_aluno
        self._listar_alunos = listar_alunos
        self._listar_presencas = listar_presencas
        if turma.id is None:
            raise ValueError("O menu exige uma turma persistida.")
        self._turma = turma
        self._turma_id = turma.id
        self._gerenciar_turmas = gerenciar_turmas
        self._voltar_ao_menu_principal = False
        self._limiar = limiar
        self._abrir_camera = abrir_camera
        self._abrir_janela = abrir_janela
        self._ler = ler
        self._escrever = escrever
        self._temporal = temporal
        self._relogio = relogio
        self._fluxo_automatico = (
            CapturaAutomaticaCLI(
                cadastrar_aluno=cadastrar_aluno,
                reconhecer_aluno=reconhecer_aluno,
                registrar=self._registrar,
                abrir_camera=abrir_camera,
                abrir_janela=abrir_janela,
                parametros=captura_automatica,
                temporal=temporal,
                relogio=relogio,
                escrever=escrever,
                turma_id=self._turma_id,
            )
            if captura_automatica is not None
            else None
        )

    def preaquecer(self) -> None:
        """Repassa o pre-aquecimento ao provider de reconhecimento."""
        self._cadastrar_aluno.preaquecer()

    # -- laco principal ---------------------------------------------------

    def executar(self) -> None:
        acoes: dict[str, Callable[[], None]] = {
            "1": self.cadastrar,
            "2": self.vincular,
            "3": self.listar,
            "4": self.reconhecer,
            "5": self.presencas_de_hoje,
            "6": self.desvincular,
            "7": self.atualizar_turma,
            "8": self.excluir_turma,
        }

        try:
            while not self._voltar_ao_menu_principal:
                self._mostrar_menu()
                opcao = prompts.perguntar_opcao(
                    {"1", "2", "3", "4", "5", "6", "7", "8", "9"},
                    self._ler,
                )

                if opcao == "9":
                    self._escrever("Encerrando... Voltando da turma ao menu principal.")
                    return
                if opcao is None:
                    self._escrever("Opcao invalida.")
                    continue

                try:
                    acoes[opcao]()
                except ErroDeDominio as erro:
                    logger.warning("Operacao interrompida: %s", type(erro).__name__)
                    self._escrever(f"ERRO: {para_operador(erro)}")
        finally:
            # A galeria e o mapa de IDs pertencem somente a esta sessao.
            # Trocar de turma sempre exige nova consulta filtrada no SQL.
            self._reconhecer_aluno.limpar_contexto()

    def _mostrar_menu(self) -> None:
        self._escrever("\n==============================")
        self._escrever(
            f" TURMA {self._turma_id}: {self._turma.materia} "
            f"({self._turma.periodo.value})"
        )
        self._escrever("==============================")
        self._escrever("1 - Cadastrar novo aluno nesta turma")
        self._escrever("2 - Vincular aluno existente por matricula")
        self._escrever("3 - Listar alunos vinculados")
        self._escrever("4 - Reconhecer e registrar presenca nesta turma")
        self._escrever("5 - Consultar presencas da turma")
        self._escrever("6 - Remover aluno desta turma")
        self._escrever("7 - Atualizar materia/periodo")
        self._escrever("8 - Excluir turma (preserva historico)")
        self._escrever("9 - Voltar / trocar turma")

    # -- cadastro ---------------------------------------------------------

    def cadastrar(self) -> None:
        self._escrever("\n=== CADASTRO DE ALUNO ===")

        nome = prompts.perguntar("Nome do aluno: ", self._ler)
        matricula = prompts.perguntar("Matricula: ", self._ler)

        # Valida ANTES de acender a camera: nao faz sentido pedir o rosto do
        # aluno para so entao descobrir que a matricula esta duplicada.
        matricula, nome = self._cadastrar_aluno.validar_identificacao(
            matricula, nome, turma_id=self._turma_id
        )

        # O termo vem ANTES de a camera ligar. Coletar a biometria para so
        # entao perguntar inverteria a ordem que a LGPD exige.
        if not self._colher_consentimento(nome):
            self._escrever("Cadastro cancelado: sem consentimento.")
            return

        self._escrever("\nPosicione o rosto dentro da camera.")
        if self._fluxo_automatico is not None:
            aluno = self._fluxo_automatico.cadastrar(matricula, nome)
            if aluno is None:
                self._escrever("Cadastro cancelado.")
                return
            self._exibir_cadastro_concluido(aluno)
            return

        self._escrever("ESPACO captura | ESC cancela.")

        while True:
            imagem = self._capturar_rosto()
            if imagem is None:
                self._escrever("Cadastro cancelado.")
                return

            try:
                aluno = self._cadastrar_aluno.executar(
                    matricula, nome, imagem, consentiu=True, turma_id=self._turma_id
                )
            except QualidadeCapturaInsuficiente as erro:
                self._escrever(f"ERRO: {para_operador(erro)}")
                continue
            break

        self._exibir_cadastro_concluido(aluno)

    def _exibir_cadastro_concluido(self, aluno: Aluno) -> None:
        self._escrever("\nCADASTRO REALIZADO COM SUCESSO!")
        self._escrever(f"Aluno: {aluno.nome}")
        self._escrever(f"Matricula: {aluno.matricula}")

    def _colher_consentimento(self, nome: str) -> bool:
        """Termo de consentimento, exibido antes de qualquer captura.

        O rosto so e pedido depois do "sim". Coletar a biometria para so
        entao perguntar inverteria a ordem que a LGPD exige.
        """
        self._escrever("")
        self._escrever("--- CONSENTIMENTO (LGPD art. 11) ---")
        self._escrever(
            f"{nome}, o sistema vai registrar a sua imagem facial e um vetor"
        )
        self._escrever("derivado dela, com a unica finalidade de controlar a presenca.")
        self._escrever(
            "Voce pode pedir a exclusao global dos dados a qualquer momento."
        )
        resposta = prompts.perguntar("Voce concorda? (s/N): ", self._ler)
        return resposta.strip().lower() in {"s", "sim"}

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

    # -- consultas --------------------------------------------------------

    def listar(self) -> None:
        alunos = self._listar_alunos.executar(turma_id=self._turma_id)

        self._escrever(
            f"\n=== ALUNOS DA TURMA {self._turma_id}: {self._turma.materia} ==="
        )
        if not alunos:
            self._escrever("Nenhum aluno cadastrado ainda. Use a opcao 1.")
            return

        self._escrever(f"{'MATRICULA':<12} {'NOME':<32} SITUACAO")
        self._escrever("-" * 60)
        for item in alunos:
            self._escrever(
                f"{item.aluno.matricula:<12} {item.aluno.nome[:32]:<32} {item.situacao}"
            )

        pendentes = [a for a in alunos if not a.pronto_para_reconhecimento]
        self._escrever(f"\nTotal: {len(alunos)} aluno(s)")
        if pendentes:
            # Estes alunos existem no cadastro mas sao invisiveis ao
            # reconhecimento. Melhor descobrir agora do que durante a aula.
            self._escrever(
                f"ATENCAO: {len(pendentes)} sem embedding do modelo em uso. "
                "Rode 'python -m scripts.backfill_embeddings --apply'."
            )

    def presencas_de_hoje(self) -> None:
        dia_texto = prompts.perguntar("Dia (AAAA-MM-DD; vazio = hoje): ", self._ler)
        if dia_texto:
            try:
                dia = dt.date.fromisoformat(dia_texto)
            except ValueError as erro:
                raise DadosInvalidos("Informe a data no formato AAAA-MM-DD.") from erro
        else:
            dia = self._listar_presencas.hoje()
        registros = self._listar_presencas.executar(dia, turma_id=self._turma_id)

        self._escrever(
            f"\n=== PRESENCAS DA TURMA {self._turma_id} "
            f"({dia.strftime('%d/%m/%Y')}) ==="
        )
        if not registros:
            self._escrever("Nenhuma presenca registrada hoje.")
            return

        self._escrever(f"{'HORA':<7} {'MATRICULA':<12} NOME")
        self._escrever("-" * 52)
        for registro in registros:
            hora = self._listar_presencas.horario_local(registro)
            self._escrever(f"{hora:<7} {registro.matricula:<12} {registro.nome}")

        self._escrever(f"\nTotal: {len(registros)} presenca(s)")

    # -- exclusao ---------------------------------------------------------

    def vincular(self) -> None:
        self._escrever("\n=== VINCULAR ALUNO EXISTENTE ===")
        self._escrever(
            "A biometria e o consentimento permanecem no cadastro global do aluno."
        )
        matricula = prompts.perguntar("Matricula: ", self._ler)
        aluno = self._excluir_aluno.localizar(matricula)
        self._escrever(f"\nAluno: {aluno.nome} (matricula {aluno.matricula})")
        if aluno.consentimento_em is None:
            raise AlunoSemConsentimento(aluno.matricula)
        confirmacao = prompts.perguntar(
            "Confirma o vinculo a esta turma? (s/N): ", self._ler
        )
        if confirmacao.strip().lower() not in {"s", "sim"}:
            self._escrever("Vinculo cancelado.")
            return
        _aluno, criado = self._gerenciar_turmas.vincular(
            self._turma_id, aluno.matricula
        )
        if criado:
            self._escrever("Aluno vinculado a esta turma. Cadastro global preservado.")
        else:
            self._escrever("Aluno ja estava vinculado a esta turma.")

    def desvincular(self) -> None:
        self._escrever("\n=== REMOVER ALUNO DESTA TURMA ===")
        self._escrever(
            "Isso preserva o cadastro global, a biometria e o historico de presencas."
        )
        matricula = prompts.perguntar("Matricula: ", self._ler)
        aluno = self._excluir_aluno.localizar(matricula)
        self._escrever(f"Aluno: {aluno.nome} (matricula {aluno.matricula})")
        confirmacao = prompts.perguntar(
            "Confirma remover somente desta turma? (s/N): ", self._ler
        )
        if confirmacao.strip().lower() not in {"s", "sim"}:
            self._escrever("Remocao cancelada.")
            return
        self._gerenciar_turmas.desvincular(self._turma_id, aluno.matricula)
        self._escrever("Aluno removido desta turma; cadastro e historico preservados.")

    def atualizar_turma(self) -> None:
        self._escrever("\n=== ATUALIZAR TURMA ===")
        materia = prompts.perguntar("Materia: ", self._ler)
        periodo = prompts.perguntar("Periodo (matutino/diurno/noturno): ", self._ler)
        self._turma = self._gerenciar_turmas.atualizar(self._turma_id, materia, periodo)
        self._escrever(
            f"Turma atualizada: {self._turma_id} - {self._turma.materia} "
            f"({self._turma.periodo.value})."
        )

    def excluir_turma(self) -> None:
        self._escrever("\n=== EXCLUSAO LOGICA DA TURMA ===")
        self._escrever(
            "A turma sai das operacoes ativas; alunos e historico de presencas "
            "permanecem consultaveis."
        )
        confirmacao = prompts.perguntar(
            "Confirma excluir esta turma? (s/N): ", self._ler
        )
        if confirmacao.strip().lower() not in {"s", "sim"}:
            self._escrever("Exclusao da turma cancelada.")
            return
        self._gerenciar_turmas.excluir(self._turma_id)
        self._escrever("Turma excluida logicamente; o historico foi preservado.")
        self._voltar_ao_menu_principal = True

    # -- reconhecimento ---------------------------------------------------

    def reconhecer(self) -> None:
        # Recarrega a cada entrada no modo: cadastros feitos depois da ultima
        # visita passam a valer imediatamente (problema A15).
        referencias = self._reconhecer_aluno.carregar_referencias(
            turma_id=self._turma_id
        )
        if len(referencias) == 0:
            self._escrever("Nenhum aluno com embedding cadastrado.")
            return

        self._escrever("\n=== RECONHECIMENTO FACIAL ===")
        self._escrever("Olhe para a camera.")
        if self._fluxo_automatico is not None:
            self._escrever("A captura e automatica | ESC sai.")
            self._fluxo_automatico.reconhecer(referencias)
            return

        if self._temporal is None:
            self._escrever("ENTER registra a presenca | ESC sai.")
        else:
            self._escrever("ENTER confirma identidade e registra | ESC sai.")

        self._laco_de_reconhecimento(referencias)

    def _laco_de_reconhecimento(self, referencias: MatrizDeReferencia) -> None:
        if self._temporal is not None:
            self._laco_temporal_de_reconhecimento(referencias, self._temporal)
            return

        rodape: Linha = ("ENTER = registrar | ESC = sair", BRANCO)
        reconhecido: Reconhecimento | None = None
        situacao = "Procurando..."
        cor_situacao = BRANCO
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
                    try:
                        reconhecido = self._reconhecer_aluno.identificar(
                            frame, referencias, turma_id=self._turma_id
                        )
                    except (QualidadeCapturaInsuficiente, IdentificacaoAmbigua) as erro:
                        reconhecido = None
                        situacao = para_operador(erro)
                        cor_situacao = AMARELO
                    else:
                        situacao, cor_situacao = rotulo_de_estado(
                            reconhecido.aluno.nome if reconhecido else None,
                            reconhecido.distancia if reconhecido else None,
                            self._limiar,
                        )

                tecla = janela.mostrar(frame, [(situacao, cor_situacao), rodape])

                if tecla == ESC:
                    return
                if tecla == ENTER and reconhecido is not None:
                    self._registrar(reconhecido.aluno)

    def _laco_temporal_de_reconhecimento(
        self,
        referencias: MatrizDeReferencia,
        parametros: ParametrosTemporais,
    ) -> None:
        confirmador = ConfirmadorTemporal(parametros)
        rodape: Linha = (
            "ENTER = confirmar identidade e registrar | ESC = sair",
            BRANCO,
        )
        reconhecido: Reconhecimento | None = None
        estado = EstadoTemporal(aluno_id=None, observacoes=0, confirmado=False)
        situacao = "Procurando..."
        cor_situacao = BRANCO
        contador = 0
        recusa_recuperavel = False

        with (
            self._abrir_camera() as camera,
            self._abrir_janela("Reconhecimento") as janela,
        ):
            while True:
                capturado_em = self._relogio()
                try:
                    frame = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    logger.error("Leitura da camera falhou: %s", erro)
                    self._escrever(f"ERRO: {para_operador(erro)}")
                    return

                contador += 1
                comparacao = contador % INTERVALO_DE_COMPARACAO == 0
                if comparacao:
                    try:
                        reconhecido = self._reconhecer_aluno.identificar(
                            frame, referencias, turma_id=self._turma_id
                        )
                    except (
                        QualidadeCapturaInsuficiente,
                        IdentificacaoAmbigua,
                    ) as erro:
                        reconhecido = None
                        confirmador.observar(None, capturado_em)
                        estado = confirmador.consultar(self._relogio())
                        situacao = para_operador(erro)
                        cor_situacao = AMARELO
                        recusa_recuperavel = True
                    else:
                        recusa_recuperavel = False
                        if reconhecido is None:
                            confirmador.observar(None, capturado_em)
                            estado = confirmador.consultar(self._relogio())
                            reconhecido = None
                            situacao = "Procurando..."
                            cor_situacao = BRANCO
                        else:
                            observado = confirmador.observar(
                                reconhecido.aluno.id, capturado_em
                            )
                            estado = confirmador.consultar(self._relogio())
                            if (
                                observado.observacoes and not estado.observacoes
                            ) or estado.aluno_id != reconhecido.aluno.id:
                                reconhecido = None
                                situacao = (
                                    "Reconhecimento expirado. "
                                    "Olhe para a camera novamente."
                                )
                                cor_situacao = AMARELO
                            else:
                                situacao, cor_situacao = self._rotulo_temporal(
                                    estado, reconhecido, parametros.min_observacoes
                                )
                else:
                    estado_anterior = estado
                    estado = confirmador.consultar(self._relogio())
                    if estado_anterior.observacoes and not estado.observacoes:
                        reconhecido = None
                        situacao = (
                            "Reconhecimento expirado. Olhe para a camera novamente."
                        )
                        cor_situacao = AMARELO
                    elif (
                        reconhecido is not None
                        and estado.aluno_id == reconhecido.aluno.id
                        and (
                            estado.observacoes != estado_anterior.observacoes
                            or estado.confirmado != estado_anterior.confirmado
                        )
                    ):
                        situacao, cor_situacao = self._rotulo_temporal(
                            estado, reconhecido, parametros.min_observacoes
                        )

                tecla = janela.mostrar(frame, [(situacao, cor_situacao), rodape])

                if tecla == ESC:
                    return
                if tecla != ENTER:
                    continue

                estado_anterior = estado
                estado = confirmador.consultar(self._relogio())
                expirou = bool(estado_anterior.observacoes and not estado.observacoes)
                if expirou:
                    reconhecido = None
                    situacao = "Reconhecimento expirado. Olhe para a camera novamente."
                    cor_situacao = AMARELO

                if (
                    reconhecido is None
                    or not estado.confirmado
                    or estado.aluno_id != reconhecido.aluno.id
                ):
                    if expirou:
                        continue
                    if not recusa_recuperavel:
                        situacao = "Aguarde a validacao da identidade."
                        cor_situacao = AMARELO
                    continue

                identidade_confirmada = estado.aluno_id
                capturado_em = self._relogio()
                try:
                    frame_confirmacao = camera.ler_frame()
                except FalhaNaLeituraDaCamera as erro:
                    logger.error("Leitura da camera falhou: %s", erro)
                    self._escrever(f"ERRO: {para_operador(erro)}")
                    return

                try:
                    novo_reconhecimento = self._reconhecer_aluno.identificar(
                        frame_confirmacao,
                        referencias,
                        turma_id=self._turma_id,
                    )
                except (
                    QualidadeCapturaInsuficiente,
                    IdentificacaoAmbigua,
                ) as erro:
                    confirmador.observar(None, capturado_em)
                    estado = confirmador.consultar(self._relogio())
                    reconhecido = None
                    situacao = para_operador(erro)
                    cor_situacao = AMARELO
                    recusa_recuperavel = True
                    continue

                if novo_reconhecimento is None:
                    confirmador.observar(None, capturado_em)
                    estado = confirmador.consultar(self._relogio())
                    reconhecido = None
                    situacao = "Procurando..."
                    cor_situacao = BRANCO
                    recusa_recuperavel = False
                    continue

                observado = confirmador.observar(
                    novo_reconhecimento.aluno.id, capturado_em
                )
                estado = confirmador.consultar(self._relogio())
                reconhecido = novo_reconhecimento
                recusa_recuperavel = False

                if observado.observacoes and not estado.observacoes:
                    reconhecido = None
                    situacao = "Reconhecimento expirado. Olhe para a camera novamente."
                    cor_situacao = AMARELO
                    continue

                if novo_reconhecimento.aluno.id != identidade_confirmada:
                    situacao = "Identidade mudou. Aguarde nova validacao."
                    cor_situacao = AMARELO
                    continue

                if (
                    estado.confirmado
                    and estado.aluno_id == identidade_confirmada
                    and estado.aluno_id == novo_reconhecimento.aluno.id
                ):
                    self._registrar(novo_reconhecimento.aluno)
                    confirmador.reiniciar()
                    estado = EstadoTemporal(
                        aluno_id=None, observacoes=0, confirmado=False
                    )
                    reconhecido = None
                    situacao = "Procurando..."
                    cor_situacao = BRANCO
                    continue

                if estado.aluno_id == identidade_confirmada:
                    situacao, cor_situacao = self._rotulo_temporal(
                        estado,
                        novo_reconhecimento,
                        parametros.min_observacoes,
                    )
                else:
                    situacao = "Reconhecimento expirado. Olhe para a camera novamente."
                    cor_situacao = AMARELO

    @staticmethod
    def _rotulo_temporal(
        estado: EstadoTemporal,
        reconhecido: Reconhecimento,
        minimo: int,
    ) -> tuple[str, tuple[int, int, int]]:
        if estado.confirmado and estado.aluno_id == reconhecido.aluno.id:
            return (
                f"Identidade consistente: {reconhecido.aluno.nome}. "
                "ENTER para confirmar.",
                VERDE,
            )
        if estado.observacoes:
            return (
                f"Validando identidade: {estado.observacoes}/{minimo}. "
                "Olhe para a camera.",
                AMARELO,
            )
        return "Procurando...", BRANCO

    def _registrar(self, aluno: Aluno) -> None:
        if self._registrar_presenca.executar(aluno.id, turma_id=self._turma_id):
            self._escrever(f"Presenca registrada: {aluno.nome}")
        else:
            self._escrever(f"Presenca ja registrada hoje: {aluno.nome}")
