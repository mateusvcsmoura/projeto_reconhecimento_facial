"""Contrato de reserva e acompanhamento dos trabalhos faciais web."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4


class TipoJobFacial(StrEnum):
    CADASTRO = "cadastro"
    PRESENCA = "presenca"


class EstadoJobFacial(StrEnum):
    RECEBIDA = "recebida"
    ENFILEIRADA = "enfileirada"
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    REJEITADA = "rejeitada"
    CANCELADA = "cancelada"
    EXPIRADA = "expirada"


@dataclass(frozen=True)
class ArquivoTemporario:
    ordinal: int
    nome: str
    tamanho_bytes: int


@dataclass(frozen=True)
class ManifestoTemporario:
    job_id: UUID
    capturas: tuple[ArquivoTemporario, ...]


@dataclass(frozen=True)
class JobFacial:
    id: UUID
    dono_id: str
    tipo: TipoJobFacial
    estado: EstadoJobFacial
    criada_em: datetime
    prazo: datetime
    prazo_execucao: datetime
    atualizada_em: datetime
    manifesto: ManifestoTemporario | None
    lease: str | None
    lease_expira_em: datetime | None
    resultado_codigo: str | None
    credencial_hash: str
    cancelamento_solicitado: bool = False


@dataclass(frozen=True)
class ReservaFacial:
    id: UUID
    credencial: str
    expira_em: datetime


@dataclass(frozen=True)
class StatusOperacao:
    id: UUID
    estado: EstadoJobFacial
    criada_em: datetime
    atualizada_em: datetime
    codigo: str | None


class FilaCheia(RuntimeError):
    """A fila ou a quota temporária atingiu o limite configurado."""

    def __init__(self, retry_after_seconds: int = 5) -> None:
        super().__init__("A fila facial está temporariamente cheia.")
        self.retry_after_seconds = max(1, retry_after_seconds)


class ReservaInvalida(RuntimeError):
    """A reserva não existe, expirou ou já foi submetida."""


class LeaseInvalida(RuntimeError):
    """O worker não possui mais um lease válido para este trabalho."""


class OperacaoNaoEncontrada(RuntimeError):
    """A operação não existe ou não pertence à credencial informada."""


class RepositorioFilaFacial(Protocol):
    def reservar(
        self,
        *,
        job_id: UUID,
        tipo: TipoJobFacial,
        dono_id: str,
        idempotencia_hash: str,
        credencial_hash: str,
        prazo: datetime,
        prazo_execucao: datetime,
        bytes_reservados: int,
        limite_aguardando: int,
        quota_temporaria_bytes: int,
        agora: datetime,
    ) -> JobFacial: ...

    def submeter(
        self,
        reserva_id: UUID,
        manifesto: ManifestoTemporario,
        *,
        agora: datetime,
    ) -> JobFacial: ...

    def consultar_com_credencial(
        self, job_id: UUID, credencial_hash: str
    ) -> JobFacial | None: ...

    def consultar_reserva(self, job_id: UUID) -> JobFacial | None: ...

    def reivindicar(
        self, *, agora: datetime, duracao_lease: timedelta
    ) -> JobFacial | None: ...

    def estender_lease(
        self,
        *,
        job_id: UUID,
        lease: str,
        agora: datetime,
        duracao_lease: timedelta,
    ) -> bool: ...

    def finalizar(
        self,
        *,
        job_id: UUID,
        lease: str,
        sucesso: bool,
        codigo: str,
        agora: datetime,
    ) -> bool: ...

    def invalidar_apos_execucao(
        self, *, job_id: UUID, lease: str, agora: datetime
    ) -> bool: ...

    def recuperar_apos_reinicio(self, *, agora: datetime) -> set[UUID]: ...

    def ids_com_temporarios(self) -> set[UUID]: ...

    def cancelar(
        self, *, job_id: UUID, credencial_hash: str, agora: datetime
    ) -> bool: ...


def _normalizar_instante(valor: datetime) -> datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("O instante deve conter fuso horário.")
    return valor.astimezone(UTC)


class FilaFacial:
    """Valida a entrada de jobs antes de delegar a admissão ao PostgreSQL."""

    def __init__(
        self,
        repositorio: RepositorioFilaFacial,
        *,
        segredo: bytes,
        relogio: Callable[[], datetime],
        limite_aguardando: int = 10,
        quota_temporaria_bytes: int = 300 * 1024 * 1024,
        max_bytes_por_captura: int = 8 * 1024 * 1024,
        max_capturas: int = 3,
        prazo_maximo_reserva: timedelta = timedelta(minutes=5),
        prazo_maximo_execucao: timedelta = timedelta(minutes=15),
        duracao_lease: timedelta = timedelta(minutes=2),
    ) -> None:
        if len(segredo) < 32:
            raise ValueError("O segredo da fila deve conter ao menos 32 bytes.")
        if limite_aguardando < 1 or max_capturas != 3:
            raise ValueError("Os limites de fila/captura são inválidos.")
        if max_bytes_por_captura < 1 or quota_temporaria_bytes < 1:
            raise ValueError("A quota temporária deve ser positiva.")
        if prazo_maximo_execucao <= timedelta(0) or duracao_lease <= timedelta(0):
            raise ValueError("Os prazos de execução devem ser positivos.")
        if quota_temporaria_bytes < max_bytes_por_captura * max_capturas:
            raise ValueError("A quota deve reservar espaço para um job completo.")
        self._repositorio = repositorio
        self._segredo = segredo
        self._relogio = relogio
        self._limite_aguardando = limite_aguardando
        self._quota_temporaria_bytes = quota_temporaria_bytes
        self._max_bytes_por_captura = max_bytes_por_captura
        self._max_capturas = max_capturas
        self._prazo_maximo_reserva = prazo_maximo_reserva
        self._prazo_maximo_execucao = prazo_maximo_execucao
        self._duracao_lease = duracao_lease

    def reservar(
        self,
        tipo: TipoJobFacial | str,
        dono_id: str,
        idempotencia: str,
        prazo: datetime,
    ) -> ReservaFacial:
        try:
            tipo_job = TipoJobFacial(tipo)
        except (TypeError, ValueError) as exc:
            raise ValueError("O tipo de job facial não é permitido.") from exc

        dono = dono_id.strip()
        chave = idempotencia.strip()
        if not dono or len(dono) > 128:
            raise ValueError("O proprietário do job é inválido.")
        if not chave or len(chave) > 256:
            raise ValueError("A chave de idempotência é inválida.")

        agora = _normalizar_instante(self._relogio())
        expira_em = _normalizar_instante(prazo)
        if expira_em <= agora or expira_em > agora + self._prazo_maximo_reserva:
            raise ValueError("O prazo da reserva é inválido.")

        idempotencia_hash = hmac.new(
            self._segredo,
            f"idempotencia:{dono}:{tipo_job.value}:{chave}".encode(),
            hashlib.sha256,
        ).hexdigest()
        novo_id = uuid4()
        credencial = self._credencial_para(novo_id)
        job = self._repositorio.reservar(
            job_id=novo_id,
            tipo=tipo_job,
            dono_id=dono,
            idempotencia_hash=idempotencia_hash,
            credencial_hash=hashlib.sha256(credencial.encode()).hexdigest(),
            prazo=expira_em,
            bytes_reservados=self._max_bytes_por_captura * self._max_capturas,
            limite_aguardando=self._limite_aguardando,
            quota_temporaria_bytes=self._quota_temporaria_bytes,
            prazo_execucao=agora + self._prazo_maximo_execucao,
            agora=agora,
        )
        return ReservaFacial(
            id=job.id,
            credencial=self._credencial_para(job.id),
            expira_em=job.prazo,
        )

    def submeter(
        self, reserva_id: UUID, manifesto_temporario: ManifestoTemporario
    ) -> JobFacial:
        if manifesto_temporario.job_id != reserva_id:
            raise ValueError("O manifesto não corresponde à reserva.")
        job = self._repositorio.consultar_reserva(reserva_id)  # type: ignore[attr-defined]
        agora = _normalizar_instante(self._relogio())
        if (
            job is None
            or job.estado is not EstadoJobFacial.RECEBIDA
            or job.prazo <= agora
        ):
            raise ReservaInvalida("A reserva não está disponível.")
        self._validar_manifesto(job.tipo, manifesto_temporario)
        return self._repositorio.submeter(
            reserva_id,
            manifesto_temporario,
            agora=agora,
        )

    def reivindicar(self) -> JobFacial | None:
        return self._repositorio.reivindicar(
            agora=_normalizar_instante(self._relogio()),
            duracao_lease=self._duracao_lease,
        )

    def heartbeat(self, job: JobFacial) -> bool:
        if job.lease is None:
            raise LeaseInvalida()
        return self._repositorio.estender_lease(
            job_id=job.id,
            lease=job.lease,
            agora=_normalizar_instante(self._relogio()),
            duracao_lease=self._duracao_lease,
        )

    def finalizar(self, job: JobFacial, *, sucesso: bool, codigo: str) -> bool:
        if job.lease is None:
            raise LeaseInvalida()
        return self._repositorio.finalizar(
            job_id=job.id,
            lease=job.lease,
            sucesso=sucesso,
            codigo=codigo,
            agora=_normalizar_instante(self._relogio()),
        )

    def invalidar_apos_execucao(self, job: JobFacial) -> bool:
        if job.lease is None:
            return False
        return self._repositorio.invalidar_apos_execucao(
            job_id=job.id,
            lease=job.lease,
            agora=_normalizar_instante(self._relogio()),
        )

    def recuperar_apos_reinicio(self) -> set[UUID]:
        return self._repositorio.recuperar_apos_reinicio(
            agora=_normalizar_instante(self._relogio())
        )

    def ids_com_temporarios(self) -> set[UUID]:
        return self._repositorio.ids_com_temporarios()

    def cancelar(self, job_id: UUID, credencial: str) -> bool:
        if not credencial or len(credencial) > 256:
            return False
        return self._repositorio.cancelar(
            job_id=job_id,
            credencial_hash=hashlib.sha256(credencial.encode()).hexdigest(),
            agora=_normalizar_instante(self._relogio()),
        )

    def consultar(self, job_id: UUID, credencial: str) -> StatusOperacao:
        if not credencial or len(credencial) > 256:
            raise OperacaoNaoEncontrada()
        digest = hashlib.sha256(credencial.encode()).hexdigest()
        job = self._repositorio.consultar_com_credencial(job_id, digest)
        if job is None:
            raise OperacaoNaoEncontrada()
        publico = (
            EstadoJobFacial.REJEITADA
            if job.estado in (EstadoJobFacial.CANCELADA, EstadoJobFacial.EXPIRADA)
            else job.estado
        )
        return StatusOperacao(
            id=job.id,
            estado=publico,
            criada_em=job.criada_em,
            atualizada_em=job.atualizada_em,
            codigo=job.resultado_codigo,
        )

    def _credencial_para(self, job_id: UUID) -> str:
        return hmac.new(
            self._segredo,
            b"operacao-web:" + job_id.bytes,
            hashlib.sha256,
        ).hexdigest()

    def _validar_manifesto(
        self, tipo: TipoJobFacial, manifesto: ManifestoTemporario
    ) -> None:
        capturas = manifesto.capturas
        if not capturas or len(capturas) > self._max_capturas:
            raise ValueError("O manifesto excede o limite de capturas.")
        if tipo is TipoJobFacial.CADASTRO and len(capturas) != 3:
            raise ValueError("Cadastro web exige três capturas.")
        ordinais: set[int] = set()
        total = 0
        for captura in capturas:
            if (
                captura.ordinal not in range(1, self._max_capturas + 1)
                or captura.ordinal in ordinais
                or re.fullmatch(rf"captura-{captura.ordinal}\.bin", captura.nome)
                is None
                or captura.tamanho_bytes < 1
                or captura.tamanho_bytes > self._max_bytes_por_captura
            ):
                raise ValueError("O manifesto temporário é inválido.")
            ordinais.add(captura.ordinal)
            total += captura.tamanho_bytes
        if total > self._max_bytes_por_captura * self._max_capturas:
            raise ValueError("O manifesto temporário excede a quota do job.")
