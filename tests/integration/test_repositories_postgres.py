"""Fase 2 -- repositories contra PostgreSQL real.

Os testes unitarios provam a regra com dubles; estes provam que a
implementacao concreta honra o mesmo contrato.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.turma import Periodo, Turma
from src.domain.errors import AlunoJaCadastrado
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
MODELO = "Facenet512"
CONSENTIMENTO = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
TURMA_ID = 1


@pytest.fixture
def alunos(banco_limpo: Engine) -> PostgresAlunoRepository:
    turmas = PostgresTurmaRepository(banco_limpo)
    turma = turmas.criar(Turma.nova("IA", Periodo.DIURNO), CONSENTIMENTO)
    assert turma.id == TURMA_ID
    return PostgresAlunoRepository(banco_limpo)


@pytest.fixture
def presencas(banco_limpo: Engine) -> PostgresPresencaRepository:
    return PostgresPresencaRepository(banco_limpo)


# -- alunos ----------------------------------------------------------------


def test_cadastrar_devolve_o_id_gerado_pelo_banco(
    alunos: PostgresAlunoRepository,
) -> None:
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID,
        matricula="42",
        nome="Maria Silva",
        foto_arquivo="42.jpg",
        embedding=None,
        consentimento_em=CONSENTIMENTO,
    )

    assert aluno.id > 0
    assert aluno.matricula == "42"
    assert aluno.foto_arquivo == "42.jpg"


def test_matricula_duplicada_vira_erro_de_dominio(
    alunos: PostgresAlunoRepository,
) -> None:
    """A IntegrityError do banco nao vaza para as camadas de cima."""
    alunos.cadastrar_em_turma(TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO)

    with pytest.raises(AlunoJaCadastrado) as capturado:
        alunos.cadastrar_em_turma(TURMA_ID, "42", "Outro", None, None, CONSENTIMENTO)

    assert capturado.value.matricula == "42"


def test_existe_matricula(alunos: PostgresAlunoRepository) -> None:
    alunos.cadastrar_em_turma(TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO)

    assert alunos.existe_matricula_global("42") is True
    assert alunos.existe_matricula_global("43") is False


def test_embedding_faz_round_trip_pelo_bytea(
    alunos: PostgresAlunoRepository,
) -> None:
    """Os floats que saem do banco tem de ser os mesmos que entraram."""
    original = FaceEmbedding.de_valores(np.random.rand(512), MODELO)
    alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", "42.jpg", original, CONSENTIMENTO
    )

    ((_, recuperado),) = alunos.listar_referencias(MODELO, turma_id=TURMA_ID)

    esperado = original.vetor.tolist()
    assert recuperado.vetor.tolist() == pytest.approx(esperado)
    assert recuperado.modelo == MODELO
    assert recuperado.dimensao == 512


def test_aluno_sem_embedding_nao_entra_na_referencia(
    alunos: PostgresAlunoRepository,
) -> None:
    alunos.cadastrar_em_turma(TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO)
    assert alunos.listar_referencias(MODELO, turma_id=TURMA_ID) == []


def test_referencia_filtra_por_modelo(alunos: PostgresAlunoRepository) -> None:
    """Vetores de outro modelo nao podem entrar na comparacao."""
    alunos.cadastrar_em_turma(
        TURMA_ID,
        "1",
        "Ana",
        None,
        FaceEmbedding.de_valores([1.0, 0.0], "Facenet512"),
        CONSENTIMENTO,
    )
    alunos.cadastrar_em_turma(
        TURMA_ID,
        "2",
        "Bruno",
        None,
        FaceEmbedding.de_valores([1.0, 0.0], "ArcFace"),
        CONSENTIMENTO,
    )

    referencias = alunos.listar_referencias("Facenet512", turma_id=TURMA_ID)

    assert [aluno.nome for aluno, _ in referencias] == ["Ana"]


def test_embedding_incompleto_e_rejeitado_pelo_banco(banco_limpo: Engine) -> None:
    """O CHECK impede vetor sem o modelo que o gerou."""
    with pytest.raises(IntegrityError), banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO alunos (matricula, nome, embedding)"
                " VALUES ('99', 'Incompleto', :vetor)"
            ),
            {"vetor": (1).to_bytes(4, "little")},
        )


def test_embedding_de_dimensao_zero_e_rejeitado(banco_limpo: Engine) -> None:
    with pytest.raises(IntegrityError), banco_limpo.begin() as conexao:
        conexao.execute(
            text(
                "INSERT INTO alunos"
                " (matricula, nome, embedding, embedding_modelo, embedding_dim)"
                " VALUES ('98', 'Dim zero', :vetor, 'Facenet512', 0)"
            ),
            {"vetor": (1).to_bytes(4, "little")},
        )


def test_entidade_devolvida_nao_carrega_sqlalchemy(
    alunos: PostgresAlunoRepository,
) -> None:
    """A fronteira devolve dataclass pura, nao objeto de sessao."""
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO
    )
    assert type(aluno).__module__.startswith("src.domain")


# -- presencas -------------------------------------------------------------


def test_primeira_presenca_do_dia_e_inserida(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO
    )
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)

    assert (
        presencas.registrar_se_ausente(
            aluno.id, momento.date(), momento, turma_id=TURMA_ID
        )
        is True
    )


def test_segunda_presenca_no_mesmo_dia_devolve_false(
    alunos: PostgresAlunoRepository,
    presencas: PostgresPresencaRepository,
    banco_limpo: Engine,
) -> None:
    """A constraint do banco resolve, sem SELECT previo e sem corrida."""
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO
    )
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)

    assert (
        presencas.registrar_se_ausente(
            aluno.id, momento.date(), momento, turma_id=TURMA_ID
        )
        is True
    )
    assert (
        presencas.registrar_se_ausente(
            aluno.id, momento.date(), momento.replace(hour=17), turma_id=TURMA_ID
        )
        is False
    )

    with banco_limpo.connect() as conexao:
        total = conexao.execute(text("SELECT count(*) FROM presencas")).scalar_one()
    assert total == 1


def test_dias_diferentes_geram_duas_presencas(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO
    )

    for dia in (dt.date(2026, 3, 10), dt.date(2026, 3, 11)):
        momento = dt.datetime.combine(dia, dt.time(8, 0), tzinfo=TZ)
        assert (
            presencas.registrar_se_ausente(aluno.id, dia, momento, turma_id=TURMA_ID)
            is True
        )


def test_alunos_diferentes_no_mesmo_dia_nao_se_bloqueiam(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    ana = alunos.cadastrar_em_turma(TURMA_ID, "1", "Ana", None, None, CONSENTIMENTO)
    bruno = alunos.cadastrar_em_turma(TURMA_ID, "2", "Bruno", None, None, CONSENTIMENTO)
    dia = dt.date(2026, 3, 10)
    momento = dt.datetime.combine(dia, dt.time(8, 0), tzinfo=TZ)

    assert (
        presencas.registrar_se_ausente(ana.id, dia, momento, turma_id=TURMA_ID) is True
    )
    assert (
        presencas.registrar_se_ausente(bruno.id, dia, momento, turma_id=TURMA_ID)
        is True
    )


def test_instante_gravado_preserva_o_fuso(
    alunos: PostgresAlunoRepository,
    presencas: PostgresPresencaRepository,
    banco_limpo: Engine,
) -> None:
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO
    )
    momento = dt.datetime(2026, 3, 10, 8, 0, tzinfo=TZ)
    presencas.registrar_se_ausente(aluno.id, momento.date(), momento, turma_id=TURMA_ID)

    with banco_limpo.connect() as conexao:
        gravado = conexao.execute(
            text("SELECT registrado_em FROM presencas")
        ).scalar_one()

    assert gravado == momento


# -- listagens para a interface (Fase 8) -----------------------------------


def test_listar_vem_ordenado_por_nome(alunos: PostgresAlunoRepository) -> None:
    alunos.cadastrar_em_turma(TURMA_ID, "2", "Bruno", None, None, CONSENTIMENTO)
    alunos.cadastrar_em_turma(TURMA_ID, "1", "Ana", None, None, CONSENTIMENTO)

    assert [a.nome for a in alunos.listar_por_turma(TURMA_ID)] == ["Ana", "Bruno"]


def test_listar_sem_alunos_devolve_lista_vazia(
    alunos: PostgresAlunoRepository,
) -> None:
    assert alunos.listar_por_turma(TURMA_ID) == []


def test_presencas_do_dia_trazem_o_aluno_resolvido(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria Silva", None, None, CONSENTIMENTO
    )
    presencas.registrar_se_ausente(
        aluno.id, CONSENTIMENTO.date(), CONSENTIMENTO, turma_id=TURMA_ID
    )

    registros = presencas.listar_da_turma(TURMA_ID, CONSENTIMENTO.date())

    assert len(registros) == 1
    assert registros[0].nome == "Maria Silva"
    assert registros[0].matricula == "42"
    assert registros[0].registrado_em == CONSENTIMENTO


def test_presencas_do_dia_ignoram_outros_dias(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    aluno = alunos.cadastrar_em_turma(
        TURMA_ID, "42", "Maria", None, None, CONSENTIMENTO
    )
    ontem = CONSENTIMENTO - dt.timedelta(days=1)
    presencas.registrar_se_ausente(aluno.id, ontem.date(), ontem, turma_id=TURMA_ID)

    assert presencas.listar_da_turma(TURMA_ID, CONSENTIMENTO.date()) == []
    assert len(presencas.listar_da_turma(TURMA_ID, ontem.date())) == 1


def test_presencas_do_dia_vem_ordenadas_por_chegada(
    alunos: PostgresAlunoRepository, presencas: PostgresPresencaRepository
) -> None:
    tarde = alunos.cadastrar_em_turma(
        TURMA_ID, "2", "Chegou depois", None, None, CONSENTIMENTO
    )
    cedo = alunos.cadastrar_em_turma(
        TURMA_ID, "1", "Chegou antes", None, None, CONSENTIMENTO
    )

    momento_tarde = CONSENTIMENTO.replace(hour=9)
    momento_cedo = CONSENTIMENTO.replace(hour=7)
    presencas.registrar_se_ausente(
        tarde.id, CONSENTIMENTO.date(), momento_tarde, turma_id=TURMA_ID
    )
    presencas.registrar_se_ausente(
        cedo.id, CONSENTIMENTO.date(), momento_cedo, turma_id=TURMA_ID
    )

    nomes = [r.nome for r in presencas.listar_da_turma(TURMA_ID, CONSENTIMENTO.date())]

    assert nomes == ["Chegou antes", "Chegou depois"]
