from __future__ import annotations

from src.domain.entities.turma import Periodo, Turma
from src.presentation.cli.turmas import TurmasCLI


class TurmasFalsas:
    def __init__(self, ativas: list[Turma] | None = None) -> None:
        self.ativas = list(ativas or [])
        self.criacoes: list[tuple[str, str]] = []

    def listar_ativas(self) -> list[Turma]:
        return list(self.ativas)

    def listar_excluidas(self) -> list[Turma]:
        return []

    def criar(self, materia: str, periodo: str) -> Turma:
        nova = Turma.nova(materia, periodo)
        self.criacoes.append((nova.materia, nova.periodo.value))
        return Turma(id=10, materia=nova.materia, periodo=nova.periodo)

    def obter_ativa(self, turma_id: int) -> Turma:
        return next(turma for turma in self.ativas if turma.id == turma_id)

    def obter(self, turma_id: int) -> Turma | None:
        return next((turma for turma in self.ativas if turma.id == turma_id), None)


class PresencasFalsas:
    pass


class ExcluirAlunoFalso:
    pass


def montar(
    respostas: list[str],
    turmas: TurmasFalsas,
    abriu: list[Turma],
) -> tuple[TurmasCLI, list[str]]:
    fila = list(respostas)
    mensagens: list[str] = []
    cli = TurmasCLI(
        gerenciar_turmas=turmas,
        listar_presencas=PresencasFalsas(),
        excluir_aluno=ExcluirAlunoFalso(),
        abrir_turma=abriu.append,
        ler=lambda _rotulo: fila.pop(0),
        escrever=mensagens.append,
    )
    return cli, mensagens


def test_menu_principal_abre_somente_turma_ativa_selecionada() -> None:
    turma = Turma(id=3, materia="IA", periodo=Periodo.DIURNO)
    turmas = TurmasFalsas([turma])
    abriu: list[Turma] = []
    cli, _ = montar(["2", "3", "5"], turmas, abriu)

    cli.executar()

    assert abriu == [turma]


def test_menu_principal_nao_abre_camera_ou_turma_sem_selecao_ativa() -> None:
    abriu: list[Turma] = []
    cli, mensagens = montar(["2", "5"], TurmasFalsas(), abriu)

    cli.executar()

    assert abriu == []
    assert any("turma ativa" in mensagem.lower() for mensagem in mensagens)


def test_criar_turma_coleta_materia_e_periodo_sem_abrir_camera() -> None:
    turmas = TurmasFalsas()
    abriu: list[Turma] = []
    cli, mensagens = montar(
        ["1", "  Matemática   Aplicada ", "noturno", "5"], turmas, abriu
    )

    cli.executar()

    assert turmas.criacoes == [("Matemática Aplicada", "noturno")]
    assert abriu == []
    assert any("criada" in mensagem.lower() for mensagem in mensagens)
