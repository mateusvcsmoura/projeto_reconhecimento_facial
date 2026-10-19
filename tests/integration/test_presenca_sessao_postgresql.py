"""Migration e escritor legado task015 em PostgreSQL descartavel local."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from src.application.services.fila_facial import (
    EstadoJobFacial,
    JobFacial,
    TipoJobFacial,
)
from src.domain.entities.tentativa_presenca import (
    EstadoTentativaPresenca,
)
from src.domain.services.autorizacao import AtorWeb
from src.domain.services.face_recognition import ResultadoFacial
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_presenca_repository import (
    PostgresPresencaRepository,
)
from src.infrastructure.repositories.postgres_presenca_web_repository import (
    PostgresPresencaWebRepository,
    QuotaTentativasEsgotada,
    TentativaAtiva,
)

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_PRESENCA_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_PRESENCA_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_015"
COMENTARIO_BANCO = (
    "projeto_reconhecimento_facial: task 015 disposable attendance database"
)
UTC = dt.UTC
AGORA = dt.datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _url_autorizada() -> str:
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("PostgreSQL task015 exige opt-in para banco descartavel.")
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} nao definida; nenhum arquivo .env e consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise RuntimeError("Banco task015 recusado: URL nao e PostgreSQL.")
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Banco task015 recusado: o destino precisa ser local.")
    if "task015" not in parsed.database.lower():
        raise RuntimeError("Banco task015 recusado: nome sem marcador descartavel.")
    return url


def _alembic(url: str, *args: str) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env={**os.environ, "ALEMBIC_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode:
        raise RuntimeError(
            f"alembic {' '.join(args)} falhou sem exibir URL.\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )


@pytest.fixture(scope="module")
def postgres_presenca_engine() -> Iterator[Engine]:
    url = _url_autorizada()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    migration_iniciada = False
    try:
        with engine.connect() as connection:
            banco, comentario, endereco = connection.execute(
                text(
                    "SELECT current_database(), "
                    "shobj_description(oid, 'pg_database'), inet_server_addr()::text "
                    "FROM pg_database WHERE datname = current_database()"
                )
            ).one()
        if (
            banco != make_url(url).database
            or comentario != COMENTARIO_BANCO
            or endereco is None
        ):
            raise RuntimeError(
                "Banco task015 recusado antes de DDL: nome, marcador ou localidade "
                "nao confirmados."
            )
        migration_iniciada = True
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        _alembic(url, "check")
        yield engine
    finally:
        try:
            if migration_iniciada:
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "TRUNCATE eventos_auditoria_web, contas_web, alunos, "
                            "turmas, jobs_faciais_web, links_cadastro_web "
                            "RESTART IDENTITY CASCADE"
                        )
                    )
                _alembic(url, "downgrade", "base")
        finally:
            engine.dispose()


@pytest.fixture(autouse=True)
def limpar_dados_entre_casos(postgres_presenca_engine: Engine) -> Iterator[None]:
    with postgres_presenca_engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE eventos_auditoria_web, contas_web, alunos, turmas, "
                "jobs_faciais_web, links_cadastro_web RESTART IDENTITY CASCADE"
            )
        )
    yield


@dataclass(frozen=True)
class ContextoPresencaTeste:
    sessao_id: int
    turma_id: int
    aluno_id: int
    conta_id: int
    professor_id: int
    link_id: UUID
    conjunto_id: int


def _criar_contexto_presenca(engine: Engine) -> ContextoPresencaTeste:
    with Session(engine) as session, session.begin():
        conta = models.ContaWeb(
            usuario_normalizado=f"task015-{uuid4().hex}",
            senha_hash="hash-sintetico",
            papel="professor",
            ativa=True,
            troca_senha_obrigatoria=False,
        )
        session.add(conta)
        session.flush()
        professor = models.ProfessorWeb(conta_id=conta.id)
        session.add(professor)
        session.flush()
        turma = models.Turma(
            materia="IA sintetica",
            periodo="diurno",
            responsavel_professor_id=professor.id,
        )
        aluno = models.Aluno(
            matricula=f"T015-{uuid4().hex[:20]}", nome="Aluno sintetico"
        )
        session.add_all((turma, aluno))
        session.flush()
        session.add(models.AlunoTurma(turma_id=turma.id, aluno_id=aluno.id))
        sessao = models.SessaoPresencaWeb(
            turma_id=turma.id,
            criada_por_conta_id=conta.id,
            titulo="Aula sintetica",
            inicio_em=AGORA - dt.timedelta(minutes=10),
            fim_em=AGORA + dt.timedelta(hours=1),
            criada_em=AGORA - dt.timedelta(minutes=11),
            versao=1,
        )
        session.add(sessao)
        session.flush()
        link_id = uuid4()
        session.add(
            models.LinkCadastroWeb(
                id=link_id,
                turma_id=turma.id,
                emitido_por_conta_id=conta.id,
                token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                finalidade="presenca",
                sessao_id=sessao.id,
                criado_em=AGORA - dt.timedelta(minutes=10),
                expira_em=AGORA + dt.timedelta(hours=1),
                finalidade_ate=AGORA + dt.timedelta(hours=1),
            )
        )
        solicitacao = models.SolicitacaoCadastroWeb(
            tipo="atualizacao",
            estado="aprovada",
            convite_ref=None,
            turma_id=turma.id,
            aluno_id=aluno.id,
            matricula=None,
            nome=None,
            consentimento_em=None,
            consentimento_versao=None,
            expira_em=AGORA + dt.timedelta(days=1),
            criada_em=AGORA - dt.timedelta(days=1),
        )
        session.add(solicitacao)
        session.flush()
        conjunto = models.ConjuntoReferenciasWeb(
            solicitacao_id=solicitacao.id,
            aluno_id=aluno.id,
            versao=1,
            estado="ativo",
            job_id=str(uuid4()),
            embedding_modelo="Facenet512",
            embedding_dim=512,
            criado_em=AGORA - dt.timedelta(days=1),
            ativado_em=AGORA - dt.timedelta(days=1),
        )
        session.add(conjunto)
        session.flush()
        session.add_all(
            [
                models.ReferenciaFacialWeb(
                    conjunto_id=conjunto.id,
                    ordinal=ordinal,
                    caminho_privado_relativo=f"synthetic/{uuid4().hex}.bin",
                    embedding=bytes(2048),
                    embedding_modelo="Facenet512",
                    embedding_dim=512,
                    consentimento_em=AGORA - dt.timedelta(days=1),
                    consentimento_versao="synthetic-v1",
                    capturada_em=AGORA - dt.timedelta(days=1),
                )
                for ordinal in (1, 2, 3)
            ]
        )
        return ContextoPresencaTeste(
            sessao_id=sessao.id,
            turma_id=turma.id,
            aluno_id=aluno.id,
            conta_id=conta.id,
            professor_id=professor.id,
            link_id=link_id,
            conjunto_id=conjunto.id,
        )


def _criar_job_recebido(
    engine: Engine, contexto: ContextoPresencaTeste, agora: dt.datetime
) -> UUID:
    job_id = uuid4()
    idempotencia = hashlib.sha256(uuid4().bytes).hexdigest()
    with Session(engine) as session, session.begin():
        session.add(
            models.JobFacialWeb(
                id=job_id,
                dono_id=f"presenca:{contexto.sessao_id}:{contexto.aluno_id}",
                tipo="presenca",
                estado=EstadoJobFacial.RECEBIDA.value,
                idempotencia_hash=idempotencia,
                credencial_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                manifesto=None,
                bytes_reservados=1024,
                prazo_reserva=agora + dt.timedelta(minutes=2),
                prazo_execucao=agora + dt.timedelta(minutes=10),
                criada_em=agora - dt.timedelta(seconds=1),
                atualizada_em=agora,
            )
        )
    return job_id


def _reservar_tentativa(
    engine: Engine,
    repo: PostgresPresencaWebRepository,
    contexto: ContextoPresencaTeste,
    indice: int,
    agora: dt.datetime,
) -> UUID:
    job_id = _criar_job_recebido(engine, contexto, agora)
    repo.reservar_tentativa(
        job_id=job_id,
        sessao_id=contexto.sessao_id,
        turma_id=contexto.turma_id,
        link_id=contexto.link_id,
        aluno_id=contexto.aluno_id,
        idempotencia_hash=hashlib.sha256(f"idem-{indice}".encode()).hexdigest(),
        iniciada_em=agora,
        prazo_envio=agora + dt.timedelta(seconds=120),
    )
    return job_id


def _preparar_processamento_valido(
    engine: Engine,
    contexto: ContextoPresencaTeste,
    job_id: UUID,
    *,
    recebida_em: dt.datetime,
    concluir_em: dt.datetime,
) -> tuple[JobFacial, ResultadoFacial]:
    lease = f"lease-{uuid4().hex}"
    lease_expira = concluir_em + dt.timedelta(minutes=2)
    with Session(engine) as session, session.begin():
        job = session.get(models.JobFacialWeb, job_id)
        tentativa = session.get(models.TentativaPresencaWeb, job_id)
        assert job is not None and tentativa is not None
        job.estado = EstadoJobFacial.PROCESSANDO.value
        job.manifesto = {"capturas": [1, 2, 3]}
        job.lease_hash = hashlib.sha256(lease.encode()).hexdigest()
        job.lease_expira_em = lease_expira
        job.iniciada_em = recebida_em
        job.atualizada_em = recebida_em
        tentativa.estado = EstadoTentativaPresenca.PROCESSANDO.value
        tentativa.recebida_em = recebida_em
        session.add(
            models.DesafioVerificacaoWeb(
                id=job_id,
                aluno_id=contexto.aluno_id,
                conjunto_id=contexto.conjunto_id,
                versao_referencia=1,
                nonce_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                direcao="esquerda",
                expira_em=concluir_em + dt.timedelta(minutes=2),
                etapa_validada=3,
                etapa_recebida=3,
                estado="concluido",
                atualizada_em=recebida_em,
            )
        )
        worker = JobFacial(
            id=job_id,
            dono_id=job.dono_id,
            tipo=TipoJobFacial.PRESENCA,
            estado=EstadoJobFacial.PROCESSANDO,
            criada_em=job.criada_em,
            prazo=job.prazo_reserva,
            prazo_execucao=job.prazo_execucao,
            atualizada_em=recebida_em,
            manifesto=None,
            lease=lease,
            lease_expira_em=lease_expira,
            resultado_codigo=None,
            credencial_hash=job.credencial_hash,
        )
    decisao = ResultadoFacial(
        identidade_ok=True,
        desafio_ok=True,
        antispoofing_ok=True,
        qualidade_ok=True,
        motivo_tecnico=None,
        versao_referencia=1,
        politica="mediana-3",
    )
    return worker, decisao


def test_migration_0011_preserva_indices_legados_e_adiciona_estado_versionado(
    postgres_presenca_engine: Engine,
) -> None:
    inspetor = inspect(postgres_presenca_engine)
    indices = {item["name"]: item for item in inspetor.get_indexes("presencas")}
    unicas = {item["name"] for item in inspetor.get_unique_constraints("presencas")}

    assert "uq_presencas_turma_aluno_dia" in indices
    assert "uq_presencas_legado_aluno_dia" in indices
    assert "uq_presencas_sessao_aluno" in indices
    assert "uq_presencas_turma_aluno_dia" not in unicas
    assert "sessao_id IS NULL" in str(
        indices["uq_presencas_turma_aluno_dia"]["dialect_options"]["postgresql_where"]
    )
    colunas = {item["name"] for item in inspetor.get_columns("presencas")}
    assert {"status", "origem", "versao", "corrigida_em"} <= colunas
    assert "revisoes_presenca_web" in inspetor.get_table_names()
    with postgres_presenca_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "0011"
        )


def test_escritor_cli_diario_continua_idempotente_com_indice_parcial(
    postgres_presenca_engine: Engine,
) -> None:
    with Session(postgres_presenca_engine) as session, session.begin():
        turma = models.Turma(materia="IA", periodo="noturno")
        aluno = models.Aluno(matricula="00015", nome="Aluno Sintetico")
        session.add_all((turma, aluno))
        session.flush()
        session.add(models.AlunoTurma(turma_id=turma.id, aluno_id=aluno.id))
        aluno_id = aluno.id
        turma_id = turma.id

    repo = PostgresPresencaRepository(postgres_presenca_engine)
    import datetime as dt

    dia = dt.date(2026, 10, 18)
    momento = dt.datetime(2026, 10, 18, 12, tzinfo=dt.UTC)
    assert repo.registrar_se_ausente(aluno_id, dia, momento, turma_id=turma_id) is True
    assert (
        repo.registrar_se_ausente(
            aluno_id, dia, momento + dt.timedelta(seconds=1), turma_id=turma_id
        )
        is False
    )


def test_reserva_concorrente_mantem_uma_tentativa_ativa_e_limite_de_tres(
    postgres_presenca_engine: Engine,
) -> None:
    engine = postgres_presenca_engine
    contexto = _criar_contexto_presenca(engine)
    repo = PostgresPresencaWebRepository(engine)
    jobs = [
        _criar_job_recebido(engine, contexto, AGORA + dt.timedelta(seconds=indice))
        for indice in range(5)
    ]

    def reservar(job_id: UUID, indice: int) -> tuple[str, UUID | None]:
        try:
            tentativa, _ = repo.reservar_tentativa(
                job_id=job_id,
                sessao_id=contexto.sessao_id,
                turma_id=contexto.turma_id,
                link_id=contexto.link_id,
                aluno_id=contexto.aluno_id,
                idempotencia_hash=hashlib.sha256(
                    f"concorrente-{indice}".encode()
                ).hexdigest(),
                iniciada_em=AGORA,
                prazo_envio=AGORA + dt.timedelta(seconds=120),
            )
        except TentativaAtiva:
            return "ativa", None
        return "reservada", tentativa.id

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        resultados = list(executor.map(reservar, jobs[:2], (1, 2)))
    assert sorted(resultado[0] for resultado in resultados) == [
        "ativa",
        "reservada",
    ]
    primeira_id = next(
        tentativa_id
        for estado, tentativa_id in resultados
        if estado == "reservada" and tentativa_id is not None
    )
    repo.rejeitar_tentativa(
        primeira_id, "falha_sintetica", agora=AGORA + dt.timedelta(seconds=1)
    )

    segunda, _ = repo.reservar_tentativa(
        job_id=jobs[2],
        sessao_id=contexto.sessao_id,
        turma_id=contexto.turma_id,
        link_id=contexto.link_id,
        aluno_id=contexto.aluno_id,
        idempotencia_hash=hashlib.sha256(b"terceira-chave").hexdigest(),
        iniciada_em=AGORA + dt.timedelta(seconds=2),
        prazo_envio=AGORA + dt.timedelta(seconds=122),
    )
    repo.rejeitar_tentativa(
        segunda.id, "falha_sintetica", agora=AGORA + dt.timedelta(seconds=3)
    )

    terceira, _ = repo.reservar_tentativa(
        job_id=jobs[3],
        sessao_id=contexto.sessao_id,
        turma_id=contexto.turma_id,
        link_id=contexto.link_id,
        aluno_id=contexto.aluno_id,
        idempotencia_hash=hashlib.sha256(b"quarta-chave").hexdigest(),
        iniciada_em=AGORA + dt.timedelta(seconds=4),
        prazo_envio=AGORA + dt.timedelta(seconds=124),
    )
    repo.rejeitar_tentativa(
        terceira.id, "falha_sintetica", agora=AGORA + dt.timedelta(seconds=5)
    )

    with pytest.raises(QuotaTentativasEsgotada):
        repo.reservar_tentativa(
            job_id=jobs[4],
            sessao_id=contexto.sessao_id,
            turma_id=contexto.turma_id,
            link_id=contexto.link_id,
            aluno_id=contexto.aluno_id,
            idempotencia_hash=hashlib.sha256(b"quinta-chave").hexdigest(),
            iniciada_em=AGORA + dt.timedelta(seconds=6),
            prazo_envio=AGORA + dt.timedelta(seconds=126),
        )

    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM tentativas_presenca_web "
                    "WHERE sessao_id = :sessao AND aluno_id = :aluno"
                ),
                {"sessao": contexto.sessao_id, "aluno": contexto.aluno_id},
            ).scalar_one()
            == 3
        )


def test_revogacao_da_sessao_impede_commit_tardio_do_worker(
    postgres_presenca_engine: Engine,
) -> None:
    engine = postgres_presenca_engine
    contexto = _criar_contexto_presenca(engine)
    repo = PostgresPresencaWebRepository(engine)
    job_id = _reservar_tentativa(engine, repo, contexto, 1, AGORA)
    job_worker, decisao = _preparar_processamento_valido(
        engine,
        contexto,
        job_id,
        recebida_em=AGORA + dt.timedelta(seconds=60),
        concluir_em=AGORA + dt.timedelta(seconds=63),
    )

    ator = AtorWeb(
        contexto.conta_id,
        "professor",
        True,
        False,
        contexto.professor_id,
    )
    canceladas, limpar = repo.revogar_sessao(
        ator, contexto.sessao_id, agora=AGORA + dt.timedelta(seconds=62)
    )
    assert canceladas == 1
    assert limpar == ()

    assert (
        repo.concluir_presenca(
            job_worker, decisao, agora=AGORA + dt.timedelta(seconds=63)
        )
        is None
    )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM presencas WHERE sessao_id = :sessao"),
                {"sessao": contexto.sessao_id},
            ).scalar_one()
            == 0
        )


def test_commit_tempestivo_pode_terminar_depois_e_duas_sessoes_no_dia_sao_distintas(
    postgres_presenca_engine: Engine,
) -> None:
    engine = postgres_presenca_engine
    contexto = _criar_contexto_presenca(engine)
    repo = PostgresPresencaWebRepository(engine)

    job_primeira = _reservar_tentativa(engine, repo, contexto, 1, AGORA)
    worker_primeira, decisao_primeira = _preparar_processamento_valido(
        engine,
        contexto,
        job_primeira,
        recebida_em=AGORA + dt.timedelta(seconds=60),
        concluir_em=AGORA + dt.timedelta(seconds=180),
    )
    primeira = repo.concluir_presenca(
        worker_primeira,
        decisao_primeira,
        agora=AGORA + dt.timedelta(seconds=180),
    )
    assert primeira is not None
    assert primeira.duplicada is False

    with Session(engine) as session, session.begin():
        segunda_sessao = models.SessaoPresencaWeb(
            turma_id=contexto.turma_id,
            criada_por_conta_id=contexto.conta_id,
            titulo="Segunda aula sintetica",
            inicio_em=AGORA - dt.timedelta(minutes=10),
            fim_em=AGORA + dt.timedelta(hours=1),
            criada_em=AGORA - dt.timedelta(minutes=11),
            versao=1,
        )
        session.add(segunda_sessao)
        session.flush()
        segundo_link_id = uuid4()
        session.add(
            models.LinkCadastroWeb(
                id=segundo_link_id,
                turma_id=contexto.turma_id,
                emitido_por_conta_id=contexto.conta_id,
                token_hash=hashlib.sha256(uuid4().bytes).hexdigest(),
                finalidade="presenca",
                sessao_id=segunda_sessao.id,
                criado_em=AGORA - dt.timedelta(minutes=10),
                expira_em=AGORA + dt.timedelta(hours=1),
                finalidade_ate=AGORA + dt.timedelta(hours=1),
            )
        )
        contexto_segunda = replace(
            contexto, sessao_id=segunda_sessao.id, link_id=segundo_link_id
        )

    job_segunda = _reservar_tentativa(
        engine, repo, contexto_segunda, 2, AGORA + dt.timedelta(seconds=200)
    )
    worker_segunda, decisao_segunda = _preparar_processamento_valido(
        engine,
        contexto_segunda,
        job_segunda,
        recebida_em=AGORA + dt.timedelta(seconds=260),
        concluir_em=AGORA + dt.timedelta(seconds=380),
    )
    segunda = repo.concluir_presenca(
        worker_segunda,
        decisao_segunda,
        agora=AGORA + dt.timedelta(seconds=380),
    )
    assert segunda is not None
    assert segunda.duplicada is False

    with engine.connect() as connection:
        linhas = connection.execute(
            text(
                "SELECT sessao_id, data_referencia FROM presencas "
                "WHERE aluno_id = :aluno ORDER BY sessao_id"
            ),
            {"aluno": contexto.aluno_id},
        ).all()
    assert len(linhas) == 2
    assert linhas[0].sessao_id != linhas[1].sessao_id
    assert linhas[0].data_referencia == linhas[1].data_referencia
