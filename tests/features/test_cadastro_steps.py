"""Passos do cenario de cadastro (tests/features/cadastro.feature)."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.application.use_cases.cadastrar_aluno import CadastrarAluno
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
    PossivelFraude,
)
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition, FakeImageStorage

scenarios("cadastro.feature")

TZ = ZoneInfo("America/Sao_Paulo")
MODELO = "Facenet512"


@pytest.fixture
def contexto() -> dict[str, Any]:
    return {
        "alunos": FakeAlunoRepository(),
        "storage": FakeImageStorage(),
        "reconhecimento": FakeFaceRecognition(
            embedding=FaceEmbedding.de_valores([1.0, 0.0, 0.0], MODELO)
        ),
        "turma_id": None,
        "erro": None,
        "aluno": None,
    }


def _caso(contexto: dict[str, Any]) -> CadastrarAluno:
    return CadastrarAluno(
        contexto["alunos"], contexto["reconhecimento"], contexto["storage"], TZ
    )


# -- Dado ------------------------------------------------------------------


@given("que o sistema esta operacional")
def sistema_operacional(contexto: dict[str, Any]) -> None:
    assert contexto["alunos"] is not None


@given("que uma turma ativa foi selecionada")
def turma_ativa_selecionada(contexto: dict[str, Any]) -> None:
    contexto["turma_id"] = 1
    contexto["alunos"].validar_turma_ativa(contexto["turma_id"])


@given("que a camera entrega o rosto de uma pessoa real")
def rosto_real(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_extrair = None


@given("que a camera nao entrega nenhum rosto")
def sem_rosto(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_extrair = NenhumRostoDetectado()


@given("que a camera entrega mais de um rosto")
def varios_rostos(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_extrair = MultiplosRostosDetectados(2)


@given("que a camera entrega uma foto impressa")
def foto_impressa(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_extrair = PossivelFraude(0.08)


@given("que o modelo de reconhecimento esta indisponivel")
def modelo_indisponivel(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_extrair = ModeloIndisponivel("pesos ausentes")


@given(parsers.parse('que ja existe um aluno com a matricula "{matricula}"'))
def aluno_existente(contexto: dict[str, Any], matricula: str) -> None:
    contexto["alunos"].alunos.append(
        Aluno(id=1, matricula=matricula, nome="Ja Cadastrado")
    )


# -- Quando ----------------------------------------------------------------


@when(parsers.parse('eu cadastrar o aluno "{nome}" com a matricula "{matricula}"'))
def cadastrar(contexto: dict[str, Any], nome: str, matricula: str) -> None:
    try:
        contexto["aluno"] = _caso(contexto).executar(
            matricula,
            nome,
            object(),
            consentiu=True,
            turma_id=contexto["turma_id"],
        )
    except Exception as erro:  # o cenario diz qual erro esperar
        contexto["erro"] = erro


@when(
    parsers.parse(
        'eu cadastrar o aluno "{nome}" com a matricula "{matricula}" sem consentimento'
    )
)
def cadastrar_sem_consentimento(
    contexto: dict[str, Any], nome: str, matricula: str
) -> None:
    try:
        contexto["aluno"] = _caso(contexto).executar(
            matricula,
            nome,
            object(),
            consentiu=False,
            turma_id=contexto["turma_id"],
        )
    except Exception as erro:
        contexto["erro"] = erro


# -- Entao -----------------------------------------------------------------


@then("o aluno deve estar cadastrado")
def aluno_cadastrado(contexto: dict[str, Any]) -> None:
    assert contexto["erro"] is None, contexto["erro"]
    assert contexto["aluno"] is not None
    assert len(contexto["alunos"].alunos) == 1


@then("o embedding facial deve ter sido gravado")
def embedding_gravado(contexto: dict[str, Any]) -> None:
    assert contexto["alunos"].embeddings


@then("a data do consentimento deve estar registrada")
def consentimento_registrado(contexto: dict[str, Any]) -> None:
    assert contexto["aluno"].consentimento_em is not None


@then(parsers.parse('o cadastro deve falhar com "{erro}"'))
def cadastro_falha(contexto: dict[str, Any], erro: str) -> None:
    assert contexto["erro"] is not None, "o cadastro deveria ter falhado"
    assert type(contexto["erro"]).__name__ == erro


@then("nenhuma imagem deve ter sido gravada")
def sem_imagem(contexto: dict[str, Any]) -> None:
    assert contexto["storage"].gravacoes == []
