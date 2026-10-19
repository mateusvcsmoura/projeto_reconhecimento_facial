"""Recebe uma unica etapa e a entrega ao worker serial existente."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from src.application.services.fila_facial import FilaFacial, ReservaInvalida
from src.domain.services.desafio_captura import DesafioCaptura, EstadoDesafio
from src.infrastructure.storage.temporary_capture_storage import TemporaryCaptureStorage


@dataclass(frozen=True, slots=True)
class CapturaRecebida:
    job_id: UUID
    etapa: int
    repetida: bool


class RepositorioRecebimentoCaptura(Protocol):
    def consultar_tentativa(
        self, tentativa_id: UUID, credencial_hash: str
    ) -> dict[str, object] | None: ...

    def registrar_captura(self, **kwargs: object) -> bool: ...

    def rejeitar_tentativa(
        self, tentativa_id: UUID, motivo: str, *, agora: datetime
    ) -> None: ...


class ReceberCaptura:
    def __init__(
        self,
        repositorio: RepositorioRecebimentoCaptura,
        desafios: DesafioCaptura,
        fila: FilaFacial,
        armazenamento: TemporaryCaptureStorage,
        *,
        max_bytes: int,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("O limite de bytes deve ser positivo.")
        self._repositorio = repositorio
        self._desafios = desafios
        self._fila = fila
        self._armazenamento = armazenamento
        self._max_bytes = max_bytes

    def executar(
        self,
        tentativa_id: UUID,
        credencial: str,
        *,
        nonce: str,
        etapa: int,
        conteudo: bytes,
        recebida_em_servidor: datetime,
    ) -> CapturaRecebida:
        instante = self._utc(recebida_em_servidor)
        if (
            not isinstance(credencial, str)
            or not credencial
            or len(credencial) > 256
            or not isinstance(conteudo, bytes)
            or not conteudo
            or len(conteudo) > self._max_bytes
            or isinstance(etapa, bool)
            or etapa not in (1, 2, 3)
        ):
            raise ValueError("A captura esta fora dos limites aceitos.")
        contexto = self._repositorio.consultar_tentativa(
            tentativa_id, hashlib.sha256(credencial.encode()).hexdigest()
        )
        if contexto is None:
            raise LookupError("Tentativa nao encontrada.")
        tentativa = contexto["tentativa"]
        recebimentos = contexto["recebimentos"]
        if not isinstance(recebimentos, int) or not hasattr(tentativa, "prazo_envio"):
            raise RuntimeError("O estado da tentativa esta inconsistente.")
        if instante > tentativa.prazo_envio:
            self._rejeitar(tentativa_id, credencial, instante, "prazo_expirado")
            raise TimeoutError("O prazo para envio foi encerrado.")
        resultado = self._desafios.registrar_etapa_recebida(
            tentativa_id, nonce, etapa, instante
        )
        repeticao_confirmada = (
            resultado.recebimento_repetido
            and resultado.estado is EstadoDesafio.AGUARDANDO_ETAPA
        )
        if (
            resultado.estado is not EstadoDesafio.ETAPA_RECEBIDA
            and not repeticao_confirmada
        ):
            self._rejeitar(
                tentativa_id,
                credencial,
                instante,
                resultado.motivo_tecnico or "desafio_recusado",
            )
            raise PermissionError("A etapa nao foi aceita.")
        try:
            nova = self._repositorio.registrar_captura(
                tentativa_id=tentativa_id,
                credencial_hash=hashlib.sha256(credencial.encode()).hexdigest(),
                ordinal=etapa,
                payload_hash=hashlib.sha256(conteudo).hexdigest(),
                recebida_em=instante,
            )
        except Exception:
            self._rejeitar(
                tentativa_id, credencial, instante, "captura_repetida_invalida"
            )
            raise
        if not nova:
            return CapturaRecebida(tentativa_id, etapa, True)
        try:
            self._armazenamento.salvar_captura(tentativa_id, etapa, conteudo)
            manifesto = self._armazenamento.manifesto(tentativa_id)
            self._fila.submeter(tentativa_id, manifesto)
        except (OSError, ValueError, ReservaInvalida, RuntimeError):
            self._rejeitar(tentativa_id, credencial, instante, "falha_ao_receber")
            self._fila.cancelar(tentativa_id, credencial)
            self._armazenamento.remover_job(tentativa_id)
            raise
        return CapturaRecebida(tentativa_id, etapa, False)

    def _rejeitar(
        self, tentativa_id: UUID, credencial: str, instante: datetime, motivo: str
    ) -> None:
        self._repositorio.rejeitar_tentativa(tentativa_id, motivo, agora=instante)
        self._fila.cancelar(tentativa_id, credencial)

    @staticmethod
    def _utc(instante: datetime) -> datetime:
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O instante recebido pelo servidor deve incluir fuso.")
        return instante.astimezone(UTC)
