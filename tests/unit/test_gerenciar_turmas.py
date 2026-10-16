from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.gerenciar_turmas import GerenciarTurmas
from src.domain.entities.aluno import Aluno
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import DadosInvalidos

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 10, 16, 12, 0, tzinfo=TZ)


class FakeTurmaRepository:
    def __init__(self) -> None:
        self.criada: tuple[Turma, dt.datetime] | None = None
        self.vinculada: tuple[int, str, dt.datetime] | None = None
        self.desvinculada: tuple[int, str, dt.datetime] | None = None

    def criar(self, turma: Turma, agora: dt.datetime) -> Turma:
        self.criada = (turma, agora)
        return Turma(id=4, materia=turma.materia, periodo=turma.periodo)

    def listar_ativas(self) -> list[Turma]:
        return []

    def listar_excluidas(self) -> list[Turma]:
        return []

    def obter(self, turma_id: int) -> Turma | None:
        return None

    def atualizar(
        self, turma_id: int, materia: str, periodo: Periodo, agora: dt.datetime
    ) -> Turma:
        return Turma(id=turma_id, materia=materia, periodo=periodo)

    def excluir_logicamente(self, turma_id: int, agora: dt.datetime) -> None:
        return None

    def vincular_matricula(
        self, turma_id: int, matricula: str, agora: dt.datetime
    ) -> tuple[Aluno, bool]:
        self.vinculada = (turma_id, matricula, agora)
        return Aluno(id=9, matricula=matricula, nome="Ana"), True

    def desvincular_matricula(
        self, turma_id: int, matricula: str, agora: dt.datetime
    ) -> Aluno:
        self.desvinculada = (turma_id, matricula, agora)
        return Aluno(id=9, matricula=matricula, nome="Ana")


def test_criar_normaliza_materia_e_periodo_e_usa_relogio_local() -> None:
    repositorio = FakeTurmaRepository()
    caso = GerenciarTurmas(repositorio, TZ, relogio=lambda: AGORA)

    turma = caso.criar("  Inteligência   Artificial ", "noturno")

    assert turma == Turma(
        id=4, materia="Inteligência Artificial", periodo=Periodo.NOTURNO
    )
    assert repositorio.criada == (
        Turma.nova("Inteligência Artificial", Periodo.NOTURNO),
        AGORA,
    )


def test_criar_recusa_periodo_invalido_antes_de_chamar_repositorio() -> None:
    repositorio = FakeTurmaRepository()
    caso = GerenciarTurmas(repositorio, TZ, relogio=lambda: AGORA)

    with pytest.raises(DadosInvalidos):
        caso.criar("Matemática", "vespertino")

    assert repositorio.criada is None


def test_vincular_normaliza_matricula_e_informa_se_reativou() -> None:
    repositorio = FakeTurmaRepository()
    caso = GerenciarTurmas(repositorio, TZ, relogio=lambda: AGORA)

    aluno, novo = caso.vincular(4, " 2026001 ")

    assert aluno.matricula == "2026001"
    assert novo
    assert repositorio.vinculada == (4, "2026001", AGORA)


def test_desvincular_encaminha_turma_e_instante_explicitos() -> None:
    repositorio = FakeTurmaRepository()
    caso = GerenciarTurmas(repositorio, TZ, relogio=lambda: AGORA)

    aluno = caso.desvincular(4, "2026001")

    assert aluno.id == 9
    assert repositorio.desvinculada == (4, "2026001", AGORA)
