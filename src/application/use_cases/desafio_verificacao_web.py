"""Orquestra uma tentativa privada através da fila única da task012.

O chamador deve fornecer ``aluno_id_autorizado`` somente depois de aplicar a
autorização do fluxo web responsável. Este caso de uso não trata matrícula
declarada como autenticação nem grava presença.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from src.application.services.fila_facial import (
    EstadoJobFacial,
    FilaFacial,
    ManifestoTemporario,
    TipoJobFacial,
)
from src.domain.services.desafio_captura import (
    ContextoDesafio,
    Desafio,
    DesafioCaptura,
    EstadoDesafio,
    ResultadoEtapaDesafio,
)
from src.infrastructure.repositories.postgres_solicitacao_repository import (
    ReferenciaAtiva,
)
from src.infrastructure.storage.temporary_capture_storage import (
    TemporaryCaptureStorage,
)


class LeitorReferenciasAtivas(Protocol):
    def obter_referencias_ativas(
        self, aluno_ids: tuple[int, ...] | None = None
    ) -> tuple[ReferenciaAtiva, ...]: ...


@dataclass(frozen=True, slots=True)
class DesafioEmitidoWeb:
    operacao_id: UUID
    credencial_operacao: str
    desafio: Desafio


@dataclass(frozen=True, slots=True)
class EtapaEnviadaWeb:
    operacao_id: UUID
    sequencia: int
    estado: str


class DesafioVerificacaoWeb:
    """Reserva a capacidade antes de publicar o nonce e recebe frames limitados."""

    def __init__(
        self,
        fila: FilaFacial,
        referencias: LeitorReferenciasAtivas,
        armazenamento: TemporaryCaptureStorage,
        desafio: DesafioCaptura,
        *,
        relogio: Callable[[], datetime],
    ) -> None:
        self._fila = fila
        self._referencias = referencias
        self._armazenamento = armazenamento
        self._desafio = desafio
        self._relogio = relogio

    def iniciar(
        self,
        *,
        aluno_id_autorizado: int,
        dono_id: str,
        idempotencia: str,
        prazo: datetime,
        agora: datetime,
        conjunto_id: int,
        versao_referencia: int,
    ) -> DesafioEmitidoWeb:
        instante = self._utc(agora)
        if aluno_id_autorizado <= 0:
            raise ValueError("O aluno autorizado é inválido.")
        ativos = self._referencias.obter_referencias_ativas((aluno_id_autorizado,))
        selecionadas = tuple(
            referencia
            for referencia in ativos
            if referencia.aluno_id == aluno_id_autorizado
            and referencia.conjunto_id == conjunto_id
            and referencia.versao == versao_referencia
        )
        if tuple(sorted(ref.ordinal for ref in selecionadas)) != (1, 2, 3):
            raise ValueError("A versão ativa não possui três referências exatas.")
        reserva = self._fila.reservar(
            TipoJobFacial.PRESENCA,
            dono_id,
            idempotencia,
            self._fila.limitar_prazo_reserva(prazo, agora=instante),
        )
        status = self._fila.consultar(reserva.id, reserva.credencial)
        if status.estado is not EstadoJobFacial.RECEBIDA:
            raise ValueError("A operação de verificação já foi iniciada ou encerrada.")
        desafio = self._desafio.emitir(
            ContextoDesafio(
                job_id=reserva.id,
                aluno_id=aluno_id_autorizado,
                conjunto_id=conjunto_id,
                versao_referencia=versao_referencia,
                prazo_recebimento=reserva.expira_em,
            ),
            instante,
        )
        return DesafioEmitidoWeb(
            operacao_id=reserva.id,
            credencial_operacao=reserva.credencial,
            desafio=desafio,
        )

    def submeter_etapa(
        self,
        operacao_id: UUID,
        credencial_operacao: str,
        nonce: str,
        sequencia: int,
        frame: bytes,
    ) -> EtapaEnviadaWeb | ResultadoEtapaDesafio:
        instante = self._utc(self._relogio())
        status = self._fila.consultar(operacao_id, credencial_operacao)
        if status.estado is not EstadoJobFacial.RECEBIDA:
            raise ValueError("A operação não está aguardando captura.")
        resultado = self._desafio.registrar_etapa_recebida(
            operacao_id, nonce, sequencia, instante
        )
        if resultado.recebimento_repetido:
            return EtapaEnviadaWeb(operacao_id, sequencia, resultado.estado.value)
        if resultado.estado is not EstadoDesafio.ETAPA_RECEBIDA:
            self._cancelar_e_limpar(operacao_id, credencial_operacao)
            return resultado
        try:
            self._armazenamento.salvar_captura(operacao_id, sequencia, frame)
            manifesto: ManifestoTemporario = self._armazenamento.manifesto(operacao_id)
            self._fila.submeter(operacao_id, manifesto)
        except (OSError, ValueError, RuntimeError):
            self._desafio.rejeitar(operacao_id, "captura_invalida", instante)
            self._cancelar_e_limpar(operacao_id, credencial_operacao)
            raise ValueError("A captura não foi aceita.") from None
        return EtapaEnviadaWeb(operacao_id, sequencia, "enfileirada")

    def _cancelar_e_limpar(self, operacao_id: UUID, credencial: str) -> None:
        self._fila.cancelar(operacao_id, credencial)
        self._armazenamento.remover_job(operacao_id)

    @staticmethod
    def _utc(valor: datetime) -> datetime:
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError("O instante deve conter fuso horário.")
        return valor.astimezone(UTC)
