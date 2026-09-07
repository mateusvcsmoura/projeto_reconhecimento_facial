"""Fase 8 -- listagens para o operador, sem banco e sem camera."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from src.application.use_cases.consultar import ListarAlunos, ListarPresencasDoDia
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from tests.fakes import FakeAlunoRepository, FakePresencaRepository

MODELO = "Facenet512"
TZ = ZoneInfo("America/Sao_Paulo")


def emb() -> FaceEmbedding:
    return FaceEmbedding.de_valores([1.0, 0.0], MODELO)


# -- listagem de alunos ----------------------------------------------------


def test_sem_alunos_a_lista_vem_vazia() -> None:
    caso = ListarAlunos(FakeAlunoRepository(), MODELO)
    assert caso.executar() == []


def test_lista_vem_ordenada_por_nome() -> None:
    repo = FakeAlunoRepository(
        [
            Aluno(id=1, matricula="1", nome="Bruno"),
            Aluno(id=2, matricula="2", nome="Ana"),
        ]
    )

    nomes = [item.aluno.nome for item in ListarAlunos(repo, MODELO).executar()]

    assert nomes == ["Ana", "Bruno"]


def test_aluno_com_embedding_aparece_como_pronto() -> None:
    repo = FakeAlunoRepository([Aluno(id=1, matricula="1", nome="Ana")], {1: emb()})

    item = ListarAlunos(repo, MODELO).executar()[0]

    assert item.pronto_para_reconhecimento is True
    assert item.situacao == "pronto"


def test_aluno_sem_embedding_e_sinalizado() -> None:
    """Ele existe no cadastro, mas e invisivel ao reconhecimento."""
    repo = FakeAlunoRepository([Aluno(id=1, matricula="1", nome="Ana")])

    item = ListarAlunos(repo, MODELO).executar()[0]

    assert item.pronto_para_reconhecimento is False
    assert item.situacao == "sem embedding"


def test_embedding_de_outro_modelo_nao_conta_como_pronto() -> None:
    repo = FakeAlunoRepository(
        [Aluno(id=1, matricula="1", nome="Ana")],
        {1: FaceEmbedding.de_valores([1.0, 0.0], "ArcFace")},
    )

    item = ListarAlunos(repo, MODELO).executar()[0]

    assert item.pronto_para_reconhecimento is False


# -- presencas do dia ------------------------------------------------------


def test_dia_sem_presencas_vem_vazio() -> None:
    caso = ListarPresencasDoDia(FakePresencaRepository(), TZ)
    assert caso.executar(dt.date(2026, 3, 10)) == []


def test_lista_apenas_as_presencas_do_dia_pedido() -> None:
    presencas = FakePresencaRepository()
    presencas.registros = {
        (1, dt.date(2026, 3, 10)),
        (2, dt.date(2026, 3, 10)),
        (3, dt.date(2026, 3, 11)),
    }
    caso = ListarPresencasDoDia(presencas, TZ)

    registros = caso.executar(dt.date(2026, 3, 10))

    assert len(registros) == 2
    assert {r.aluno_id for r in registros} == {1, 2}


def test_hoje_usa_o_fuso_da_aplicacao() -> None:
    caso = ListarPresencasDoDia(FakePresencaRepository(), TZ)
    assert caso.hoje() == dt.datetime.now(TZ).date()


def test_horario_e_apresentado_no_fuso_local() -> None:
    """Gravado em UTC, exibido no fuso de quem le."""
    presencas = FakePresencaRepository()
    presencas.registros = {(1, dt.date(2026, 3, 10))}
    caso = ListarPresencasDoDia(presencas, TZ)

    registro = caso.executar(dt.date(2026, 3, 10))[0]

    # O fake grava 08:00 UTC, que e 05:00 em Sao Paulo.
    assert caso.horario_local(registro) == "05:00"
