"""Persistência PostgreSQL da fila facial, reserva, idempotência e leases."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import case, func, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.application.services.fila_facial import (
    ArquivoTemporario,
    EstadoJobFacial,
    FilaCheia,
    JobFacial,
    ManifestoTemporario,
    ReservaInvalida,
    TipoJobFacial,
)
from src.infrastructure.database import models

_LOCK_ADMISSAO = 0x4641434544494646
_LOCK_WORKER_UNICO = 0x464143454449574B
_ESTADOS_AGUARDANDO = (EstadoJobFacial.RECEBIDA, EstadoJobFacial.ENFILEIRADA)
_ESTADOS_OCUPAM_QUOTA = (
    EstadoJobFacial.RECEBIDA,
    EstadoJobFacial.ENFILEIRADA,
    EstadoJobFacial.PROCESSANDO,
)
_CODIGOS_RESULTADO = {
    "concluida",
    "recusa_biometrica",
    "falha_tecnica",
    "arquivo_ausente",
    "modelo_indisponivel",
    "tipo_nao_habilitado",
    "worker_reiniciado",
    "prazo_expirado",
    "cancelada",
}


class PostgresJobRepository:
    """Serializa admissão/claim com advisory lock transacional no PostgreSQL."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    @contextmanager
    def worker_unico(self) -> Iterator[bool]:
        """Mantém advisory session lock enquanto o processo executa inferência."""
        bind = self.session_factory.kw.get("bind")
        if not isinstance(bind, Engine):
            raise RuntimeError("O lock do worker exige uma engine PostgreSQL.")
        connection = bind.connect()
        adquirido = False
        try:
            adquirido = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": _LOCK_WORKER_UNICO},
                ).scalar_one()
            )
            connection.commit()
            yield adquirido
        finally:
            try:
                if adquirido:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:lock_id)"),
                        {"lock_id": _LOCK_WORKER_UNICO},
                    )
                    connection.commit()
            finally:
                connection.close()

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
    ) -> JobFacial:
        with self.session_factory() as session, session.begin():
            self._bloquear_admissao(session)
            self._expirar_aguardando(session, agora)
            existente = session.scalar(
                select(models.JobFacialWeb).where(
                    models.JobFacialWeb.dono_id == dono_id,
                    models.JobFacialWeb.tipo == tipo.value,
                    models.JobFacialWeb.idempotencia_hash == idempotencia_hash,
                )
            )
            if existente is not None:
                return self._para_job(existente)

            aguardando = session.scalar(
                select(func.count())
                .select_from(models.JobFacialWeb)
                .where(
                    models.JobFacialWeb.estado.in_(
                        [estado.value for estado in _ESTADOS_AGUARDANDO]
                    )
                )
            )
            bytes_em_uso = session.scalar(
                select(
                    func.coalesce(func.sum(models.JobFacialWeb.bytes_reservados), 0)
                ).where(
                    models.JobFacialWeb.estado.in_(
                        [estado.value for estado in _ESTADOS_OCUPAM_QUOTA]
                    )
                )
            )
            if int(aguardando or 0) >= limite_aguardando or (
                int(bytes_em_uso or 0) + bytes_reservados > quota_temporaria_bytes
            ):
                raise FilaCheia()

            registro = models.JobFacialWeb(
                id=job_id,
                dono_id=dono_id,
                tipo=tipo.value,
                estado=EstadoJobFacial.RECEBIDA.value,
                idempotencia_hash=idempotencia_hash,
                credencial_hash=credencial_hash,
                manifesto=None,
                bytes_reservados=bytes_reservados,
                prazo_reserva=prazo,
                prazo_execucao=prazo_execucao,
                criada_em=agora,
                atualizada_em=agora,
                enfileirada_em=None,
                iniciada_em=None,
                finalizada_em=None,
            )
            session.add(registro)
            session.flush()
            return self._para_job(registro)

    def consultar_reserva(self, job_id: UUID) -> JobFacial | None:
        with self.session_factory() as session:
            registro = session.get(models.JobFacialWeb, job_id)
            return self._para_job(registro) if registro is not None else None

    def submeter(
        self,
        reserva_id: UUID,
        manifesto: ManifestoTemporario,
        *,
        agora: datetime,
    ) -> JobFacial:
        indisponivel = False
        with self.session_factory() as session, session.begin():
            self._bloquear_admissao(session)
            registro = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == reserva_id)
                .with_for_update()
            )
            if (
                registro is None
                or registro.estado != EstadoJobFacial.RECEBIDA.value
                or registro.prazo_reserva < agora
            ):
                if (
                    registro is not None
                    and registro.estado == EstadoJobFacial.RECEBIDA.value
                ):
                    registro.estado = EstadoJobFacial.EXPIRADA.value
                    registro.resultado_codigo = "prazo_expirado"
                    registro.atualizada_em = agora
                    registro.finalizada_em = agora
                    self._atualizar_tentativa(
                        session,
                        reserva_id,
                        "expirada",
                        agora,
                        "prazo_expirado",
                    )
                indisponivel = True
            else:
                registro.manifesto = self._serializar_manifesto(manifesto)
                registro.estado = EstadoJobFacial.ENFILEIRADA.value
                registro.enfileirada_em = agora
                registro.atualizada_em = agora
                session.flush()
                self._atualizar_tentativa(session, reserva_id, "enfileirada", agora)
                job = self._para_job(registro)
        if indisponivel:
            raise ReservaInvalida("A reserva expirou ou já foi submetida.")
        return job

    def consultar_com_credencial(
        self, job_id: UUID, credencial_hash: str
    ) -> JobFacial | None:
        with self.session_factory() as session:
            registro = session.scalar(
                select(models.JobFacialWeb).where(
                    models.JobFacialWeb.id == job_id,
                    models.JobFacialWeb.credencial_hash == credencial_hash,
                )
            )
            return self._para_job(registro) if registro is not None else None

    def reivindicar(
        self, *, agora: datetime, duracao_lease: timedelta
    ) -> JobFacial | None:
        with self.session_factory() as session, session.begin():
            self._bloquear_admissao(session)
            self._expirar_aguardando(session, agora)
            ativo = session.scalar(
                select(models.JobFacialWeb.id)
                .where(models.JobFacialWeb.estado == EstadoJobFacial.PROCESSANDO.value)
                .limit(1)
            )
            if ativo is not None:
                return None
            registro = session.scalar(
                select(models.JobFacialWeb)
                .outerjoin(
                    models.DesafioVerificacaoWeb,
                    models.DesafioVerificacaoWeb.id == models.JobFacialWeb.id,
                )
                .where(
                    models.JobFacialWeb.estado == EstadoJobFacial.ENFILEIRADA.value,
                    models.JobFacialWeb.prazo_execucao > agora,
                )
                .order_by(
                    case(
                        (models.DesafioVerificacaoWeb.etapa_validada > 0, 0),
                        else_=1,
                    ),
                    models.JobFacialWeb.enfileirada_em,
                    models.JobFacialWeb.criada_em,
                    models.JobFacialWeb.id,
                )
                # O desafio entra por LEFT JOIN; bloquear todos os alvos faria
                # o PostgreSQL tentar aplicar FOR UPDATE ao lado anulável.
                .with_for_update(skip_locked=True, of=models.JobFacialWeb)
                .limit(1)
            )
            if registro is None:
                return None
            lease = secrets.token_urlsafe(32)
            registro.estado = EstadoJobFacial.PROCESSANDO.value
            registro.lease_hash = self._hash(lease)
            registro.lease_expira_em = agora + duracao_lease
            registro.iniciada_em = agora
            registro.atualizada_em = agora
            session.flush()
            self._atualizar_tentativa(session, registro.id, "processando", agora)
            return self._para_job(registro, lease=lease)

    def estender_lease(
        self,
        *,
        job_id: UUID,
        lease: str,
        agora: datetime,
        duracao_lease: timedelta,
    ) -> bool:
        with self.session_factory() as session, session.begin():
            registro = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == job_id)
                .with_for_update()
            )
            if not self._lease_valida(registro, lease, agora):
                return False
            assert registro is not None
            registro.lease_expira_em = agora + duracao_lease
            registro.atualizada_em = agora
            return True

    def finalizar(
        self,
        *,
        job_id: UUID,
        lease: str,
        sucesso: bool,
        codigo: str,
        agora: datetime,
    ) -> bool:
        resultado = codigo if codigo in _CODIGOS_RESULTADO else "falha_tecnica"
        with self.session_factory() as session, session.begin():
            registro = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == job_id)
                .with_for_update()
            )
            if not self._lease_valida(registro, lease, agora):
                return False
            assert registro is not None
            if registro.cancelamento_solicitado:
                registro.estado = EstadoJobFacial.CANCELADA.value
                registro.resultado_codigo = "cancelada"
            else:
                registro.estado = (
                    EstadoJobFacial.CONCLUIDA.value
                    if sucesso
                    else EstadoJobFacial.REJEITADA.value
                )
                registro.resultado_codigo = resultado
            registro.lease_hash = None
            registro.lease_expira_em = None
            registro.manifesto = None
            registro.atualizada_em = agora
            registro.finalizada_em = agora
            self._atualizar_tentativa(
                session,
                job_id,
                "concluida"
                if registro.estado == EstadoJobFacial.CONCLUIDA.value
                else "rejeitada",
                agora,
                registro.resultado_codigo,
            )
            return True

    def aguardar_proxima_etapa(
        self, *, job_id: UUID, lease: str, agora: datetime
    ) -> bool:
        """Retorna o mesmo job à reserva sem ocupar o slot singleton."""
        with self.session_factory() as session, session.begin():
            registro = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == job_id)
                .with_for_update()
            )
            if not self._lease_valida(registro, lease, agora):
                return False
            assert registro is not None
            if registro.cancelamento_solicitado:
                registro.estado = EstadoJobFacial.CANCELADA.value
                registro.resultado_codigo = "cancelada"
                registro.finalizada_em = agora
            elif registro.prazo_reserva <= agora or registro.prazo_execucao <= agora:
                registro.estado = EstadoJobFacial.EXPIRADA.value
                registro.resultado_codigo = "prazo_expirado"
                registro.finalizada_em = agora
            else:
                registro.estado = EstadoJobFacial.RECEBIDA.value
                registro.resultado_codigo = None
                registro.finalizada_em = None
            registro.lease_hash = None
            registro.lease_expira_em = None
            registro.manifesto = None
            registro.atualizada_em = agora
            aguardando = registro.estado == EstadoJobFacial.RECEBIDA.value
            self._atualizar_tentativa(
                session,
                job_id,
                "recebida"
                if aguardando
                else "expirada"
                if registro.estado == EstadoJobFacial.EXPIRADA.value
                else "rejeitada",
                agora,
                registro.resultado_codigo,
            )
            return aguardando

    def invalidar_apos_execucao(
        self, *, job_id: UUID, lease: str, agora: datetime
    ) -> bool:
        """Libera ativo expirado somente depois do retorno efetivo do executor."""
        with self.session_factory() as session, session.begin():
            registro = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == job_id)
                .with_for_update()
            )
            if (
                registro is None
                or registro.estado != EstadoJobFacial.PROCESSANDO.value
                or registro.lease_hash != self._hash(lease)
            ):
                return False
            registro.estado = EstadoJobFacial.REJEITADA.value
            registro.resultado_codigo = "prazo_expirado"
            registro.lease_hash = None
            registro.lease_expira_em = None
            registro.manifesto = None
            registro.atualizada_em = agora
            registro.finalizada_em = agora
            self._atualizar_tentativa(
                session, job_id, "expirada", agora, "prazo_expirado"
            )
            return True

    def recuperar_apos_reinicio(self, *, agora: datetime) -> set[UUID]:
        """Falha jobs ativos após o novo processo adquirir o lock singleton."""
        with self.session_factory() as session, session.begin():
            self._bloquear_admissao(session)
            registros = list(
                session.scalars(
                    select(models.JobFacialWeb)
                    .where(
                        models.JobFacialWeb.estado == EstadoJobFacial.PROCESSANDO.value
                    )
                    .with_for_update()
                )
            )
            ids = {registro.id for registro in registros}
            for registro in registros:
                registro.estado = EstadoJobFacial.REJEITADA.value
                registro.resultado_codigo = "worker_reiniciado"
                registro.lease_hash = None
                registro.lease_expira_em = None
                registro.manifesto = None
                registro.atualizada_em = agora
                registro.finalizada_em = agora
                self._atualizar_tentativa(
                    session, registro.id, "rejeitada", agora, "worker_reiniciado"
                )
            return ids

    def ids_com_temporarios(self) -> set[UUID]:
        with self.session_factory() as session:
            return set(
                session.scalars(
                    select(models.JobFacialWeb.id).where(
                        models.JobFacialWeb.estado.in_(
                            [
                                EstadoJobFacial.RECEBIDA.value,
                                EstadoJobFacial.ENFILEIRADA.value,
                                EstadoJobFacial.PROCESSANDO.value,
                            ]
                        )
                    )
                )
            )

    def cancelar(
        self,
        *,
        job_id: UUID,
        credencial_hash: str,
        agora: datetime,
    ) -> bool:
        with self.session_factory() as session, session.begin():
            registro = session.scalar(
                select(models.JobFacialWeb)
                .where(
                    models.JobFacialWeb.id == job_id,
                    models.JobFacialWeb.credencial_hash == credencial_hash,
                )
                .with_for_update()
            )
            if registro is None or registro.estado not in {
                EstadoJobFacial.RECEBIDA.value,
                EstadoJobFacial.ENFILEIRADA.value,
                EstadoJobFacial.PROCESSANDO.value,
            }:
                return False
            if registro.estado == EstadoJobFacial.PROCESSANDO.value:
                registro.cancelamento_solicitado = True
                self._atualizar_tentativa(
                    session, job_id, "rejeitada", agora, "cancelada"
                )
            else:
                registro.estado = EstadoJobFacial.CANCELADA.value
                registro.resultado_codigo = "cancelada"
                registro.manifesto = None
                registro.finalizada_em = agora
                self._atualizar_tentativa(
                    session, job_id, "rejeitada", agora, "cancelada"
                )
            registro.atualizada_em = agora
            return True

    def _expirar_aguardando(self, session: Session, agora: datetime) -> None:
        expiradas = tuple(
            session.scalars(
                select(models.JobFacialWeb.id).where(
                    models.JobFacialWeb.estado == EstadoJobFacial.RECEBIDA.value,
                    models.JobFacialWeb.prazo_reserva < agora,
                )
            )
        )
        session.execute(
            update(models.JobFacialWeb)
            .where(
                models.JobFacialWeb.estado == EstadoJobFacial.RECEBIDA.value,
                models.JobFacialWeb.prazo_reserva < agora,
            )
            .values(
                estado=EstadoJobFacial.EXPIRADA.value,
                resultado_codigo="prazo_expirado",
                atualizada_em=agora,
                finalizada_em=agora,
            )
        )
        for job_id in expiradas:
            self._atualizar_tentativa(
                session, job_id, "expirada", agora, "prazo_expirado"
            )
        expiradas_execucao = tuple(
            session.scalars(
                select(models.JobFacialWeb.id).where(
                    models.JobFacialWeb.estado == EstadoJobFacial.ENFILEIRADA.value,
                    models.JobFacialWeb.prazo_execucao <= agora,
                )
            )
        )
        session.execute(
            update(models.JobFacialWeb)
            .where(
                models.JobFacialWeb.estado == EstadoJobFacial.ENFILEIRADA.value,
                models.JobFacialWeb.prazo_execucao <= agora,
            )
            .values(
                estado=EstadoJobFacial.EXPIRADA.value,
                resultado_codigo="prazo_expirado",
                manifesto=None,
                atualizada_em=agora,
                finalizada_em=agora,
            )
        )
        for job_id in expiradas_execucao:
            self._atualizar_tentativa(
                session, job_id, "expirada", agora, "prazo_expirado"
            )

    @staticmethod
    def _atualizar_tentativa(
        session: Session,
        job_id: UUID,
        estado: str,
        agora: datetime,
        motivo: str | None = None,
    ) -> None:
        terminal = estado in {"concluida", "expirada", "rejeitada"}
        valores: dict[str, object] = {
            "estado": estado,
            "concluida_em": agora if terminal else None,
            "motivo_tecnico": motivo[:64] if terminal and motivo else None,
        }
        session.execute(
            update(models.TentativaPresencaWeb)
            .where(models.TentativaPresencaWeb.id == job_id)
            .where(
                models.TentativaPresencaWeb.estado.in_(
                    ["iniciada", "recebida", "enfileirada", "processando"]
                )
            )
            .values(**valores)
        )

    @staticmethod
    def _bloquear_admissao(session: Session) -> None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": _LOCK_ADMISSAO},
        )

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _lease_valida(
        self,
        registro: models.JobFacialWeb | None,
        lease: str,
        agora: datetime,
    ) -> bool:
        return bool(
            registro is not None
            and registro.estado == EstadoJobFacial.PROCESSANDO.value
            and registro.lease_hash == self._hash(lease)
            and registro.lease_expira_em is not None
            and registro.lease_expira_em > agora
            and registro.prazo_execucao > agora
        )

    def _para_job(
        self, registro: models.JobFacialWeb, *, lease: str | None = None
    ) -> JobFacial:
        return JobFacial(
            id=registro.id,
            dono_id=registro.dono_id,
            tipo=TipoJobFacial(registro.tipo),
            estado=EstadoJobFacial(registro.estado),
            criada_em=registro.criada_em,
            prazo=registro.prazo_reserva,
            prazo_execucao=registro.prazo_execucao,
            atualizada_em=registro.atualizada_em,
            manifesto=self._ler_manifesto(registro.id, registro.manifesto),
            lease=lease,
            lease_expira_em=registro.lease_expira_em,
            resultado_codigo=registro.resultado_codigo,
            credencial_hash=registro.credencial_hash,
            cancelamento_solicitado=registro.cancelamento_solicitado,
        )

    @staticmethod
    def _serializar_manifesto(
        manifesto: ManifestoTemporario,
    ) -> dict[str, object]:
        return {
            "capturas": [
                {
                    "ordinal": captura.ordinal,
                    "nome": captura.nome,
                    "tamanho_bytes": captura.tamanho_bytes,
                }
                for captura in manifesto.capturas
            ]
        }

    @staticmethod
    def _ler_manifesto(
        job_id: UUID, manifesto: dict[str, object] | None
    ) -> ManifestoTemporario | None:
        if manifesto is None:
            return None
        capturas = manifesto.get("capturas")
        if not isinstance(capturas, list):
            return None
        arquivos: list[ArquivoTemporario] = []
        for dado in capturas:
            if not isinstance(dado, dict):
                return None
            ordinal = dado.get("ordinal")
            nome = dado.get("nome")
            tamanho = dado.get("tamanho_bytes")
            if (
                isinstance(ordinal, bool)
                or not isinstance(ordinal, int)
                or not isinstance(nome, str)
                or isinstance(tamanho, bool)
                or not isinstance(tamanho, int)
            ):
                return None
            arquivos.append(ArquivoTemporario(ordinal, nome, tamanho))
        return ManifestoTemporario(job_id=job_id, capturas=tuple(arquivos))
