"""Locks, idempotência e migration reais da fila task012."""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    FilaCheia,
    FilaFacial,
    ManifestoTemporario,
    TipoJobFacial,
)
from src.application.services.worker_facial import (
    CodigoResultadoWorker,
    ResultadoWorker,
    WorkerFacial,
)
from src.domain.services.desafio_captura import (
    ContextoDesafio,
    DesafioCaptura,
    EstadoDesafio,
    EvidenciaEtapa,
    OrientacaoPose,
)
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_desafio_repository import (
    PostgresDesafioRepository,
)
from src.infrastructure.repositories.postgres_job_repository import (
    PostgresJobRepository,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)

ROOT = Path(__file__).resolve().parents[2]
ENV_URL = "FACE_WEB_WORKER_TEST_DATABASE_URL"
ENV_AUTORIZACAO = "FACE_WEB_WORKER_TEST_DB_AUTORIZACAO"
TOKEN_AUTORIZACAO = "AUTORIZO_MIGRAR_BANCO_DESCARTAVEL_TASK_012"
COMENTARIO_BANCO = "projeto_reconhecimento_facial: task 012 disposable worker database"
UTC = dt.UTC


def _url_autorizada() -> str:
    if os.environ.get(ENV_AUTORIZACAO) != TOKEN_AUTORIZACAO:
        pytest.skip("PostgreSQL task012 exige opt-in para banco descartável.")
    url = os.environ.get(ENV_URL)
    if not url:
        pytest.skip(f"{ENV_URL} não definida; nenhum .env será consultado.")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or not parsed.database:
        raise RuntimeError("Banco task012 recusado: URL não é PostgreSQL.")
    if parsed.host not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Banco task012 recusado: a conexão precisa ser local.")
    if "task012" not in parsed.database.lower():
        raise RuntimeError("Banco task012 recusado: nome sem marcador descartável.")
    return url


def _alembic(url: str, *argumentos: str) -> None:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *argumentos],
        cwd=ROOT,
        env={**os.environ, "ALEMBIC_DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    if resultado.returncode:
        raise RuntimeError(
            f"alembic {' '.join(argumentos)} falhou sem exibir URL.\n"
            f"{resultado.stdout}\n{resultado.stderr}"
        )


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    url = _url_autorizada()
    engine = create_engine(url, future=True, pool_pre_ping=True)
    migration_started = False
    try:
        with engine.connect() as connection:
            comentario, endereco = connection.execute(
                text(
                    "SELECT shobj_description(oid, 'pg_database'), "
                    "inet_server_addr()::text FROM pg_database "
                    "WHERE datname = current_database()"
                )
            ).one()
        if comentario != COMENTARIO_BANCO:
            raise RuntimeError(
                "Banco task012 recusado antes de DDL: marcador descartável ausente."
            )
        if endereco is None:
            raise RuntimeError(
                "Banco task012 recusado: não foi possível confirmar servidor local."
            )
        migration_started = True
        _alembic(url, "downgrade", "base")
        _alembic(url, "upgrade", "head")
        _alembic(url, "check")
        yield engine
    finally:
        try:
            if migration_started:
                with engine.begin() as connection:
                    connection.execute(
                        text("TRUNCATE jobs_faciais_web RESTART IDENTITY CASCADE")
                    )
                _alembic(url, "downgrade", "base")
        finally:
            engine.dispose()


@pytest.fixture(autouse=True)
def limpar_jobs_entre_casos(postgres_engine: Engine) -> Iterator[None]:
    with postgres_engine.begin() as connection:
        connection.execute(text("TRUNCATE jobs_faciais_web RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def fila(postgres_engine: Engine) -> FilaFacial:
    factory: sessionmaker[Session] = sessionmaker(
        bind=postgres_engine, expire_on_commit=False, future=True
    )
    return FilaFacial(
        PostgresJobRepository(factory),
        segredo=b"task012-secret-synthetic-test-value-32-bytes-minimum",
        relogio=lambda: dt.datetime.now(UTC),
        limite_aguardando=10,
        quota_temporaria_bytes=300 * 1024 * 1024,
        max_bytes_por_captura=8 * 1024 * 1024,
        max_capturas=3,
        duracao_lease=dt.timedelta(seconds=1),
    )


def _manifesto(job_id: uuid.UUID) -> ManifestoTemporario:
    return ManifestoTemporario(
        job_id,
        (ArquivoTemporario(1, "captura-1.bin", 3),),
    )


def test_admissao_concorrente_limita_dez_espera_e_um_ativo(
    postgres_engine: Engine,
    fila: FilaFacial,
) -> None:
    factory: sessionmaker[Session] = sessionmaker(
        bind=postgres_engine, expire_on_commit=False, future=True
    )

    def reservar(indice: int) -> uuid.UUID | None:
        try:
            reserva = fila.reservar(
                TipoJobFacial.PRESENCA,
                f"owner:{indice}",
                f"idem:{indice}",
                dt.datetime.now(UTC) + dt.timedelta(minutes=4),
            )
            return reserva.id
        except FilaCheia:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        resultados = list(pool.map(reservar, range(24)))
    ids = [job_id for job_id in resultados if job_id is not None]
    assert len(ids) == 10

    for job_id in ids:
        fila.submeter(job_id, _manifesto(job_id))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        ativos = list(pool.map(lambda _index: fila.reivindicar(), range(8)))
    reivindicados = [job for job in ativos if job is not None]
    assert len(reivindicados) == 1
    assert reivindicados[0].estado is EstadoJobFacial.PROCESSANDO

    extra = fila.reservar(
        TipoJobFacial.PRESENCA,
        "owner:extra",
        "idem:extra",
        dt.datetime.now(UTC) + dt.timedelta(minutes=4),
    )
    assert extra.id not in ids
    with pytest.raises(FilaCheia):
        fila.reservar(
            TipoJobFacial.PRESENCA,
            "owner:overflow",
            "idem:overflow",
            dt.datetime.now(UTC) + dt.timedelta(minutes=4),
        )

    with factory() as session:
        ativos_no_banco = session.scalar(
            select(func.count())
            .select_from(models.JobFacialWeb)
            .where(models.JobFacialWeb.estado == EstadoJobFacial.PROCESSANDO.value)
        )
        aguardando_no_banco = session.scalar(
            select(func.count())
            .select_from(models.JobFacialWeb)
            .where(
                models.JobFacialWeb.estado.in_(
                    [EstadoJobFacial.RECEBIDA.value, EstadoJobFacial.ENFILEIRADA.value]
                )
            )
        )
    assert ativos_no_banco == 1
    assert aguardando_no_banco == 10


def test_idempotencia_concorrente_lease_expirado_e_recuperacao_de_restart(
    postgres_engine: Engine,
    fila: FilaFacial,
) -> None:
    def reservar(_indice: int) -> uuid.UUID:
        return fila.reservar(
            TipoJobFacial.PRESENCA,
            "owner:stable",
            "idem:stable",
            dt.datetime.now(UTC) + dt.timedelta(minutes=4),
        ).id

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        ids = list(pool.map(reservar, range(12)))
    assert len(set(ids)) == 1

    job_id = ids[0]
    fila.submeter(job_id, _manifesto(job_id))
    job = fila.reivindicar()
    assert job is not None and job.lease is not None
    expirado_em = dt.datetime.now(UTC) + dt.timedelta(seconds=2)
    factory: sessionmaker[Session] = sessionmaker(
        bind=postgres_engine, expire_on_commit=False, future=True
    )
    repository = PostgresJobRepository(factory)
    assert not repository.finalizar(
        job_id=job.id,
        lease=job.lease,
        sucesso=True,
        codigo="concluida",
        agora=expirado_em,
    )
    assert repository.invalidar_apos_execucao(
        job_id=job.id,
        lease=job.lease,
        agora=expirado_em,
    )

    job_reiniciado = fila.reservar(
        TipoJobFacial.PRESENCA,
        "owner:restart",
        "idem:restart",
        dt.datetime.now(UTC) + dt.timedelta(minutes=4),
    )
    fila.submeter(job_reiniciado.id, _manifesto(job_reiniciado.id))
    job_ativo = fila.reivindicar()
    assert job_ativo is not None
    interrompidos = fila.recuperar_apos_reinicio()
    assert job_ativo.id in interrompidos
    assert fila.reivindicar() is None


def test_cancelamento_nao_reivindica_job_e_status_e_rejeitado(
    fila: FilaFacial,
) -> None:
    reserva = fila.reservar(
        TipoJobFacial.PRESENCA,
        "owner:cancel",
        "idem:cancel",
        dt.datetime.now(UTC) + dt.timedelta(minutes=4),
    )
    job_id = reserva.id
    fila.submeter(job_id, _manifesto(job_id))

    assert fila.cancelar(job_id, reserva.credencial)
    status = fila.consultar(job_id, reserva.credencial)

    assert status.estado is EstadoJobFacial.REJEITADA
    assert status.codigo == "cancelada"
    assert fila.reivindicar() is None


def test_advisory_lock_mantem_um_worker_ativo_por_database(
    postgres_engine: Engine,
) -> None:
    factory: sessionmaker[Session] = sessionmaker(
        bind=postgres_engine, expire_on_commit=False, future=True
    )
    primeiro = PostgresJobRepository(factory)
    segundo = PostgresJobRepository(factory)

    with primeiro.worker_unico() as lock_um, segundo.worker_unico() as lock_dois:
        assert lock_um
        assert not lock_dois

    with segundo.worker_unico() as depois:
        assert depois


def test_worker_apos_reinicio_processa_job_que_ainda_estava_na_fila(
    fila: FilaFacial, postgres_engine: Engine, tmp_path: Path
) -> None:
    reserva = fila.reservar(
        TipoJobFacial.PRESENCA,
        "sessao:task019a:aluno:sintetico",
        f"restart-pending-{uuid.uuid4()}",
        dt.datetime.now(UTC) + dt.timedelta(minutes=2),
    )
    armazenamento = TemporaryCaptureStorage(
        tmp_path / "capturas-restart",
        max_bytes_per_capture=32,
        max_captures=3,
    )
    armazenamento.salvar_captura(reserva.id, 1, b"frame-sintetico")
    fila.submeter(reserva.id, armazenamento.manifesto(reserva.id))

    class ProcessadorComFalha:
        chamadas = 0

        def processar(self, _job, capturas):
            self.chamadas += 1
            assert capturas == (b"frame-sintetico",)
            return ResultadoWorker(False, CodigoResultadoWorker.FALHA_TECNICA)

    processador = ProcessadorComFalha()
    worker_apos_reinicio = WorkerFacial(
        fila,
        armazenamento,
        processadores={TipoJobFacial.PRESENCA: processador},
    )
    with postgres_engine.connect() as connection:
        presencas_antes = connection.scalar(
            select(func.count()).select_from(models.Presenca)
        )
    try:
        worker_apos_reinicio.inicializar()
        assert worker_apos_reinicio.executar_um()
        estado = fila.consultar(reserva.id, reserva.credencial)
    finally:
        worker_apos_reinicio.fechar()
    with postgres_engine.connect() as connection:
        presencas_depois = connection.scalar(
            select(func.count()).select_from(models.Presenca)
        )

    assert processador.chamadas == 1
    assert estado.estado is EstadoJobFacial.REJEITADA
    assert estado.codigo == CodigoResultadoWorker.FALHA_TECNICA.value
    assert not armazenamento.raiz.joinpath(str(reserva.id)).exists()
    assert presencas_depois == presencas_antes


def test_desafio_verificacao_transiciona_no_postgresql(
    postgres_engine: Engine,
    fila: FilaFacial,
) -> None:
    factory: sessionmaker[Session] = sessionmaker(
        bind=postgres_engine, expire_on_commit=False, future=True
    )
    job_id: uuid.UUID | None = None
    aluno_id: int | None = None
    turma_id: int | None = None
    solicitacao_id: int | None = None
    conjunto_id: int | None = None
    try:
        reserva = fila.reservar(
            TipoJobFacial.PRESENCA,
            "conta:task013",
            f"desafio:{uuid.uuid4()}",
            dt.datetime.now(UTC) + dt.timedelta(minutes=4),
        )
        job_id = reserva.id
        agora = dt.datetime.now(UTC)
        with factory() as session, session.begin():
            turma = models.Turma(materia="IA de teste", periodo="noturno")
            session.add(turma)
            session.flush()
            turma_id = turma.id
            aluno = models.Aluno(
                matricula=f"T013-{uuid.uuid4().hex[:20]}", nome="Aluno sintético"
            )
            session.add(aluno)
            session.flush()
            aluno_id = aluno.id
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
                expira_em=agora + dt.timedelta(days=1),
                criada_em=agora,
            )
            session.add(solicitacao)
            session.flush()
            solicitacao_id = solicitacao.id
            conjunto = models.ConjuntoReferenciasWeb(
                solicitacao_id=solicitacao.id,
                aluno_id=aluno.id,
                versao=1,
                estado="ativo",
                job_id=str(uuid.uuid4()),
                embedding_modelo="Facenet512",
                embedding_dim=512,
                criado_em=agora,
                ativado_em=agora,
            )
            session.add(conjunto)
            session.flush()
            conjunto_id = conjunto.id

        repository = PostgresDesafioRepository(factory)
        service = DesafioCaptura(
            repository, segredo=b"task013-synthetic-secret-with-at-least-32-bytes"
        )
        desafio = service.emitir(
            ContextoDesafio(
                job_id,
                aluno_id,
                conjunto_id,
                1,
                agora + dt.timedelta(minutes=2),
            ),
            agora,
        )
        fila.submeter(job_id, _manifesto(job_id))
        regular = fila.reservar(
            TipoJobFacial.PRESENCA,
            "conta:task013-regular",
            f"regular:{uuid.uuid4()}",
            agora + dt.timedelta(minutes=4),
        )
        fila.submeter(regular.id, _manifesto(regular.id))
        ativo = fila.reivindicar()
        assert ativo is not None and ativo.id == job_id
        recebido = service.registrar_etapa_recebida(desafio.id, desafio.nonce, 1, agora)
        validado = service.validar_etapa(
            desafio.id,
            1,
            EvidenciaEtapa(1, OrientacaoPose.FRENTE, True, True, True, 1),
            agora,
        )

        assert recebido.estado is EstadoDesafio.ETAPA_RECEBIDA
        assert validado.estado is EstadoDesafio.AGUARDANDO_ETAPA
        assert fila.aguardar_proxima_etapa(ativo)
        fila.submeter(
            job_id,
            ManifestoTemporario(
                job_id,
                (
                    ArquivoTemporario(1, "captura-1.bin", 4),
                    ArquivoTemporario(2, "captura-2.bin", 4),
                ),
            ),
        )
        retomado = fila.reivindicar()
        assert retomado is not None and retomado.id == job_id
        assert repository.obter(desafio.id) is not None
        with pytest.raises(RuntimeError, match="desafios persistidos"):
            _alembic(
                postgres_engine.url.render_as_string(hide_password=False),
                "downgrade",
                "0007",
            )
        assert repository.obter(desafio.id) is not None
    finally:
        with factory() as session, session.begin():
            if job_id is not None:
                session.query(models.DesafioVerificacaoWeb).filter_by(
                    id=job_id
                ).delete()
                session.query(models.JobFacialWeb).filter_by(id=job_id).delete()
            if conjunto_id is not None:
                session.query(models.ConjuntoReferenciasWeb).filter_by(
                    id=conjunto_id
                ).delete()
            if solicitacao_id is not None:
                session.query(models.SolicitacaoCadastroWeb).filter_by(
                    id=solicitacao_id
                ).delete()
            if aluno_id is not None:
                session.query(models.Aluno).filter_by(id=aluno_id).delete()
            if turma_id is not None:
                session.query(models.Turma).filter_by(id=turma_id).delete()
