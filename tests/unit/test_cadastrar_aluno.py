"""Fase 2 -- cadastro, sem webcam e sem DeepFace."""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.domain.entities.aluno import Aluno
from src.domain.errors import (
    AlunoJaCadastrado,
    ConsentimentoNaoRegistrado,
    DadosInvalidos,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    RostoSemNitidez,
    TurmaNaoEncontrada,
)
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition, FakeImageStorage

TZ = ZoneInfo("America/Sao_Paulo")
TURMA_ID = 1

FRAME = object()  # a imagem e opaca para o dominio


def montar(
    alunos: FakeAlunoRepository | None = None,
    reconhecimento: FakeFaceRecognition | None = None,
) -> tuple[CadastrarAluno, FakeAlunoRepository, FakeImageStorage]:
    alunos = alunos or FakeAlunoRepository()
    storage = FakeImageStorage()
    caso = CadastrarAluno(alunos, reconhecimento or FakeFaceRecognition(), storage, TZ)
    return caso, alunos, storage


def test_cadastra_aluno_valido() -> None:
    caso, alunos, storage = montar()

    aluno = caso.executar(
        "  42 ", "  Maria   Silva ", FRAME, consentiu=True, turma_id=TURMA_ID
    )

    assert aluno.matricula == "42"
    assert aluno.nome == "Maria Silva"
    assert aluno.foto_arquivo == storage.gravacoes[0]
    assert aluno.foto_arquivo != "42.jpg"
    assert len(alunos.alunos) == 1


def test_foto_e_gravada_com_nome_relativo_nao_absoluto() -> None:
    """Problema A11: caminho absoluto no banco tornava a base nao portavel."""
    caso, _, _ = montar()
    aluno = caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert aluno.foto_arquivo is not None
    assert "/" not in aluno.foto_arquivo
    assert "\\" not in aluno.foto_arquivo


def test_matricula_duplicada_e_recusada() -> None:
    repo = FakeAlunoRepository([Aluno(id=1, matricula="42", nome="Maria")])
    caso, _, storage = montar(alunos=repo)

    with pytest.raises(AlunoJaCadastrado):
        caso.executar("42", "Outro Nome", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert storage.gravacoes == []


def test_nome_em_branco_e_recusado() -> None:
    caso, _, _ = montar()
    with pytest.raises(DadosInvalidos, match="nome"):
        caso.executar("42", "   ", FRAME, consentiu=True, turma_id=TURMA_ID)


def test_matricula_em_branco_e_recusada() -> None:
    caso, _, _ = montar()
    with pytest.raises(DadosInvalidos, match="matricula"):
        caso.executar("  ", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)


def test_matricula_longa_demais_e_recusada() -> None:
    caso, _, _ = montar()
    with pytest.raises(DadosInvalidos, match="32 caracteres"):
        caso.executar("9" * 33, "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)


def test_sem_rosto_nao_cadastra_nem_grava_imagem() -> None:
    caso, alunos, storage = montar(
        reconhecimento=FakeFaceRecognition(erro_ao_extrair=NenhumRostoDetectado())
    )

    with pytest.raises(NenhumRostoDetectado):
        caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_multiplos_rostos_nao_cadastra() -> None:
    caso, alunos, _ = montar(
        reconhecimento=FakeFaceRecognition(erro_ao_extrair=MultiplosRostosDetectados(3))
    )

    with pytest.raises(MultiplosRostosDetectados):
        caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert alunos.alunos == []


def test_validacao_pode_rodar_antes_de_acender_a_camera() -> None:
    repo = FakeAlunoRepository([Aluno(id=1, matricula="42", nome="Maria")])
    caso, _, _ = montar(alunos=repo)

    with pytest.raises(AlunoJaCadastrado):
        caso.validar_identificacao("42", "Outro", turma_id=TURMA_ID)


def test_cadastro_persiste_a_imagem_e_embedding_da_preparacao_unica() -> None:
    embedding = FakeFaceRecognition().gerar_embedding(FRAME)
    imagem_preparada = object()
    reconhecimento = FakeFaceRecognition(face=imagem_preparada, embedding=embedding)
    caso, alunos, storage = montar(reconhecimento=reconhecimento)

    aluno = caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert reconhecimento.preparacoes == 1
    assert storage.imagens_salvas[0][1] is imagem_preparada
    assert storage.imagens_salvas[0][0] != "42.jpg"
    assert alunos.embeddings[aluno.id] is embedding


def test_recusa_de_qualidade_nao_grava_imagem_nem_cadastra_aluno() -> None:
    reconhecimento = FakeFaceRecognition(erro_ao_preparar=RostoSemNitidez())
    caso, alunos, storage = montar(reconhecimento=reconhecimento)

    with pytest.raises(RostoSemNitidez):
        caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=TURMA_ID)

    assert reconhecimento.preparacoes == 1
    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_consentimento_negado_nao_prepara_face() -> None:
    reconhecimento = FakeFaceRecognition(erro_ao_preparar=RostoSemNitidez())
    caso, alunos, storage = montar(reconhecimento=reconhecimento)

    with pytest.raises(ConsentimentoNaoRegistrado):
        caso.executar("42", "Maria", FRAME, consentiu=False, turma_id=TURMA_ID)

    assert reconhecimento.preparacoes == 0
    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_validar_captura_nao_calcula_embedding_nem_persiste() -> None:
    reconhecimento = FakeFaceRecognition()
    caso, alunos, storage = montar(reconhecimento=reconhecimento)

    caso.validar_captura(FRAME)

    assert reconhecimento.extracoes == 1
    assert reconhecimento.inferencias == 0
    assert reconhecimento.preparacoes == 0
    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_preparar_captura_nao_persiste_e_concluir_reusa_preparacao() -> None:
    reconhecimento = FakeFaceRecognition()
    caso, alunos, storage = montar(reconhecimento=reconhecimento)

    preparada = caso.preparar_captura(FRAME)

    assert reconhecimento.preparacoes == 1
    assert reconhecimento.inferencias == 1
    assert storage.gravacoes == []
    assert alunos.alunos == []

    aluno = caso.concluir_cadastro(
        "42", "Maria", preparada, consentiu=True, turma_id=TURMA_ID
    )

    assert aluno.matricula == "42"
    assert reconhecimento.preparacoes == 1
    assert storage.imagens_salvas[0][1] is preparada.imagem
    assert storage.imagens_salvas[0][0] != "42.jpg"
    assert alunos.embeddings[aluno.id] is preparada.embedding


def test_concluir_cadastro_revalida_identificacao_antes_de_persistir() -> None:
    existente = Aluno(id=1, matricula="42", nome="Maria")
    repo = FakeAlunoRepository([existente])
    caso, alunos, storage = montar(alunos=repo)
    preparada = caso.preparar_captura(FRAME)

    with pytest.raises(AlunoJaCadastrado):
        caso.concluir_cadastro(
            "42", "Outro nome", preparada, consentiu=True, turma_id=TURMA_ID
        )

    assert alunos.alunos == [existente]
    assert storage.gravacoes == []


def test_concluir_cadastro_exige_consentimento_antes_de_persistir() -> None:
    caso, alunos, storage = montar()
    preparada = caso.preparar_captura(FRAME)

    with pytest.raises(ConsentimentoNaoRegistrado):
        caso.concluir_cadastro(
            "42", "Maria", preparada, consentiu=False, turma_id=TURMA_ID
        )

    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_turma_inexistente_e_recusada_antes_de_abrir_fluxo_de_face() -> None:
    reconhecimento = FakeFaceRecognition()
    caso, alunos, storage = montar(reconhecimento=reconhecimento)

    with pytest.raises(TurmaNaoEncontrada):
        caso.executar("42", "Maria", FRAME, consentiu=True, turma_id=8)

    assert reconhecimento.preparacoes == 0
    assert alunos.alunos == []
    assert storage.gravacoes == []


def test_falha_sql_remove_somente_arquivo_da_tentativa() -> None:
    class RepositorioFalho(FakeAlunoRepository):
        def cadastrar_em_turma(self, *args: object, **kwargs: object) -> Aluno:
            raise RuntimeError("falha no banco")

    repo = RepositorioFalho()
    storage = FakeImageStorage(existentes={"42.jpg"})
    caso = CadastrarAluno(repo, FakeFaceRecognition(), storage, TZ)
    preparada = caso.preparar_captura(FRAME)

    with pytest.raises(RuntimeError, match="falha no banco"):
        caso.concluir_cadastro(
            "42", "Maria", preparada, consentiu=True, turma_id=TURMA_ID
        )

    assert len(storage.gravacoes) == 1
    assert storage.remocoes == storage.gravacoes
    assert storage.existe("42.jpg")
