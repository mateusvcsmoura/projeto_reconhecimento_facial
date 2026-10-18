from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import replace
from typing import Any

import pytest

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    FilaCheia,
    FilaFacial,
    JobFacial,
    ManifestoTemporario,
    TipoJobFacial,
)

UTC = dt.UTC
AGORA = dt.datetime(2026, 10, 18, 12, tzinfo=UTC)


class RepositorioFilaFake:
    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, JobFacial] = {}
        self.chaves: dict[tuple[str, str, str], uuid.UUID] = {}
        self.limite_pendentes = 10

    def reservar(self, **dados: Any) -> JobFacial:
        chave = (
            dados["dono_id"],
            dados["tipo"].value,
            dados["idempotencia_hash"],
        )
        existente = self.chaves.get(chave)
        if existente is not None:
            return self.jobs[existente]
        pendentes = sum(
            job.estado in (EstadoJobFacial.RECEBIDA, EstadoJobFacial.ENFILEIRADA)
            for job in self.jobs.values()
        )
        if pendentes >= self.limite_pendentes:
            raise FilaCheia()
        job = JobFacial(
            id=dados["job_id"],
            dono_id=dados["dono_id"],
            tipo=dados["tipo"],
            estado=EstadoJobFacial.RECEBIDA,
            criada_em=dados["agora"],
            prazo=dados["prazo"],
            prazo_execucao=dados["prazo_execucao"],
            atualizada_em=dados["agora"],
            manifesto=None,
            lease=None,
            lease_expira_em=None,
            resultado_codigo=None,
            credencial_hash=dados["credencial_hash"],
        )
        self.jobs[job.id] = job
        self.chaves[chave] = job.id
        return job

    def submeter(
        self, reserva_id: uuid.UUID, manifesto: ManifestoTemporario, **_: Any
    ) -> JobFacial:
        job = self.jobs[reserva_id]
        atualizado = replace(
            job,
            estado=EstadoJobFacial.ENFILEIRADA,
            manifesto=manifesto,
        )
        self.jobs[reserva_id] = atualizado
        return atualizado

    def consultar_com_credencial(
        self, job_id: uuid.UUID, credencial_hash: str
    ) -> JobFacial | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        return job if job.credencial_hash == credencial_hash else None

    def consultar_reserva(self, job_id: uuid.UUID) -> JobFacial | None:
        return self.jobs.get(job_id)

    def aguardar_proxima_etapa(self, **dados: Any) -> bool:
        job = self.jobs[dados["job_id"]]
        if job.estado is not EstadoJobFacial.PROCESSANDO:
            return False
        self.jobs[job.id] = replace(
            job,
            estado=EstadoJobFacial.RECEBIDA,
            manifesto=None,
            lease=None,
            lease_expira_em=None,
            resultado_codigo=None,
            atualizada_em=dados["agora"],
        )
        return True


def _manifesto(job_id: uuid.UUID, total: int = 3) -> ManifestoTemporario:
    return ManifestoTemporario(
        job_id=job_id,
        capturas=tuple(
            ArquivoTemporario(ordinal=i, nome=f"captura-{i}.bin", tamanho_bytes=4)
            for i in range(1, total + 1)
        ),
    )


def test_reserva_repetida_preserva_id_e_credencial_opaca() -> None:
    repository = RepositorioFilaFake()
    queue = FilaFacial(repository, segredo=b"s" * 32, relogio=lambda: AGORA)
    prazo = AGORA + dt.timedelta(minutes=5)

    primeira = queue.reservar("cadastro", "conta:12", "idem-1", prazo)
    repetida = queue.reservar("cadastro", "conta:12", "idem-1", prazo)

    assert primeira.id == repetida.id
    assert primeira.credencial == repetida.credencial
    assert len(primeira.credencial) >= 32
    assert (
        repository.jobs[primeira.id].credencial_hash
        == hashlib.sha256(primeira.credencial.encode()).hexdigest()
    )


def test_reserva_rejeita_tipo_desconhecido_e_prazo_invalido() -> None:
    queue = FilaFacial(RepositorioFilaFake(), segredo=b"s" * 32, relogio=lambda: AGORA)

    with pytest.raises(ValueError, match="tipo"):
        queue.reservar("shell", "conta:12", "idem-1", AGORA + dt.timedelta(minutes=1))
    with pytest.raises(ValueError, match="prazo"):
        queue.reservar("cadastro", "conta:12", "idem-2", AGORA)


def test_cadastro_exige_tres_referencias_validas_na_submissao() -> None:
    repository = RepositorioFilaFake()
    queue = FilaFacial(repository, segredo=b"s" * 32, relogio=lambda: AGORA)
    reserva = queue.reservar(
        TipoJobFacial.CADASTRO,
        "conta:12",
        "idem-1",
        AGORA + dt.timedelta(minutes=5),
    )

    with pytest.raises(ValueError, match="três"):
        queue.submeter(reserva.id, _manifesto(reserva.id, total=2))

    job = queue.submeter(reserva.id, _manifesto(reserva.id))
    assert job.estado is EstadoJobFacial.ENFILEIRADA
    assert job.manifesto is not None
    assert len(job.manifesto.capturas) == 3


def test_capacidade_cheia_retorna_503_sem_expor_detalhes() -> None:
    repository = RepositorioFilaFake()
    repository.limite_pendentes = 1
    queue = FilaFacial(repository, segredo=b"s" * 32, relogio=lambda: AGORA)
    prazo = AGORA + dt.timedelta(minutes=5)
    queue.reservar("presenca", "conta:12", "idem-1", prazo)

    with pytest.raises(FilaCheia) as erro:
        queue.reservar("presenca", "conta:13", "idem-2", prazo)

    assert erro.value.retry_after_seconds > 0


def test_fila_libera_lease_mas_preserva_reserva_entre_etapas() -> None:
    repository = RepositorioFilaFake()
    queue = FilaFacial(repository, segredo=b"s" * 32, relogio=lambda: AGORA)
    reservation = queue.reservar(
        "presenca", "conta:12", "desafio-1", AGORA + dt.timedelta(minutes=5)
    )
    job = replace(
        repository.jobs[reservation.id],
        tipo=TipoJobFacial.PRESENCA,
        estado=EstadoJobFacial.PROCESSANDO,
        lease="lease-privado",
        lease_expira_em=AGORA + dt.timedelta(minutes=2),
        manifesto=_manifesto(reservation.id, total=1),
    )
    repository.jobs[job.id] = job

    assert queue.aguardar_proxima_etapa(job)
    aguardando = repository.jobs[job.id]
    assert aguardando.estado is EstadoJobFacial.RECEBIDA
    assert aguardando.lease is None
    assert aguardando.manifesto is None
