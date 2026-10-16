"""Fase 5 -- reconhecimento por embeddings, sem webcam e sem DeepFace."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from src.application.use_cases.reconhecer_aluno import ReconhecerAluno
from src.domain.entities.aluno import Aluno
from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.errors import (
    IdentificacaoAmbigua,
    ModeloIndisponivel,
    MultiplosRostosDetectados,
    NenhumRostoDetectado,
)
from src.domain.services.matcher import PoliticaAmbiguidade
from tests.fakes import FakeAlunoRepository, FakeFaceRecognition

MODELO = "Facenet512"
TZ = ZoneInfo("America/Sao_Paulo")
LIMIAR = 0.30
TURMA_ID = 1
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
    assert len(caso.carregar_referencias(turma_id=TURMA_ID)) == 0


def test_alunos_de_outro_modelo_ficam_de_fora() -> None:
    caso = montar([ANA], {1: emb([1.0, 0.0], "ArcFace")}, FakeFaceRecognition())
    assert len(caso.carregar_referencias(turma_id=TURMA_ID)) == 0


def test_identifica_o_aluno_mais_proximo() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([1.0, 0.05, 0.0]))
    caso = montar(
        [ANA, BRUNO],
        {1: emb([0.0, 0.0, 1.0]), 2: emb([1.0, 0.05, 0.0])},
        reconhecimento,
    )

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    resultado = caso.identificar(FRAME, refs, turma_id=TURMA_ID)

    assert resultado is not None
    assert resultado.aluno.nome == "Bruno"
    assert resultado.distancia == pytest.approx(0.0, abs=1e-6)


def test_uma_unica_inferencia_por_ciclo_independente_de_n() -> None:
    """Problema A5: o custo por ciclo nao pode crescer com o numero de alunos."""
    reconhecimento = FakeFaceRecognition(embedding=emb([0.0, 1.0, 0.0]))
    muitos = [Aluno(id=i, matricula=str(i), nome=f"Aluno {i}") for i in range(1, 51)]
    embeddings = {i: emb([1.0, 0.0, 0.0]) for i in range(1, 51)}
    caso = montar(muitos, embeddings, reconhecimento)

    referencias = caso.carregar_referencias(turma_id=TURMA_ID)
    assert len(referencias) == 50

    caso.identificar(FRAME, referencias, turma_id=TURMA_ID)

    assert reconhecimento.inferencias == 1


def test_ninguem_abaixo_do_limiar_devolve_none() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([0.0, 1.0, 0.0]))
    caso = montar([ANA], {1: emb([1.0, 0.0, 0.0])}, reconhecimento)

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    assert caso.identificar(FRAME, refs, turma_id=TURMA_ID) is None


def test_referencia_vazia_nao_aciona_o_modelo() -> None:
    reconhecimento = FakeFaceRecognition()
    caso = montar([], {}, reconhecimento)

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    assert caso.identificar(FRAME, refs, turma_id=TURMA_ID) is None
    assert reconhecimento.inferencias == 0


def test_frame_sem_rosto_devolve_none() -> None:
    reconhecimento = FakeFaceRecognition(erro_ao_gerar=NenhumRostoDetectado())
    caso = montar([ANA], {1: emb([1.0, 0.0])}, reconhecimento)

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    assert caso.identificar(FRAME, refs, turma_id=TURMA_ID) is None


def test_frame_com_varias_pessoas_devolve_none() -> None:
    """Ambiguidade, nao falha: nao ha identidade unica a registrar."""
    reconhecimento = FakeFaceRecognition(erro_ao_gerar=MultiplosRostosDetectados(3))
    caso = montar([ANA], {1: emb([1.0, 0.0])}, reconhecimento)

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    assert caso.identificar(FRAME, refs, turma_id=TURMA_ID) is None


def test_falha_de_modelo_nao_se_disfarca_de_nao_reconhecido() -> None:
    """Problema A6: erro de infraestrutura tem de doer, nao virar None."""
    reconhecimento = FakeFaceRecognition(
        erro_ao_gerar=ModeloIndisponivel("pesos ausentes")
    )
    caso = montar([ANA], {1: emb([1.0, 0.0])}, reconhecimento)

    with pytest.raises(ModeloIndisponivel):
        refs = caso.carregar_referencias(turma_id=TURMA_ID)
        caso.identificar(FRAME, refs, turma_id=TURMA_ID)


def test_recarregar_enxerga_cadastros_novos() -> None:
    """Problema A15: o prototipo so via a lista materializada na entrada."""
    repo = FakeAlunoRepository([ANA], {1: emb([1.0, 0.0])})
    caso = ReconhecerAluno(repo, FakeFaceRecognition(), modelo=MODELO, limiar=LIMIAR)
    assert len(caso.carregar_referencias(turma_id=TURMA_ID)) == 1

    repo.cadastrar("2", "Bruno", None, emb([0.0, 1.0]), dt.datetime.now(TZ))

    assert len(caso.carregar_referencias(turma_id=TURMA_ID)) == 2


def test_trocar_turma_filtra_galeria_e_recusa_matriz_anterior() -> None:
    repo = FakeAlunoRepository(
        [ANA, BRUNO],
        {1: emb([1.0, 0.0]), 2: emb([0.0, 1.0])},
    )
    repo.turmas_ativas.add(2)
    repo.vinculos = {(1, ANA.id), (2, BRUNO.id)}
    reconhecimento = FakeFaceRecognition(embedding=emb([0.0, 1.0]))
    caso = ReconhecerAluno(repo, reconhecimento, modelo=MODELO, limiar=LIMIAR)

    refs_a = caso.carregar_referencias(turma_id=1)
    refs_b = caso.carregar_referencias(turma_id=2)

    assert len(refs_a) == 1
    assert len(refs_b) == 1
    with pytest.raises(RuntimeError, match="contexto da turma"):
        caso.identificar(FRAME, refs_a, turma_id=2)
    resultado = caso.identificar(FRAME, refs_b, turma_id=2)
    assert resultado is not None and resultado.aluno == BRUNO


def test_politica_de_ambiguidade_propaga_recusa_apos_uma_inferencia() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([1.0, 0.0]))
    repo = FakeAlunoRepository([ANA, BRUNO], {1: emb([1.0, 0.0]), 2: emb([1.0, 0.0])})
    caso = ReconhecerAluno(
        repo,
        reconhecimento,
        modelo=MODELO,
        limiar=LIMIAR,
        ambiguidade=PoliticaAmbiguidade(0.0),
    )

    with pytest.raises(IdentificacaoAmbigua):
        refs = caso.carregar_referencias(turma_id=TURMA_ID)
        caso.identificar(FRAME, refs, turma_id=TURMA_ID)

    assert reconhecimento.inferencias == 1


def test_politica_ativa_preserva_identidade_unica_e_distante() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([1.0, 0.0]))
    repo = FakeAlunoRepository([ANA, BRUNO], {1: emb([1.0, 0.0]), 2: emb([0.0, 1.0])})
    caso = ReconhecerAluno(
        repo,
        reconhecimento,
        modelo=MODELO,
        limiar=LIMIAR,
        ambiguidade=PoliticaAmbiguidade(0.5),
    )

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    resultado = caso.identificar(FRAME, refs, turma_id=TURMA_ID)

    assert resultado is not None and resultado.aluno == ANA
    assert reconhecimento.inferencias == 1


def test_politica_ativa_mantem_none_quando_ninguem_atende_ao_limiar() -> None:
    reconhecimento = FakeFaceRecognition(embedding=emb([0.0, 1.0]))
    caso = ReconhecerAluno(
        FakeAlunoRepository([ANA], {1: emb([1.0, 0.0])}),
        reconhecimento,
        modelo=MODELO,
        limiar=LIMIAR,
        ambiguidade=PoliticaAmbiguidade(0.1),
    )

    refs = caso.carregar_referencias(turma_id=TURMA_ID)
    assert caso.identificar(FRAME, refs, turma_id=TURMA_ID) is None
    assert reconhecimento.inferencias == 1
