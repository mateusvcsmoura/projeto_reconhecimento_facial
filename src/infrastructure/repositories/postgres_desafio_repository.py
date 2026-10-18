"""Persistência do estado mínimo de desafio, sem guardar biometria."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from src.domain.services.desafio_captura import (
    DirecaoMovimento,
    EstadoDesafio,
    RegistroDesafio,
)
from src.infrastructure.database.models import DesafioVerificacaoWeb


def _utc(instante: datetime) -> datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("O instante persistido deve conter fuso horário.")
    return instante.astimezone(UTC)


class PostgresDesafioRepository:
    """Faz transições condicionais sob lock da linha do desafio."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def criar(self, registro: RegistroDesafio) -> RegistroDesafio:
        try:
            with self.session_factory() as session, session.begin():
                existente = session.get(DesafioVerificacaoWeb, registro.id)
                if existente is not None:
                    return self._para_registro(existente)
                linha = DesafioVerificacaoWeb(
                    id=registro.id,
                    aluno_id=registro.aluno_id,
                    conjunto_id=registro.conjunto_id,
                    versao_referencia=registro.versao_referencia,
                    nonce_hash=registro.nonce_hash,
                    direcao=registro.direcao.value,
                    expira_em=_utc(registro.expira_em),
                    etapa_validada=registro.etapa_validada,
                    etapa_recebida=registro.etapa_recebida,
                    estado=registro.estado.value,
                    atualizada_em=_utc(registro.atualizada_em),
                    motivo=registro.motivo,
                )
                session.add(linha)
                session.flush()
                return self._para_registro(linha)
        except IntegrityError:
            persistido = self.obter(registro.id)
            if persistido is None:
                raise
            return persistido

    def obter(self, desafio_id: UUID) -> RegistroDesafio | None:
        with self.session_factory() as session:
            linha = session.get(DesafioVerificacaoWeb, desafio_id)
            return self._para_registro(linha) if linha is not None else None

    def registrar_recebimento(
        self,
        desafio_id: UUID,
        sequencia: int,
        nonce_hash: str,
        agora: datetime,
    ) -> RegistroDesafio | None:
        instante = _utc(agora)
        with self.session_factory() as session, session.begin():
            linha = self._bloquear(session, desafio_id)
            if (
                linha is None
                or linha.estado != EstadoDesafio.AGUARDANDO_ETAPA.value
                or linha.etapa_recebida != linha.etapa_validada
                or sequencia != linha.etapa_validada + 1
                or nonce_hash != linha.nonce_hash
                or instante > _utc(linha.expira_em)
            ):
                return None
            linha.estado = EstadoDesafio.ETAPA_RECEBIDA.value
            linha.etapa_recebida = sequencia
            linha.atualizada_em = instante
            session.flush()
            return self._para_registro(linha)

    def validar_etapa(
        self,
        desafio_id: UUID,
        sequencia: int,
        *,
        aprovada: bool,
        motivo: str | None,
        agora: datetime,
    ) -> RegistroDesafio | None:
        instante = _utc(agora)
        with self.session_factory() as session, session.begin():
            linha = self._bloquear(session, desafio_id)
            if linha is None:
                return None
            if linha.estado != EstadoDesafio.ETAPA_RECEBIDA.value:
                return self._para_registro(linha)
            if (
                linha.etapa_recebida != sequencia
                or linha.etapa_validada + 1 != sequencia
            ):
                return self._para_registro(linha)
            if instante > _utc(linha.expira_em):
                linha.estado = EstadoDesafio.EXPIRADO.value
                linha.motivo = "desafio_expirado"
            elif not aprovada:
                linha.estado = EstadoDesafio.REJEITADO.value
                linha.motivo = motivo or "evidencia_recusada"
            else:
                linha.etapa_validada = sequencia
                linha.estado = (
                    EstadoDesafio.CONCLUIDO.value
                    if sequencia == 3
                    else EstadoDesafio.AGUARDANDO_ETAPA.value
                )
                linha.motivo = None
            linha.atualizada_em = instante
            session.flush()
            return self._para_registro(linha)

    def encerrar(
        self,
        desafio_id: UUID,
        estado: EstadoDesafio,
        *,
        motivo: str,
        agora: datetime,
    ) -> RegistroDesafio | None:
        if estado not in {EstadoDesafio.REJEITADO, EstadoDesafio.EXPIRADO}:
            raise ValueError("O encerramento exige estado terminal permitido.")
        instante = _utc(agora)
        with self.session_factory() as session, session.begin():
            linha = self._bloquear(session, desafio_id)
            if linha is None:
                return None
            if linha.estado not in {
                EstadoDesafio.CONCLUIDO.value,
                EstadoDesafio.REJEITADO.value,
                EstadoDesafio.EXPIRADO.value,
            }:
                linha.estado = estado.value
                linha.motivo = motivo
                linha.atualizada_em = instante
                session.flush()
            return self._para_registro(linha)

    @staticmethod
    def _bloquear(session: Session, desafio_id: UUID) -> DesafioVerificacaoWeb | None:
        return session.scalar(
            select(DesafioVerificacaoWeb)
            .where(DesafioVerificacaoWeb.id == desafio_id)
            .with_for_update()
        )

    @staticmethod
    def _para_registro(linha: DesafioVerificacaoWeb) -> RegistroDesafio:
        return RegistroDesafio(
            id=linha.id,
            aluno_id=linha.aluno_id,
            conjunto_id=linha.conjunto_id,
            versao_referencia=linha.versao_referencia,
            nonce_hash=linha.nonce_hash,
            direcao=DirecaoMovimento(linha.direcao),
            expira_em=_utc(linha.expira_em),
            etapa_validada=linha.etapa_validada,
            etapa_recebida=linha.etapa_recebida,
            estado=EstadoDesafio(linha.estado),
            atualizada_em=_utc(linha.atualizada_em),
            motivo=linha.motivo,
        )
