from __future__ import annotations

import datetime as dt

import pytest

from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import DadosInvalidos


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("matutino", Periodo.MATUTINO),
        ("diurno", Periodo.DIURNO),
        ("noturno", Periodo.NOTURNO),
    ],
)
def test_turma_aceita_somente_periodos_definidos(valor: str, esperado: Periodo) -> None:
    turma = Turma.nova(" Matemática   Aplicada ", valor)

    assert turma.periodo is esperado
    assert turma.materia == "Matemática Aplicada"
    assert turma.id is None
    assert turma.ativa


@pytest.mark.parametrize("materia", ["", "   ", "x" * 121])
def test_turma_recusa_materia_vazia_ou_maior_que_120(materia: str) -> None:
    with pytest.raises(DadosInvalidos):
        Turma.nova(materia, "matutino")


@pytest.mark.parametrize("periodo", ["vespertino", "Matutino", " matutino ", ""])
def test_turma_recusa_periodo_fora_do_vocabulario_exato(periodo: str) -> None:
    with pytest.raises(DadosInvalidos):
        Turma.nova("Matemática", periodo)


def test_turma_recusa_identificador_invalido() -> None:
    with pytest.raises(DadosInvalidos):
        Turma(id=0, materia="Matemática", periodo=Periodo.MATUTINO)


def test_turma_excluida_logicamente_nao_esta_ativa() -> None:
    excluida = Turma(
        id=7,
        materia="Matemática",
        periodo=Periodo.NOTURNO,
        excluida_em=dt.datetime(2026, 10, 16, tzinfo=dt.UTC),
    )

    assert not excluida.ativa
