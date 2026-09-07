"""Fase 2 -- cadastro, sem webcam e sem DeepFace."""

from __future__ import annotations

import pytest

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.domain.entities.aluno import Aluno
from src.domain.errors import (
    AlunoJaCadastrado,
    DadosInvalidos,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
)
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition, FakeImageStorage

FRAME = object()  # a imagem e opaca para o dominio


def montar(
    alunos: FakeAlunoRepository | None = None,
    reconhecimento: FakeFaceRecognition | None = None,
) -> tuple[CadastrarAluno, FakeAlunoRepository, FakeImageStorage]:
    alunos = alunos or FakeAlunoRepository()
    storage = FakeImageStorage()
    caso = CadastrarAluno(alunos, reconhecimento or FakeFaceRecognition(), storage)
    return caso, alunos, storage


def test_cadastra_aluno_valido() -> None:
    caso, alunos, storage = montar()

    aluno = caso.executar("  42 ", "  Maria   Silva ", FRAME)

    assert aluno.matricula == "42"
    assert aluno.nome == "Maria Silva"
    assert aluno.foto_arquivo == "42.jpg"
    assert storage.gravacoes == ["42.jpg"]
    assert len(alunos.alunos) == 1


def test_foto_e_gravada_com_nome_relativo_nao_absoluto() -> None:
    """Problema A11: caminho absoluto no banco tornava a base nao portavel."""
    caso, _, _ = montar()
    aluno = caso.executar("42", "Maria", FRAME)

    assert aluno.foto_arquivo is not None
    assert "/" not in aluno.foto_arquivo
    assert "\\" not in aluno.foto_arquivo


def test_matricula_duplicada_e_recusada() -> None:
    repo = FakeAlunoRepository([Aluno(id=1, matricula="42", nome="Maria")])
    caso, _, storage = montar(alunos=repo)

    with pytest.raises(AlunoJaCadastrado):
        caso.executar("42", "Outro Nome", FRAME)

    assert storage.gravacoes == []


def test_nome_em_branco_e_recusado() -> None:
    caso, _, _ = montar()
    with pytest.raises(DadosInvalidos, match="nome"):
        caso.executar("42", "   ", FRAME)


def test_matricula_em_branco_e_recusada() -> None:
    caso, _, _ = montar()
    with pytest.raises(DadosInvalidos, match="matricula"):
        caso.executar("  ", "Maria", FRAME)


def test_matricula_longa_demais_e_recusada() -> None:
    caso, _, _ = montar()
    with pytest.raises(DadosInvalidos, match="32 caracteres"):
        caso.executar("9" * 33, "Maria", FRAME)


def test_sem_rosto_nao_cadastra_nem_grava_imagem() -> None:
    caso, alunos, storage = montar(
        reconhecimento=FakeFaceRecognition(erro_ao_extrair=NenhumRostoDetectado())
    )

    with pytest.raises(NenhumRostoDetectado):
        caso.executar("42", "Maria", FRAME)

    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_multiplos_rostos_nao_cadastra() -> None:
    caso, alunos, _ = montar(
        reconhecimento=FakeFaceRecognition(erro_ao_extrair=MultiplosRostosDetectados(3))
    )

    with pytest.raises(MultiplosRostosDetectados):
        caso.executar("42", "Maria", FRAME)

    assert alunos.alunos == []


def test_validacao_pode_rodar_antes_de_acender_a_camera() -> None:
    repo = FakeAlunoRepository([Aluno(id=1, matricula="42", nome="Maria")])
    caso, _, _ = montar(alunos=repo)

    with pytest.raises(AlunoJaCadastrado):
        caso.validar_identificacao("42", "Outro")
