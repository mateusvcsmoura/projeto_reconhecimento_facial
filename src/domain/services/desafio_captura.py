"""Protocolo de desafio facial com estado controlado no servidor.

O nonce bruto só é entregue ao cliente na emissão. A persistência recebe o hash;
o worker envia à regra apenas evidências produzidas no backend.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class DirecaoMovimento(StrEnum):
    ESQUERDA = "esquerda"
    DIREITA = "direita"


class OrientacaoPose(StrEnum):
    FRENTE = "frente"
    ESQUERDA = "esquerda"
    DIREITA = "direita"
    INDETERMINADA = "indeterminada"
    AUSENTE = "ausente"
    MULTIPLOS = "multiplos"


class EstadoDesafio(StrEnum):
    AGUARDANDO_ETAPA = "aguardando_etapa"
    ETAPA_RECEBIDA = "etapa_recebida"
    CONCLUIDO = "concluido"
    REJEITADO = "rejeitado"
    EXPIRADO = "expirado"


@dataclass(frozen=True, slots=True)
class ContextoDesafio:
    """Alvo fechado e reserva já criada na fila única task012."""

    job_id: UUID
    aluno_id: int
    conjunto_id: int
    versao_referencia: int
    prazo_recebimento: datetime


@dataclass(frozen=True, slots=True)
class RegistroDesafio:
    """Estado mínimo persistível; não guarda frames, pontos ou embeddings."""

    id: UUID
    aluno_id: int
    conjunto_id: int
    versao_referencia: int
    nonce_hash: str
    direcao: DirecaoMovimento
    expira_em: datetime
    etapa_validada: int
    etapa_recebida: int
    estado: EstadoDesafio
    atualizada_em: datetime
    motivo: str | None = None


@dataclass(frozen=True, slots=True)
class Desafio:
    id: UUID
    nonce: str
    direcao: DirecaoMovimento
    primeira_orientacao: OrientacaoPose
    expira_em: datetime
    proxima_etapa: int


@dataclass(frozen=True, slots=True)
class EvidenciaEtapa:
    """Evidência interna calculada pelo worker; nunca aceita ``desafio_ok``."""

    quantidade_rostos: int
    orientacao: OrientacaoPose
    identidade_ok: bool
    qualidade_ok: bool
    antispoofing_ok: bool
    versao_referencia: int


@dataclass(frozen=True, slots=True)
class ResultadoEtapaDesafio:
    id: UUID
    estado: EstadoDesafio
    etapa_validada: int
    proxima_etapa: int | None
    proxima_orientacao: OrientacaoPose | None
    desafio_ok: bool
    motivo_tecnico: str | None
    recebimento_repetido: bool = False


class RepositorioDesafio(Protocol):
    def criar(self, registro: RegistroDesafio) -> RegistroDesafio: ...

    def obter(self, desafio_id: UUID) -> RegistroDesafio | None: ...

    def registrar_recebimento(
        self,
        desafio_id: UUID,
        sequencia: int,
        nonce_hash: str,
        agora: datetime,
    ) -> RegistroDesafio | None: ...

    def validar_etapa(
        self,
        desafio_id: UUID,
        sequencia: int,
        *,
        aprovada: bool,
        motivo: str | None,
        agora: datetime,
    ) -> RegistroDesafio | None: ...

    def encerrar(
        self,
        desafio_id: UUID,
        estado: EstadoDesafio,
        *,
        motivo: str,
        agora: datetime,
    ) -> RegistroDesafio | None: ...


def _utc(instante: datetime) -> datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("O instante deve conter fuso horário.")
    return instante.astimezone(UTC)


class DesafioCaptura:
    """Emite e valida etapas; cada transição é persistida pelo repositório."""

    DURACAO_PADRAO = timedelta(seconds=120)

    def __init__(
        self,
        repositorio: RepositorioDesafio,
        *,
        segredo: bytes,
        duracao: timedelta = DURACAO_PADRAO,
        escolher_direcao: Callable[
            [tuple[DirecaoMovimento, ...]], DirecaoMovimento
        ] = secrets.choice,
    ) -> None:
        if len(segredo) < 32:
            raise ValueError("O segredo do desafio deve conter ao menos 32 bytes.")
        if duracao <= timedelta(0):
            raise ValueError("A duração do desafio deve ser positiva.")
        self._repositorio = repositorio
        self._segredo = segredo
        self._duracao = duracao
        self._escolher_direcao = escolher_direcao

    def emitir(self, contexto: ContextoDesafio, agora: datetime) -> Desafio:
        instante = _utc(agora)
        prazo = _utc(contexto.prazo_recebimento)
        if (
            contexto.aluno_id <= 0
            or contexto.conjunto_id <= 0
            or contexto.versao_referencia <= 0
            or prazo <= instante
        ):
            raise ValueError("O contexto ou prazo do desafio é inválido.")

        expiracao = min(instante + self._duracao, prazo)
        nonce = self._nonce(contexto.job_id)
        direcao = self._escolher_direcao(
            (DirecaoMovimento.ESQUERDA, DirecaoMovimento.DIREITA)
        )
        registro = RegistroDesafio(
            id=contexto.job_id,
            aluno_id=contexto.aluno_id,
            conjunto_id=contexto.conjunto_id,
            versao_referencia=contexto.versao_referencia,
            nonce_hash=hashlib.sha256(nonce.encode()).hexdigest(),
            direcao=direcao,
            expira_em=expiracao,
            etapa_validada=0,
            etapa_recebida=0,
            estado=EstadoDesafio.AGUARDANDO_ETAPA,
            atualizada_em=instante,
        )
        persistido = self._repositorio.criar(registro)
        if (
            persistido.nonce_hash != registro.nonce_hash
            or persistido.aluno_id != contexto.aluno_id
            or persistido.conjunto_id != contexto.conjunto_id
            or persistido.versao_referencia != contexto.versao_referencia
        ):
            raise ValueError("A reserva já está ligada a outro desafio.")
        if (
            persistido.estado is not EstadoDesafio.AGUARDANDO_ETAPA
            or persistido.etapa_recebida != persistido.etapa_validada
            or _utc(persistido.expira_em) <= instante
        ):
            raise ValueError("O desafio já foi iniciado ou expirou.")
        return Desafio(
            id=persistido.id,
            nonce=nonce,
            direcao=persistido.direcao,
            primeira_orientacao=OrientacaoPose.FRENTE,
            expira_em=persistido.expira_em,
            proxima_etapa=persistido.etapa_validada + 1,
        )

    def registrar_etapa_recebida(
        self, desafio_id: UUID, nonce: str, sequencia: int, agora: datetime
    ) -> ResultadoEtapaDesafio:
        instante = _utc(agora)
        registro = self._repositorio.obter(desafio_id)
        if registro is None:
            return self._resultado_desconhecido(desafio_id)
        if registro.estado in (
            EstadoDesafio.CONCLUIDO,
            EstadoDesafio.REJEITADO,
            EstadoDesafio.EXPIRADO,
        ):
            return self._resultado(registro)
        if instante > registro.expira_em:
            return self._encerrar(
                desafio_id, EstadoDesafio.EXPIRADO, "desafio_expirado", instante
            )
        if not isinstance(nonce, str) or not hmac.compare_digest(
            hashlib.sha256(nonce.encode()).hexdigest(), registro.nonce_hash
        ):
            return self._encerrar(
                desafio_id, EstadoDesafio.REJEITADO, "nonce_invalido", instante
            )
        if self._etapa_ja_recebida(registro, sequencia):
            return self._resultado(registro, recebimento_repetido=True)
        if (
            isinstance(sequencia, bool)
            or not isinstance(sequencia, int)
            or sequencia not in (1, 2, 3)
            or registro.estado is not EstadoDesafio.AGUARDANDO_ETAPA
            or registro.etapa_recebida != registro.etapa_validada
            or sequencia != registro.etapa_validada + 1
        ):
            return self._encerrar(
                desafio_id, EstadoDesafio.REJEITADO, "protocolo_invalido", instante
            )
        atualizado = self._repositorio.registrar_recebimento(
            desafio_id,
            sequencia,
            registro.nonce_hash,
            instante,
        )
        if atualizado is None:
            atual = self._repositorio.obter(desafio_id)
            if (
                atual is not None
                and hmac.compare_digest(
                    hashlib.sha256(nonce.encode()).hexdigest(), atual.nonce_hash
                )
                and self._etapa_ja_recebida(atual, sequencia)
            ):
                return self._resultado(atual, recebimento_repetido=True)
            return (
                self._resultado(atual)
                if atual
                else self._resultado_desconhecido(desafio_id)
            )
        return self._resultado(atualizado)

    def rejeitar(
        self, desafio_id: UUID, motivo: str, agora: datetime
    ) -> ResultadoEtapaDesafio:
        """Encerra uma tentativa quando a aceitação do frame falha no backend."""
        codigo = motivo.strip()
        if not codigo or len(codigo) > 64 or not codigo.replace("_", "").isalnum():
            raise ValueError("O motivo técnico do encerramento é inválido.")
        return self._encerrar(
            desafio_id,
            EstadoDesafio.REJEITADO,
            codigo,
            _utc(agora),
        )

    def validar_etapa(
        self,
        desafio_id: UUID,
        sequencia: int,
        evidencias: EvidenciaEtapa,
        agora: datetime,
    ) -> ResultadoEtapaDesafio:
        instante = _utc(agora)
        registro = self._repositorio.obter(desafio_id)
        if registro is None:
            return self._resultado_desconhecido(desafio_id)
        if registro.estado in (
            EstadoDesafio.CONCLUIDO,
            EstadoDesafio.REJEITADO,
            EstadoDesafio.EXPIRADO,
        ):
            return self._resultado(registro)
        if instante > registro.expira_em:
            return self._encerrar(
                desafio_id, EstadoDesafio.EXPIRADO, "desafio_expirado", instante
            )
        if (
            isinstance(sequencia, bool)
            or not isinstance(sequencia, int)
            or sequencia not in (1, 2, 3)
            or registro.estado is not EstadoDesafio.ETAPA_RECEBIDA
            or registro.etapa_recebida != sequencia
            or registro.etapa_validada + 1 != sequencia
        ):
            return self._encerrar(
                desafio_id, EstadoDesafio.REJEITADO, "protocolo_invalido", instante
            )

        motivo = self._motivo_recusa(registro, sequencia, evidencias)
        atualizado = self._repositorio.validar_etapa(
            desafio_id,
            sequencia,
            aprovada=motivo is None,
            motivo=motivo,
            agora=instante,
        )
        if atualizado is None:
            return self._resultado_atual(desafio_id)
        return self._resultado(atualizado)

    def _motivo_recusa(
        self,
        registro: RegistroDesafio,
        sequencia: int,
        evidencia: EvidenciaEtapa,
    ) -> str | None:
        if not isinstance(evidencia, EvidenciaEtapa):
            return "evidencia_invalida"
        if (
            type(evidencia.quantidade_rostos) is not int
            or evidencia.quantidade_rostos != 1
            or isinstance(evidencia.versao_referencia, bool)
            or not isinstance(evidencia.versao_referencia, int)
            or evidencia.versao_referencia != registro.versao_referencia
            or any(
                type(valor) is not bool
                for valor in (
                    evidencia.identidade_ok,
                    evidencia.qualidade_ok,
                    evidencia.antispoofing_ok,
                )
            )
        ):
            return "evidencia_invalida"
        if not evidencia.identidade_ok:
            return "identidade_nao_confirmada"
        if not evidencia.qualidade_ok:
            return "qualidade_insuficiente"
        if not evidencia.antispoofing_ok:
            return "antispoofing_recusado"
        esperado = (
            OrientacaoPose.FRENTE
            if sequencia in (1, 3)
            else OrientacaoPose(self._orientacao_movimento(registro.direcao))
        )
        if evidencia.orientacao is not esperado:
            return "movimento_nao_confirmado"
        return None

    @staticmethod
    def _orientacao_movimento(direcao: DirecaoMovimento) -> str:
        return direcao.value

    def _nonce(self, job_id: UUID) -> str:
        return hmac.new(
            self._segredo,
            b"desafio-captura:" + job_id.bytes,
            hashlib.sha256,
        ).hexdigest()

    def _encerrar(
        self,
        desafio_id: UUID,
        estado: EstadoDesafio,
        motivo: str,
        agora: datetime,
    ) -> ResultadoEtapaDesafio:
        registro = self._repositorio.encerrar(
            desafio_id, estado, motivo=motivo, agora=agora
        )
        return (
            self._resultado(registro)
            if registro
            else self._resultado_desconhecido(desafio_id)
        )

    def _resultado_atual(self, desafio_id: UUID) -> ResultadoEtapaDesafio:
        registro = self._repositorio.obter(desafio_id)
        return (
            self._resultado(registro)
            if registro
            else self._resultado_desconhecido(desafio_id)
        )

    @staticmethod
    def _etapa_ja_recebida(registro: RegistroDesafio, sequencia: object) -> bool:
        if (
            isinstance(sequencia, bool)
            or not isinstance(sequencia, int)
            or sequencia not in (1, 2, 3)
        ):
            return False
        return sequencia <= registro.etapa_validada or (
            registro.estado is EstadoDesafio.ETAPA_RECEBIDA
            and registro.etapa_recebida == sequencia
            and sequencia == registro.etapa_validada + 1
        )

    @staticmethod
    def _resultado_desconhecido(desafio_id: UUID) -> ResultadoEtapaDesafio:
        return ResultadoEtapaDesafio(
            id=desafio_id,
            estado=EstadoDesafio.REJEITADO,
            etapa_validada=0,
            proxima_etapa=None,
            proxima_orientacao=None,
            desafio_ok=False,
            motivo_tecnico="desafio_indisponivel",
        )

    @staticmethod
    def _resultado(
        registro: RegistroDesafio, *, recebimento_repetido: bool = False
    ) -> ResultadoEtapaDesafio:
        concluido = registro.estado is EstadoDesafio.CONCLUIDO
        if registro.estado is EstadoDesafio.AGUARDANDO_ETAPA:
            proxima_etapa = registro.etapa_validada + 1
            if proxima_etapa == 1:
                orientacao = OrientacaoPose.FRENTE
            elif proxima_etapa == 2:
                orientacao = OrientacaoPose(registro.direcao.value)
            else:
                orientacao = OrientacaoPose.FRENTE
        else:
            proxima_etapa = None
            orientacao = None
        return ResultadoEtapaDesafio(
            id=registro.id,
            estado=registro.estado,
            etapa_validada=registro.etapa_validada,
            proxima_etapa=proxima_etapa,
            proxima_orientacao=orientacao,
            desafio_ok=concluido,
            motivo_tecnico=registro.motivo,
            recebimento_repetido=recebimento_repetido,
        )
