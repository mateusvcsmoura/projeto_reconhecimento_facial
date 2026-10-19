"""Cobertura funcional do repositório de jobs com SQLite sintético.

O advisory lock exclusivo do PostgreSQL é substituído nesta suíte unitária;
concorrência e semântica de locks continuam sendo responsabilidade das provas
de integração PostgreSQL.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    FilaCheia,
    ManifestoTemporario,
    ReservaInvalida,
    TipoJobFacial,
)
from src.infrastructure.database import models
from src.infrastructure.repositories.postgres_job_repository import (
    PostgresJobRepository,
)

AGORA = datetime(2026, 10, 19, 12, 0)
HASH_CREDENCIAL = "a" * 64


@pytest.fixture
def repositorio(monkeypatch: pytest.MonkeyPatch) -> Any:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", poolclass=StaticPool, future=True
    )

    @event.listens_for(engine, "connect")
    def sqlite_btrim(connection: Any, _record: Any) -> None:
        connection.create_function("btrim", 1, lambda value: value.strip())

    models.Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        PostgresJobRepository,
        "_bloquear_admissao",
        staticmethod(lambda _session: None),
    )
    yield PostgresJobRepository(factory)
    engine.dispose()


def _reservar(
    repositorio: PostgresJobRepository,
    *,
    chave: str = "idempotencia-1",
    dono: str = "aluno-1",
    bytes_reservados: int = 4,
    limite_aguardando: int = 10,
    quota_temporaria_bytes: int = 100,
    prazo: datetime | None = None,
    prazo_execucao: datetime | None = None,
) -> Any:
    return repositorio.reservar(
        job_id=uuid4(),
        tipo=TipoJobFacial.CADASTRO,
        dono_id=dono,
        idempotencia_hash=hashlib.sha256(chave.encode()).hexdigest(),
        credencial_hash=HASH_CREDENCIAL,
        prazo=prazo or AGORA + timedelta(minutes=5),
        prazo_execucao=prazo_execucao or AGORA + timedelta(minutes=15),
        bytes_reservados=bytes_reservados,
        limite_aguardando=limite_aguardando,
        quota_temporaria_bytes=quota_temporaria_bytes,
        agora=AGORA,
    )


def _manifesto(job_id: UUID, nome: str = "captura-1.bin") -> ManifestoTemporario:
    return ManifestoTemporario(
        job_id=job_id,
        capturas=(ArquivoTemporario(1, nome, 12),),
    )


def _inserir_tentativa(
    repositorio: PostgresJobRepository, job_id: UUID, *, ordinal: int = 1
) -> None:
    with repositorio.session_factory.begin() as session:
        session.add(
            models.TentativaPresencaWeb(
                id=job_id,
                sessao_id=1,
                turma_id=1,
                aluno_id=1,
                ordinal=ordinal,
                conjunto_id=1,
                versao_referencia=1,
                versao_sessao=1,
                link_id=uuid4(),
                idempotencia_hash=hashlib.sha256(job_id.bytes).hexdigest(),
                estado="recebida",
                iniciada_em=AGORA,
                prazo_envio=AGORA + timedelta(minutes=5),
                recebida_em=AGORA,
                concluida_em=None,
                motivo_tecnico=None,
            )
        )


def _estado(repositorio: PostgresJobRepository, job_id: UUID) -> models.JobFacialWeb:
    with repositorio.session_factory() as session:
        registro = session.get(models.JobFacialWeb, job_id)
        assert registro is not None
        return registro


def test_reserva_idempotente_consulta_e_limites_de_fila(repositorio: Any) -> None:
    primeira = _reservar(
        repositorio,
        chave="mesma-chave",
        bytes_reservados=7,
        limite_aguardando=1,
        quota_temporaria_bytes=10,
    )
    duplicada = _reservar(
        repositorio,
        chave="mesma-chave",
        bytes_reservados=7,
        limite_aguardando=1,
        quota_temporaria_bytes=10,
    )

    assert duplicada.id == primeira.id
    assert repositorio.consultar_reserva(primeira.id).estado == EstadoJobFacial.RECEBIDA
    assert (
        repositorio.consultar_com_credencial(primeira.id, HASH_CREDENCIAL).id
        == primeira.id
    )
    assert repositorio.consultar_com_credencial(primeira.id, "0" * 64) is None
    assert repositorio.ids_com_temporarios() == {primeira.id}
    with pytest.raises(FilaCheia):
        _reservar(
            repositorio,
            chave="limite-fila",
            dono="aluno-2",
            limite_aguardando=1,
        )
    with pytest.raises(FilaCheia):
        _reservar(
            repositorio,
            chave="limite-quota",
            dono="aluno-3",
            bytes_reservados=4,
            limite_aguardando=10,
            quota_temporaria_bytes=10,
        )


def test_submissao_claim_lease_e_finalizacao(repositorio: Any) -> None:
    reserva = _reservar(repositorio)
    manifesto = _manifesto(reserva.id)

    submetido = repositorio.submeter(reserva.id, manifesto, agora=AGORA)
    assert submetido.estado == EstadoJobFacial.ENFILEIRADA
    assert submetido.manifesto == manifesto
    with pytest.raises(ReservaInvalida):
        repositorio.submeter(reserva.id, manifesto, agora=AGORA)

    job = repositorio.reivindicar(agora=AGORA, duracao_lease=timedelta(minutes=2))
    assert job is not None and job.id == reserva.id
    assert job.estado == EstadoJobFacial.PROCESSANDO
    assert job.lease is not None and job.manifesto == manifesto
    assert (
        repositorio.reivindicar(agora=AGORA, duracao_lease=timedelta(minutes=2)) is None
    )
    assert not repositorio.estender_lease(
        job_id=job.id,
        lease="lease-incorreto",
        agora=AGORA,
        duracao_lease=timedelta(minutes=2),
    )
    assert repositorio.estender_lease(
        job_id=job.id,
        lease=job.lease,
        agora=AGORA,
        duracao_lease=timedelta(minutes=3),
    )
    assert repositorio.finalizar(
        job_id=job.id,
        lease=job.lease,
        sucesso=True,
        codigo="concluida",
        agora=AGORA,
    )
    finalizado = repositorio.consultar_reserva(job.id)
    assert finalizado.estado == EstadoJobFacial.CONCLUIDA
    assert finalizado.resultado_codigo == "concluida"
    assert finalizado.manifesto is None
    assert not repositorio.finalizar(
        job_id=job.id,
        lease=job.lease,
        sucesso=False,
        codigo="falha_tecnica",
        agora=AGORA,
    )


def test_reserva_expirada_e_job_com_prazo_de_execucao_expirado(
    repositorio: Any,
) -> None:
    reserva_expirada = _reservar(
        repositorio,
        chave="reserva-expirada",
        dono="aluno-expirado",
        prazo=AGORA + timedelta(minutes=1),
    )
    _inserir_tentativa(repositorio, reserva_expirada.id)
    with pytest.raises(ReservaInvalida):
        repositorio.submeter(
            reserva_expirada.id,
            _manifesto(reserva_expirada.id),
            agora=AGORA + timedelta(minutes=2),
        )
    assert _estado(repositorio, reserva_expirada.id).estado == "expirada"

    job_expirado = _reservar(
        repositorio,
        chave="execucao-expirada",
        dono="aluno-expirado-2",
        prazo_execucao=AGORA + timedelta(minutes=1),
    )
    repositorio.submeter(job_expirado.id, _manifesto(job_expirado.id), agora=AGORA)
    _inserir_tentativa(repositorio, job_expirado.id, ordinal=2)
    assert (
        repositorio.reivindicar(
            agora=AGORA + timedelta(minutes=2),
            duracao_lease=timedelta(minutes=2),
        )
        is None
    )
    assert _estado(repositorio, job_expirado.id).estado == "expirada"
    with repositorio.session_factory() as session:
        tentativas = list(
            session.scalars(
                select(models.TentativaPresencaWeb).where(
                    models.TentativaPresencaWeb.id.in_(
                        [reserva_expirada.id, job_expirado.id]
                    )
                )
            )
        )
    assert len(tentativas) == 2
    assert all(tentativa.estado == "expirada" for tentativa in tentativas)


def test_reagendamento_cancelamento_recuperacao_e_invalidacao(
    repositorio: Any,
) -> None:
    reprocessar = _reservar(repositorio, chave="reprocessar", dono="aluno-reprocessar")
    repositorio.submeter(reprocessar.id, _manifesto(reprocessar.id), agora=AGORA)
    job = repositorio.reivindicar(agora=AGORA, duracao_lease=timedelta(minutes=2))
    assert job is not None and job.lease is not None
    assert not repositorio.aguardar_proxima_etapa(
        job_id=job.id, lease="lease-errado", agora=AGORA
    )
    assert repositorio.aguardar_proxima_etapa(
        job_id=job.id, lease=job.lease, agora=AGORA
    )
    assert _estado(repositorio, job.id).estado == "recebida"
    assert repositorio.ids_com_temporarios() == {job.id}

    repositorio.submeter(job.id, _manifesto(job.id, "captura-2.bin"), agora=AGORA)
    job = repositorio.reivindicar(agora=AGORA, duracao_lease=timedelta(minutes=2))
    assert job is not None and job.lease is not None
    assert not repositorio.invalidar_apos_execucao(
        job_id=job.id, lease="lease-errado", agora=AGORA
    )
    assert repositorio.invalidar_apos_execucao(
        job_id=job.id, lease=job.lease, agora=AGORA
    )
    assert _estado(repositorio, job.id).resultado_codigo == "prazo_expirado"

    cancelar_na_fila = _reservar(
        repositorio, chave="cancelar-fila", dono="aluno-cancelar-fila"
    )
    repositorio.submeter(
        cancelar_na_fila.id, _manifesto(cancelar_na_fila.id), agora=AGORA
    )
    assert repositorio.cancelar(
        job_id=cancelar_na_fila.id,
        credencial_hash=HASH_CREDENCIAL,
        agora=AGORA,
    )
    assert _estado(repositorio, cancelar_na_fila.id).estado == "cancelada"
    assert not repositorio.cancelar(
        job_id=cancelar_na_fila.id,
        credencial_hash=HASH_CREDENCIAL,
        agora=AGORA,
    )
    assert not repositorio.cancelar(
        job_id=uuid4(), credencial_hash=HASH_CREDENCIAL, agora=AGORA
    )

    cancelar_processando = _reservar(
        repositorio, chave="cancelar-ativo", dono="aluno-cancelar-ativo"
    )
    repositorio.submeter(
        cancelar_processando.id,
        _manifesto(cancelar_processando.id),
        agora=AGORA,
    )
    ativo = repositorio.reivindicar(agora=AGORA, duracao_lease=timedelta(minutes=2))
    assert ativo is not None and ativo.lease is not None
    assert repositorio.cancelar(
        job_id=ativo.id,
        credencial_hash=HASH_CREDENCIAL,
        agora=AGORA,
    )
    assert repositorio.finalizar(
        job_id=ativo.id,
        lease=ativo.lease,
        sucesso=True,
        codigo="concluida",
        agora=AGORA,
    )
    assert _estado(repositorio, ativo.id).estado == "cancelada"

    reiniciar = _reservar(repositorio, chave="reiniciar", dono="aluno-reiniciar")
    repositorio.submeter(reiniciar.id, _manifesto(reiniciar.id), agora=AGORA)
    job_reiniciar = repositorio.reivindicar(
        agora=AGORA, duracao_lease=timedelta(minutes=2)
    )
    assert job_reiniciar is not None
    assert repositorio.recuperar_apos_reinicio(agora=AGORA) == {reiniciar.id}
    registro = _estado(repositorio, reiniciar.id)
    assert registro.estado == "rejeitada"
    assert registro.resultado_codigo == "worker_reiniciado"
    assert repositorio.ids_com_temporarios() == set()


@pytest.mark.parametrize(
    "manifesto",
    [
        None,
        {},
        {"capturas": "invalido"},
        {"capturas": ["invalido"]},
        {"capturas": [{"ordinal": True, "nome": "a", "tamanho_bytes": 1}]},
        {"capturas": [{"ordinal": 1, "nome": "a", "tamanho_bytes": False}]},
    ],
)
def test_manifesto_persistido_invalido_e_ignorado(
    manifesto: Any,
) -> None:
    assert PostgresJobRepository._ler_manifesto(uuid4(), manifesto) is None


def test_manifesto_persistido_valido_preserva_capturas() -> None:
    job_id = uuid4()
    manifesto = PostgresJobRepository._ler_manifesto(
        job_id,
        {"capturas": [{"ordinal": 2, "nome": "captura.bin", "tamanho_bytes": 37}]},
    )
    assert manifesto == ManifestoTemporario(
        job_id, (ArquivoTemporario(2, "captura.bin", 37),)
    )
