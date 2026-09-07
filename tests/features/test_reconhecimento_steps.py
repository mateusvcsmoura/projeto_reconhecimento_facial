"""Passos do cenario de reconhecimento (reconhecimento.feature)."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import ModeloIndisponivel, NenhumRostoDetectado
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition

scenarios("reconhecimento.feature")

MODELO = "Facenet512"
LIMIAR = 0.30


def emb(valores: list[float]) -> FaceEmbedding:
    return FaceEmbedding.de_valores(valores, MODELO)


@pytest.fixture
def contexto() -> dict[str, Any]:
    return {
        "alunos": FakeAlunoRepository(),
        "reconhecimento": FakeFaceRecognition(),
        "resultado": None,
        "erro": None,
    }


def _caso(contexto: dict[str, Any]) -> ReconhecerAluno:
    return ReconhecerAluno(
        contexto["alunos"], contexto["reconhecimento"], modelo=MODELO, limiar=LIMIAR
    )


# -- Dado ------------------------------------------------------------------


@given("que o sistema esta operacional")
def sistema_operacional(contexto: dict[str, Any]) -> None:
    assert contexto["alunos"] is not None


@given(parsers.parse('que o aluno "{nome}" esta cadastrado com um embedding conhecido'))
def aluno_com_embedding(contexto: dict[str, Any], nome: str) -> None:
    aluno = Aluno(id=1, matricula="1001", nome=nome)
    contexto["alunos"].alunos.append(aluno)
    contexto["alunos"].embeddings[1] = emb([1.0, 0.0, 0.0])


@given("que existem dois alunos com embeddings parecidos")
def dois_alunos_parecidos(contexto: dict[str, Any]) -> None:
    contexto["alunos"].alunos.extend(
        [
            Aluno(id=1, matricula="1", nome="Primeiro"),
            Aluno(id=2, matricula="2", nome="Segundo"),
        ]
    )
    contexto["alunos"].embeddings[1] = emb([1.0, 0.00, 0.0])
    contexto["alunos"].embeddings[2] = emb([1.0, 0.20, 0.0])


@given("que nenhum aluno possui embedding cadastrado")
def sem_embeddings(contexto: dict[str, Any]) -> None:
    contexto["alunos"].alunos.append(Aluno(id=1, matricula="1", nome="Sem vetor"))


@given(parsers.parse("que existem {quantidade:d} alunos cadastrados com embedding"))
def muitos_alunos(contexto: dict[str, Any], quantidade: int) -> None:
    for i in range(1, quantidade + 1):
        contexto["alunos"].alunos.append(
            Aluno(id=i, matricula=str(i), nome=f"Aluno {i}")
        )
        contexto["alunos"].embeddings[i] = emb([1.0, 0.0, 0.0])


@given("que o modelo de reconhecimento esta indisponivel")
def modelo_indisponivel(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_gerar = ModeloIndisponivel("pesos ausentes")


# -- Quando ----------------------------------------------------------------


def _identificar(contexto: dict[str, Any]) -> None:
    caso = _caso(contexto)
    referencias = caso.carregar_referencias()
    try:
        contexto["resultado"] = caso.identificar(object(), referencias)
    except Exception as erro:
        contexto["erro"] = erro


@when(parsers.parse('a camera apresentar o rosto de "{nome}"'))
def apresentar_rosto_de(contexto: dict[str, Any], nome: str) -> None:
    contexto["reconhecimento"].embedding = emb([1.0, 0.0, 0.0])
    _identificar(contexto)


@when("a camera apresentar um rosto desconhecido")
def apresentar_desconhecido(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].embedding = emb([0.0, 0.0, 1.0])
    _identificar(contexto)


@when("a camera apresentar o rosto mais parecido com o segundo aluno")
def apresentar_parecido_com_segundo(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].embedding = emb([1.0, 0.20, 0.0])
    _identificar(contexto)


@when("a camera apresentar um rosto qualquer")
def apresentar_qualquer(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].embedding = emb([1.0, 0.0, 0.0])
    _identificar(contexto)


@when("a camera nao apresentar nenhum rosto")
def apresentar_sem_rosto(contexto: dict[str, Any]) -> None:
    contexto["reconhecimento"].erro_ao_gerar = NenhumRostoDetectado()
    _identificar(contexto)


# -- Entao -----------------------------------------------------------------


@then(parsers.parse('o sistema deve identificar "{nome}"'))
def identificou(contexto: dict[str, Any], nome: str) -> None:
    assert contexto["erro"] is None, contexto["erro"]
    assert contexto["resultado"] is not None
    assert contexto["resultado"].aluno.nome == nome


@then("o sistema nao deve identificar ninguem")
def nao_identificou(contexto: dict[str, Any]) -> None:
    assert contexto["erro"] is None, contexto["erro"]
    assert contexto["resultado"] is None


@then("o sistema deve identificar o segundo aluno")
def identificou_o_segundo(contexto: dict[str, Any]) -> None:
    assert contexto["resultado"] is not None
    assert contexto["resultado"].aluno.id == 2


@then("nao o primeiro que estava dentro do limiar")
def nao_o_primeiro(contexto: dict[str, Any]) -> None:
    # O primeiro tambem passaria no limiar; perde por estar mais longe.
    from src.domain.services.matcher import MatrizDeReferencia

    apenas_o_primeiro = MatrizDeReferencia.de_embeddings(
        [(1, contexto["alunos"].embeddings[1])]
    )
    assert (
        apenas_o_primeiro.melhor_candidato(emb([1.0, 0.20, 0.0]), LIMIAR) is not None
    )
    assert contexto["resultado"].aluno.id != 1


@then(parsers.parse('o reconhecimento deve falhar com "{erro}"'))
def reconhecimento_falha(contexto: dict[str, Any], erro: str) -> None:
    assert contexto["erro"] is not None, "o reconhecimento deveria ter falhado"
    assert type(contexto["erro"]).__name__ == erro


@then("a falha nao deve ser confundida com rosto nao reconhecido")
def falha_nao_e_none(contexto: dict[str, Any]) -> None:
    assert contexto["resultado"] is None
    assert contexto["erro"] is not None


@then("o modelo nao deve ser acionado")
def modelo_nao_acionado(contexto: dict[str, Any]) -> None:
    assert contexto["reconhecimento"].inferencias == 0


@then("o modelo deve ser acionado exatamente uma vez")
def modelo_acionado_uma_vez(contexto: dict[str, Any]) -> None:
    """Problema A5: o custo por ciclo nao pode crescer com N."""
    assert contexto["reconhecimento"].inferencias == 1
