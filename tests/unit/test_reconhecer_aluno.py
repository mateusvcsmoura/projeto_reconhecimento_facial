"""Fase 2 -- reconhecimento, sem webcam e sem DeepFace."""

from __future__ import annotations

import pytest

from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.domain.entities.aluno import Aluno
from src.domain.errors import ModeloIndisponivel, NenhumRostoDetectado
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition, FakeImageStorage

FRAME = object()

ANA = Aluno(id=1, matricula="1", nome="Ana", foto_arquivo="1.jpg")
BRUNO = Aluno(id=2, matricula="2", nome="Bruno", foto_arquivo="2.jpg")


def test_candidatos_ignoram_aluno_sem_foto_disponivel() -> None:
    alunos = FakeAlunoRepository(
        [
            ANA,
            Aluno(id=2, matricula="2", nome="Sem Arquivo", foto_arquivo="2.jpg"),
            Aluno(id=3, matricula="3", nome="Sem Campo", foto_arquivo=None),
        ]
    )
    caso = ReconhecerAluno(
        alunos, FakeFaceRecognition(), FakeImageStorage(existentes={"1.jpg"})
    )

    assert [a.id for a in caso.candidatos()] == [1]


def test_sem_nenhum_candidato_a_lista_vem_vazia() -> None:
    caso = ReconhecerAluno(
        FakeAlunoRepository(), FakeFaceRecognition(), FakeImageStorage()
    )
    assert caso.candidatos() == []


def test_identifica_o_aluno_que_casa() -> None:
    alunos = FakeAlunoRepository([ANA, BRUNO])
    storage = FakeImageStorage(existentes={"1.jpg", "2.jpg"})
    caso = ReconhecerAluno(alunos, FakeFaceRecognition(casa_com="2.jpg"), storage)

    encontrado = caso.identificar(FRAME, caso.candidatos())

    assert encontrado is not None
    assert encontrado.id == 2


def test_nenhum_candidato_casa_devolve_none() -> None:
    alunos = FakeAlunoRepository([ANA])
    caso = ReconhecerAluno(
        alunos, FakeFaceRecognition(casa_com=None), FakeImageStorage({"1.jpg"})
    )

    assert caso.identificar(FRAME, caso.candidatos()) is None


def test_lista_de_candidatos_vazia_devolve_none() -> None:
    caso = ReconhecerAluno(
        FakeAlunoRepository(), FakeFaceRecognition(), FakeImageStorage()
    )
    assert caso.identificar(FRAME, []) is None


def test_frame_sem_rosto_para_de_comparar() -> None:
    """Sem rosto no frame, varrer os demais candidatos e desperdicio."""
    alunos = FakeAlunoRepository([ANA, BRUNO])
    reconhecimento = FakeFaceRecognition(erro_ao_comparar=NenhumRostoDetectado())
    caso = ReconhecerAluno(
        alunos, reconhecimento, FakeImageStorage({"1.jpg", "2.jpg"})
    )

    assert caso.identificar(FRAME, caso.candidatos()) is None
    assert len(reconhecimento.comparacoes) == 1


def test_falha_de_modelo_nao_se_disfarca_de_nao_reconhecido() -> None:
    """Problema A6: erro de infraestrutura tem de doer, nao virar None."""
    alunos = FakeAlunoRepository([ANA])
    caso = ReconhecerAluno(
        alunos,
        FakeFaceRecognition(erro_ao_comparar=ModeloIndisponivel("pesos ausentes")),
        FakeImageStorage({"1.jpg"}),
    )

    with pytest.raises(ModeloIndisponivel):
        caso.identificar(FRAME, caso.candidatos())
