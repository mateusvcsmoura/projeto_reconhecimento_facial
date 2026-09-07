"""Fase 5 -- reconhecimento por embeddings, sem webcam e sem DeepFace."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
)
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition

MODELO = "Facenet512"
TZ = ZoneInfo("America/Sao_Paulo")
LIMIAR = 0.30
FRAME = object()

ANA = Aluno(id=1, matricula="1", nome="Ana")
BRUNO = Aluno(id=2, matricula="2", nome="Bruno")


def emb(valores: list[float], modelo: str = MODELO) -> FaceEmbedding:
    return FaceEmbedding.de_valores(valores, modelo)


def montar(
    alunos: list[Aluno],
    embeddings: dict[int, FaceEmbedding],
    reconhecimento: FakeFaceRecognition,
) -> ReconhecerAluno:
    repo = FakeAlunoRepository(alunos, embeddings)
    return ReconhecerAluno(repo, reconhecimento, modelo=MODELO, limiar=LIMIAR)


def test_sem_embeddings_a_referencia_vem_vazia() -> None:
    caso = montar([ANA], {}, FakeFaceRecognition())
    assert len(caso.carregar_referencias()) == 0


def test_alunos_de_outro_modelo_ficam_de_fora() -> None:
    caso = montar([ANA], {1: emb([1.0, 0.0], "ArcFace")}, FakeFaceRecognition())
    assert len(caso.carregar_referencias()) == 0


def test_identifica_o_aluno_mais_proximo() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([1.0, 0.05, 0.0]))
    caso = montar(
        [ANA, BRUNO],
        {1: emb([0.0, 0.0, 1.0]), 2: emb([1.0, 0.05, 0.0])},
        reconhecimento,
    )

    resultado = caso.identificar(FRAME, caso.carregar_referencias())

    assert resultado is not None
    assert resultado.aluno.nome == "Bruno"
    assert resultado.distancia == pytest.approx(0.0, abs=1e-6)


def test_uma_unica_inferencia_por_ciclo_independente_de_n() -> None:
    """Problema A5: o custo por ciclo nao pode crescer com o numero de alunos."""
    reconhecimento = FakeFaceRecognition(embedding=emb([0.0, 1.0, 0.0]))
    muitos = [Aluno(id=i, matricula=str(i), nome=f"Aluno {i}") for i in range(1, 51)]
    embeddings = {i: emb([1.0, 0.0, 0.0]) for i in range(1, 51)}
    caso = montar(muitos, embeddings, reconhecimento)

    referencias = caso.carregar_referencias()
    assert len(referencias) == 50

    caso.identificar(FRAME, referencias)

    assert reconhecimento.inferencias == 1


def test_ninguem_abaixo_do_limiar_devolve_none() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([0.0, 1.0, 0.0]))
    caso = montar([ANA], {1: emb([1.0, 0.0, 0.0])}, reconhecimento)

    assert caso.identificar(FRAME, caso.carregar_referencias()) is None


def test_referencia_vazia_nao_aciona_o_modelo() -> None:
    reconhecimento = FakeFaceRecognition()
    caso = montar([], {}, reconhecimento)

    assert caso.identificar(FRAME, caso.carregar_referencias()) is None
    assert reconhecimento.inferencias == 0


def test_frame_sem_rosto_devolve_none() -> None:
    reconhecimento = FakeFaceRecognition(erro_ao_gerar=NenhumRostoDetectado())
    caso = montar([ANA], {1: emb([1.0, 0.0])}, reconhecimento)

    assert caso.identificar(FRAME, caso.carregar_referencias()) is None


def test_frame_com_varias_pessoas_devolve_none() -> None:
    """Ambiguidade, nao falha: nao ha identidade unica a registrar."""
    reconhecimento = FakeFaceRecognition(erro_ao_gerar=MultiplosRostosDetectados(3))
    caso = montar([ANA], {1: emb([1.0, 0.0])}, reconhecimento)

    assert caso.identificar(FRAME, caso.carregar_referencias()) is None


def test_falha_de_modelo_nao_se_disfarca_de_nao_reconhecido() -> None:
    """Problema A6: erro de infraestrutura tem de doer, nao virar None."""
    reconhecimento = FakeFaceRecognition(
        erro_ao_gerar=ModeloIndisponivel("pesos ausentes")
    )
    caso = montar([ANA], {1: emb([1.0, 0.0])}, reconhecimento)

    with pytest.raises(ModeloIndisponivel):
        caso.identificar(FRAME, caso.carregar_referencias())


def test_recarregar_enxerga_cadastros_novos() -> None:
    """Problema A15: o prototipo so via a lista materializada na entrada."""
    repo = FakeAlunoRepository([ANA], {1: emb([1.0, 0.0])})
    caso = ReconhecerAluno(
        repo, FakeFaceRecognition(), modelo=MODELO, limiar=LIMIAR
    )
    assert len(caso.carregar_referencias()) == 1

    repo.cadastrar("2", "Bruno", None, emb([0.0, 1.0]), dt.datetime.now(TZ))

    assert len(caso.carregar_referencias()) == 2
