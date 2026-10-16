"""Cenarios PostgreSQL da tarefa 008; exigem banco descartavel identificado."""

from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Engine

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import AlunoJaCadastrado, TurmaInativa, VinculoInativo
from src.infrastructure.repositories.postgres_aluno_repository import (
    PostgresAlunoRepository,
)
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)
from src.infrastructure.repositories.postgres_turma_repository import (
    PostgresTurmaRepository,
)

TZ = ZoneInfo("America/Sao_Paulo")
AGORA = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
MODELO = "Facenet512"


def criar_turma(repo: PostgresTurmaRepository, materia: str) -> int:
    turma = repo.criar(Turma.nova(materia, Periodo.DIURNO), AGORA)
    assert turma.id is not None
    return turma.id


@pytest.fixture
def repositorios(
    banco_limpo: Engine,
) -> tuple[
    PostgresTurmaRepository, PostgresAlunoRepository, PostgresPresencaRepository
]:
    return (
        PostgresTurmaRepository(banco_limpo),
        PostgresAlunoRepository(banco_limpo),
        PostgresPresencaRepository(banco_limpo),
    )


def test_matricula_global_e_vinculo_n_n_sem_recapturar(
    repositorios: tuple[
        PostgresTurmaRepository, PostgresAlunoRepository, PostgresPresencaRepository
    ],
) -> None:
    turmas, alunos, _presencas = repositorios
    turma_a = criar_turma(turmas, "IA")
    turma_b = criar_turma(turmas, "Banco de Dados")
    original = alunos.cadastrar_em_turma(
        turma_a,
        "100",
        "Ana",
        "ana.jpg",
        FaceEmbedding.de_valores([1.0, 0.0], MODELO),
        AGORA,
    )

    vinculado, criado = turmas.vincular_matricula(turma_b, "100", AGORA)
    repetido, criado_novamente = turmas.vincular_matricula(turma_b, "100", AGORA)

    assert criado is True
    assert criado_novamente is False
    assert vinculado.id == repetido.id == original.id
    assert vinculado.foto_arquivo == original.foto_arquivo
    with pytest.raises(AlunoJaCadastrado):
        alunos.cadastrar_em_turma(turma_b, "100", "Outra Ana", None, None, AGORA)


def test_presencas_sao_unicas_por_turma_e_aluno_no_mesmo_dia(
    repositorios: tuple[
        PostgresTurmaRepository, PostgresAlunoRepository, PostgresPresencaRepository
    ],
) -> None:
    turmas, alunos, presencas = repositorios
    turma_a = criar_turma(turmas, "IA")
    turma_b = criar_turma(turmas, "IA")
    aluno = alunos.cadastrar_em_turma(turma_a, "101", "Bruno", None, None, AGORA)
    turmas.vincular_matricula(turma_b, "101", AGORA)

    assert presencas.registrar_se_ausente(
        aluno.id, AGORA.date(), AGORA, turma_id=turma_a
    )
    assert presencas.registrar_se_ausente(
        aluno.id, AGORA.date(), AGORA, turma_id=turma_b
    )
    assert not presencas.registrar_se_ausente(
        aluno.id, AGORA.date(), AGORA, turma_id=turma_a
    )


def test_desvinculo_preserva_historico_e_bloqueia_novo_registro(
    repositorios: tuple[
        PostgresTurmaRepository, PostgresAlunoRepository, PostgresPresencaRepository
    ],
) -> None:
    turmas, alunos, presencas = repositorios
    turma_id = criar_turma(turmas, "Sistemas Inteligentes")
    aluno = alunos.cadastrar_em_turma(turma_id, "102", "Carla", None, None, AGORA)
    presencas.registrar_se_ausente(aluno.id, AGORA.date(), AGORA, turma_id=turma_id)

    turmas.desvincular_matricula(turma_id, aluno.matricula, AGORA)

    with pytest.raises(VinculoInativo):
        presencas.registrar_se_ausente(aluno.id, AGORA.date(), AGORA, turma_id=turma_id)
    historico = presencas.listar_historico_da_turma(turma_id, AGORA.date())
    assert [registro.aluno_id for registro in historico] == [aluno.id]


def test_exclusao_logica_preserva_historico_e_fecha_operacao_ativa(
    repositorios: tuple[
        PostgresTurmaRepository, PostgresAlunoRepository, PostgresPresencaRepository
    ],
) -> None:
    turmas, alunos, presencas = repositorios
    turma_id = criar_turma(turmas, "Visao Computacional")
    aluno = alunos.cadastrar_em_turma(turma_id, "103", "Davi", None, None, AGORA)
    presencas.registrar_se_ausente(aluno.id, AGORA.date(), AGORA, turma_id=turma_id)

    turmas.excluir_logicamente(turma_id, AGORA)

    with pytest.raises(TurmaInativa):
        presencas.listar_da_turma(turma_id, AGORA.date())
    assert len(presencas.listar_historico_da_turma(turma_id, AGORA.date())) == 1
    assert alunos.obter_global_por_matricula("103") is not None


def test_corrida_entre_presenca_e_desvinculo_respeita_ordem_de_lock(
    repositorios: tuple[
        PostgresTurmaRepository, PostgresAlunoRepository, PostgresPresencaRepository
    ],
) -> None:
    turmas, alunos, presencas = repositorios
    turma_id = criar_turma(turmas, "Aprendizado de Maquina")
    aluno = alunos.cadastrar_em_turma(turma_id, "104", "Eva", None, None, AGORA)
    barreira = Barrier(2)

    def registrar() -> str:
        barreira.wait()
        try:
            inserida = presencas.registrar_se_ausente(
                aluno.id, AGORA.date(), AGORA, turma_id=turma_id
            )
        except VinculoInativo:
            return "vinculo_inativo"
        return "presenca_registrada" if inserida else "presenca_existente"

    def desvincular() -> None:
        barreira.wait()
        turmas.desvincular_matricula(turma_id, aluno.matricula, AGORA)

    with ThreadPoolExecutor(max_workers=2) as executor:
        tarefa_registro = executor.submit(registrar)
        tarefa_desvinculo = executor.submit(desvincular)
        resultado = tarefa_registro.result()
        tarefa_desvinculo.result()

    historico = presencas.listar_historico_da_turma(turma_id, AGORA.date())
    if resultado == "vinculo_inativo":
        assert historico == []
    else:
        assert resultado == "presenca_registrada"
        assert len(historico) == 1
