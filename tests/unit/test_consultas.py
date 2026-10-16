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
    assert caso.executar(turma_id=1) == []


def test_lista_vem_ordenada_por_nome() -> None:
    repo = FakeAlunoRepository(
        [
            Aluno(id=1, matricula="1", nome="Bruno"),
            Aluno(id=2, matricula="2", nome="Ana"),
        ]
    )

    nomes = [
        item.aluno.nome for item in ListarAlunos(repo, MODELO).executar(turma_id=1)
    ]

    assert nomes == ["Ana", "Bruno"]


def test_aluno_com_embedding_aparece_como_pronto() -> None:
    repo = FakeAlunoRepository([Aluno(id=1, matricula="1", nome="Ana")], {1: emb()})

    item = ListarAlunos(repo, MODELO).executar(turma_id=1)[0]

    assert item.pronto_para_reconhecimento is True
    assert item.situacao == "pronto"


def test_aluno_sem_embedding_e_sinalizado() -> None:
    """Ele existe no cadastro, mas e invisivel ao reconhecimento."""
    repo = FakeAlunoRepository([Aluno(id=1, matricula="1", nome="Ana")])

    item = ListarAlunos(repo, MODELO).executar(turma_id=1)[0]

    assert item.pronto_para_reconhecimento is False
    assert item.situacao == "sem embedding"


def test_embedding_de_outro_modelo_nao_conta_como_pronto() -> None:
    repo = FakeAlunoRepository(
        [Aluno(id=1, matricula="1", nome="Ana")],
        {1: FaceEmbedding.de_valores([1.0, 0.0], "ArcFace")},
    )

    item = ListarAlunos(repo, MODELO).executar(turma_id=1)[0]

    assert item.pronto_para_reconhecimento is False


def test_lista_de_alunos_nao_exibe_matriculados_em_outra_turma() -> None:
    ana = Aluno(id=1, matricula="1", nome="Ana")
    bruno = Aluno(id=2, matricula="2", nome="Bruno")
    repo = FakeAlunoRepository([ana, bruno], {1: emb(), 2: emb()})
    repo.turmas_ativas.add(2)
    repo.vinculos = {(1, ana.id), (2, bruno.id)}

    itens = ListarAlunos(repo, MODELO).executar(turma_id=1)

    assert [item.aluno for item in itens] == [ana]


# -- presencas do dia ------------------------------------------------------


def test_dia_sem_presencas_vem_vazio() -> None:
    caso = ListarPresencasDoDia(FakePresencaRepository(), TZ)
    assert caso.executar(dt.date(2026, 3, 10), turma_id=1) == []


def test_lista_apenas_as_presencas_do_dia_pedido() -> None:
    presencas = FakePresencaRepository()
    presencas.registros = {
        (1, dt.date(2026, 3, 10)),
        (2, dt.date(2026, 3, 10)),
        (3, dt.date(2026, 3, 11)),
    }
    caso = ListarPresencasDoDia(presencas, TZ)

    registros = caso.executar(dt.date(2026, 3, 10), turma_id=1)

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

    registro = caso.executar(dt.date(2026, 3, 10), turma_id=1)[0]

    # O fake grava 08:00 UTC, que e 05:00 em Sao Paulo.
    assert caso.horario_local(registro) == "05:00"


def test_mesmo_aluno_aparece_em_presencas_das_duas_turmas() -> None:
    dia = dt.date(2026, 3, 10)
    repo = FakePresencaRepository()
    repo.registros = {(1, 42, dia), (2, 42, dia)}
    caso = ListarPresencasDoDia(repo, TZ)

    turma_a = caso.executar(dia, turma_id=1)
    turma_b = caso.executar(dia, turma_id=2)

    assert len(turma_a) == len(turma_b) == 1
    assert turma_a[0].turma_id == 1
    assert turma_b[0].turma_id == 2


def test_presencas_legadas_sao_consultadas_por_caminho_separado() -> None:
    dia = dt.date(2026, 3, 10)
    repo = FakePresencaRepository()
    repo.registros_legado.add((42, dia))
    caso = ListarPresencasDoDia(repo, TZ)

    legado = caso.executar_legado(dia)

    assert len(legado) == 1
    assert legado[0].turma_id is None
