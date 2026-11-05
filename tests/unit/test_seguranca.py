"""Fase 6 -- consentimento, exclusao, retencao e privacidade dos logs."""

from __future__ import annotations

import datetime as dt
import logging
from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.application.use_cases.excluir_aluno import ExcluirAluno
from src.application.use_cases.expurgar_presencas import ExpurgarPresencas
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import AlunoNaoEncontrado, ConsentimentoNaoRegistrado
from tests.fakes import (
    FakeAlunoRepository,
    FakeFaceRecognition,
    FakeImageStorage,
    FakePresencaRepository,
)

TZ = ZoneInfo("America/Sao_Paulo")
TURMA_ID = 1
FRAME = object()
NOME_REAL = "Mariana Aparecida de Souza"


# -- consentimento ---------------------------------------------------------


def montar_cadastro() -> tuple[CadastrarAluno, FakeAlunoRepository, FakeImageStorage]:
    alunos = FakeAlunoRepository()
    storage = FakeImageStorage()
    return CadastrarAluno(alunos, FakeFaceRecognition(), storage, TZ), alunos, storage


def test_sem_consentimento_nao_cadastra() -> None:
    caso, alunos, storage = montar_cadastro()

    with pytest.raises(ConsentimentoNaoRegistrado):
        caso.executar("42", "Maria", FRAME, consentiu=False, turma_id=TURMA_ID)

    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_consentimento_e_verificado_antes_de_tudo() -> None:
    """Nem a matricula e consultada sem o "sim" do titular."""
    caso, alunos, _ = montar_cadastro()
    alunos.alunos.append(Aluno(id=1, matricula="42", nome="Ja existe"))

    # Mesmo com matricula duplicada, o erro que sobe e o de consentimento.
    with pytest.raises(ConsentimentoNaoRegistrado):
        caso.executar("42", "Outro", FRAME, consentiu=False, turma_id=TURMA_ID)


def test_consentimento_fica_datado_no_cadastro() -> None:
    caso, _, _ = montar_cadastro()

    aluno = caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert aluno.consentimento_em is not None
    assert aluno.consentimento_em.tzinfo is not None


# -- exclusao --------------------------------------------------------------


def montar_exclusao() -> tuple[ExcluirAluno, FakeAlunoRepository, FakeImageStorage]:
    aluno = Aluno(id=1, matricula="42", nome="Maria", foto_arquivo="42.jpg")
    alunos = FakeAlunoRepository(
        [aluno], {1: FaceEmbedding.de_valores([1.0, 0.0], "Facenet512")}
    )
    storage = FakeImageStorage(existentes={"42.jpg"})
    return ExcluirAluno(alunos, storage), alunos, storage


def test_exclusao_remove_linha_embedding_e_imagem() -> None:
    """Apagar so a linha deixaria dado biometrico no disco."""
    caso, alunos, storage = montar_exclusao()

    caso.executar(caso.localizar("42"))

    assert alunos.alunos == []
    assert alunos.embeddings == {}
    assert storage.remocoes == ["42.jpg"]
    assert not storage.existe("42.jpg")


def test_localizar_aluno_inexistente_falha_com_clareza() -> None:
    caso, _, _ = montar_exclusao()

    with pytest.raises(AlunoNaoEncontrado):
        caso.localizar("999")


def test_exclusao_de_aluno_sem_imagem_nao_quebra() -> None:
    alunos = FakeAlunoRepository([Aluno(id=1, matricula="42", nome="Maria")])
    caso = ExcluirAluno(alunos, FakeImageStorage())

    caso.executar(caso.localizar("42"))

    assert alunos.alunos == []


# -- retencao --------------------------------------------------------------


def test_expurgo_remove_apenas_o_que_excedeu_o_prazo() -> None:
    presencas = FakePresencaRepository()
    hoje = dt.date(2026, 3, 10)
    presencas.registros = {
        (1, dt.date(2020, 1, 1)),  # antiga
        (1, dt.date(2025, 1, 1)),  # antiga
        (1, hoje),  # recente
    }
    caso = ExpurgarPresencas(presencas, TZ, retencao_dias=365)

    removidas = caso.executar(hoje)

    assert removidas == 2
    assert presencas.registros == {(1, hoje)}


def test_retencao_zero_desliga_o_expurgo() -> None:
    presencas = FakePresencaRepository()
    presencas.registros = {(1, dt.date(2000, 1, 1))}
    caso = ExpurgarPresencas(presencas, TZ, retencao_dias=0)

    assert caso.ativo is False
    assert caso.executar() == 0
    assert len(presencas.registros) == 1


def test_limite_e_calculado_a_partir_de_hoje() -> None:
    caso = ExpurgarPresencas(FakePresencaRepository(), TZ, retencao_dias=30)

    assert caso.limite(dt.date(2026, 3, 31)) == dt.date(2026, 3, 1)


# -- privacidade dos logs --------------------------------------------------


def test_log_de_cadastro_nao_contem_o_nome_do_aluno(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log de rotina identifica por id interno, nunca por nome."""
    caso, _, _ = montar_cadastro()

    with caplog.at_level(logging.DEBUG):
        caso.executar("42", NOME_REAL, FRAME, consentiu=True, turma_id=TURMA_ID)

    registrado = caplog.text
    assert NOME_REAL not in registrado
    assert "Mariana" not in registrado


def test_log_de_exclusao_nao_contem_nome_nem_nome_de_arquivo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    aluno = Aluno(id=7, matricula="42", nome=NOME_REAL, foto_arquivo="42.jpg")
    alunos = FakeAlunoRepository([aluno])
    caso = ExcluirAluno(alunos, FakeImageStorage(existentes={"42.jpg"}))

    with caplog.at_level(logging.DEBUG):
        caso.executar(aluno)

    assert NOME_REAL not in caplog.text
    # O nome do arquivo e a matricula do aluno -- tambem e identificador.
    assert "42.jpg" not in caplog.text


def test_log_nao_contem_o_vetor_do_embedding(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Embedding e dado biometrico; nao pode vazar por log."""
    caso, _, _ = montar_cadastro()

    with caplog.at_level(logging.DEBUG):
        aluno = caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert aluno is not None
    assert "0.99" not in caplog.text
    assert "array(" not in caplog.text
