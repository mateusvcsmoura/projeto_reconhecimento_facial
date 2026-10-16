"""Navegacao por turma e administracao global da CLI."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable

from src.application.use_cases.consultar import ListarPresencasDoDia
from src.application.use_cases.excluir_aluno import ExcluirAluno
from src.application.use_cases.gerenciar_turmas import GerenciarTurmas
from src.domain.entities.turma import Turma
from src.domain.errors import DadosInvalidos, ErroDeDominio
from src.domain.repositories.presenca_repository import PresencaRegistrada
from src.presentation.cli import prompts
from src.presentation.cli.mensagens import para_operador

logger = logging.getLogger(__name__)


class TurmasCLI:
    """Menu de entrada, selecao de turma e operacoes administrativas globais."""

    def __init__(
        self,
        *,
        gerenciar_turmas: GerenciarTurmas,
        listar_presencas: ListarPresencasDoDia,
        excluir_aluno: ExcluirAluno,
        abrir_turma: Callable[[Turma], None],
        preaquecer: Callable[[], None] = lambda: None,
        ler: prompts.Leitor = input,
        escrever: Callable[[str], None] = print,
    ) -> None:
        self._gerenciar = gerenciar_turmas
        self._listar_presencas = listar_presencas
        self._excluir_aluno = excluir_aluno
        self._abrir_turma = abrir_turma
        self._preaquecer = preaquecer
        self._ler = ler
        self._escrever = escrever

    def preaquecer(self) -> None:
        """Mantido pela composicao para preparar o provider antes dos menus."""
        # O modelo e compartilhado com o fluxo de turma, que ja foi composto
        # pelo callback. A inicializacao real fica delegada a ele.
        self._preaquecer()

    def executar(self) -> None:
        acoes: dict[str, Callable[[], None]] = {
            "1": self.criar_turma,
            "2": self.selecionar_turma,
            "3": self.consultar_turmas_excluidas,
            "4": self.administracao_global,
        }
        while True:
            self._mostrar_menu()
            opcao = prompts.perguntar_opcao({"1", "2", "3", "4", "5"}, self._ler)
            if opcao == "5":
                self._escrever("Encerrando...")
                return
            if opcao is None:
                self._escrever("Opcao invalida.")
                continue
            try:
                acoes[opcao]()
            except ErroDeDominio as erro:
                logger.warning(
                    "Operacao de turma interrompida: %s", type(erro).__name__
                )
                self._escrever(f"ERRO: {para_operador(erro)}")

    def _mostrar_menu(self) -> None:
        self._escrever("\n==============================")
        self._escrever(" TURMAS — CONTROLE DE PRESENCA")
        self._escrever("==============================")
        self._escrever("1 - Criar turma")
        self._escrever("2 - Listar e selecionar turma ativa")
        self._escrever("3 - Consultar turmas excluidas e historico")
        self._escrever("4 - Administracao global de alunos e legado")
        self._escrever("5 - Sair")

    def criar_turma(self) -> None:
        self._escrever("\n=== NOVA TURMA ===")
        materia = prompts.perguntar("Materia: ", self._ler)
        periodo = prompts.perguntar("Periodo (matutino/diurno/noturno): ", self._ler)
        turma = self._gerenciar.criar(materia, periodo)
        self._escrever(
            f"Turma {turma.id} criada: {turma.materia} — {turma.periodo.value}."
        )

    def selecionar_turma(self) -> None:
        turmas = self._gerenciar.listar_ativas()
        if not turmas:
            self._escrever("Nenhuma turma ativa. Crie uma turma para continuar.")
            return
        self._escrever("\n=== TURMAS ATIVAS ===")
        self._mostrar_turmas(turmas)
        turma_id = self._ler_id_turma()
        if turma_id is None:
            return
        self._abrir_turma(self._gerenciar.obter_ativa(turma_id))

    def consultar_turmas_excluidas(self) -> None:
        turmas = self._gerenciar.listar_excluidas()
        if not turmas:
            self._escrever("Nenhuma turma excluida com historico disponivel.")
            return
        self._escrever("\n=== TURMAS EXCLUIDAS — SOMENTE HISTORICO ===")
        self._mostrar_turmas(turmas)
        turma_id = self._ler_id_turma()
        if turma_id is None:
            return
        turma = self._gerenciar.obter(turma_id)
        if turma is None or turma.ativa:
            self._escrever("Selecione uma turma excluida desta lista.")
            return
        dia = self._ler_dia("Dia do historico (AAAA-MM-DD; vazio = hoje): ")
        registros = self._listar_presencas.executar_historico_turma(turma_id, dia)
        self._mostrar_presencas(registros, dia, turma=turma)

    def administracao_global(self) -> None:
        while True:
            self._escrever("\n=== ADMINISTRACAO GLOBAL ===")
            self._escrever("1 - Excluir aluno do sistema (todas as turmas e dados)")
            self._escrever("2 - Consultar presencas sem turma (legado)")
            self._escrever("3 - Voltar")
            opcao = prompts.perguntar_opcao({"1", "2", "3"}, self._ler)
            if opcao in (None, "3"):
                return
            try:
                if opcao == "1":
                    self._excluir_aluno_global()
                else:
                    dia = self._ler_dia(
                        "Dia das presencas legadas (AAAA-MM-DD; vazio = hoje): "
                    )
                    self._mostrar_presencas(
                        self._listar_presencas.executar_legado(dia), dia, legado=True
                    )
            except ErroDeDominio as erro:
                logger.warning(
                    "Administracao global interrompida: %s", type(erro).__name__
                )
                self._escrever(f"ERRO: {para_operador(erro)}")

    def _excluir_aluno_global(self) -> None:
        self._escrever(
            "Esta acao remove o cadastro global, imagem, embedding, vinculos e "
            "presencas do aluno em todas as turmas."
        )
        matricula = prompts.perguntar("Matricula: ", self._ler)
        aluno = self._excluir_aluno.localizar(matricula)
        self._escrever(f"Aluno: {aluno.nome} (matricula {aluno.matricula})")
        confirmacao = prompts.perguntar(
            "Confirma a exclusao global irreversivel? (s/N): ", self._ler
        )
        if confirmacao.strip().lower() not in {"s", "sim"}:
            self._escrever("Exclusao cancelada.")
            return
        self._excluir_aluno.executar(aluno)
        self._escrever("Aluno e seus dados globais foram removidos.")

    def _ler_id_turma(self) -> int | None:
        valor = prompts.perguntar("ID da turma: ", self._ler)
        if not valor.isdecimal() or int(valor) <= 0:
            self._escrever("ID de turma invalido.")
            return None
        return int(valor)

    def _ler_dia(self, rotulo: str) -> dt.date:
        valor = prompts.perguntar(rotulo, self._ler)
        if not valor:
            return self._listar_presencas.hoje()
        try:
            return dt.date.fromisoformat(valor)
        except ValueError as erro:
            raise DadosInvalidos("Informe a data no formato AAAA-MM-DD.") from erro

    def _mostrar_turmas(self, turmas: list[Turma]) -> None:
        for turma in turmas:
            self._escrever(f"ID {turma.id}: {turma.materia} — {turma.periodo.value}")

    def _mostrar_presencas(
        self,
        registros: list[PresencaRegistrada],
        dia: dt.date,
        *,
        turma: Turma | None = None,
        legado: bool = False,
    ) -> None:
        if legado:
            titulo = "PRESENCAS SEM TURMA — LEGADO"
        elif turma is not None:
            titulo = (
                f"HISTORICO DA TURMA {turma.id}: {turma.materia} "
                f"— {turma.periodo.value}"
            )
        else:
            titulo = f"PRESENCAS DA TURMA: {dia:%d/%m/%Y}"
        self._escrever(f"\n=== {titulo} ({dia:%d/%m/%Y}) ===")
        if not registros:
            self._escrever("Nenhuma presenca encontrada nesse dia.")
            return
        self._escrever(f"{'HORA':<7} {'MATRICULA':<12} NOME")
        self._escrever("-" * 52)
        for registro in registros:
            hora = self._listar_presencas.horario_local(registro)
            self._escrever(f"{hora:<7} {registro.matricula:<12} {registro.nome}")
        self._escrever(f"\nTotal: {len(registros)} presenca(s)")
