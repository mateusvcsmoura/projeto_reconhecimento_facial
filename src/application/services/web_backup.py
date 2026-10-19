"""Orquestra backup, transporte, ensaio de restauração e expurgo web."""

from __future__ import annotations

import re
from contextlib import AbstractContextManager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol

ModoBackup = Literal["diario", "manual_pre_apresentacao"]


class ChaveBackupAusente(RuntimeError):
    """A configuração de criptografia não contém a chave necessária."""


@dataclass(frozen=True, slots=True)
class ArquivoManifestoBackup:
    caminho: str
    tamanho_bytes: int
    sha256: str
    restaurar_em: str | None = None


@dataclass(frozen=True, slots=True)
class ManifestoBackup:
    geracao: str
    criado_em: datetime
    modo: str
    versao_aplicacao: str
    revisao_schema: str
    arquivos: tuple[ArquivoManifestoBackup, ...]

    @property
    def tamanho_total_bytes(self) -> int:
        return sum(arquivo.tamanho_bytes for arquivo in self.arquivos)


@dataclass(frozen=True, slots=True)
class ResultadoVerificado:
    geracao: str
    destino: str
    tamanho_bytes: int
    sha256: str
    verificado_em: datetime


@dataclass(frozen=True, slots=True)
class AutorizacaoRestore:
    banco: str
    confirmacao: str

    def exigir_alvo(self, banco: str) -> None:
        esperado = f"RESTAURAR-TASK017-{banco}"
        if self.banco != banco or self.confirmacao != esperado:
            raise ValueError(
                "A restauração exige confirmação explícita do banco descartável."
            )


@dataclass(frozen=True, slots=True)
class EvidenciaRestore:
    geracao: str
    banco: str
    revisao_schema: str
    arquivos_verificados: int
    exclusoes_reaplicadas: int
    sessoes_tokens_invalidos: int
    validado_em: datetime


@dataclass(frozen=True, slots=True)
class PlanoExpurgo:
    ambiente: str
    alvo: str
    planejado_em: datetime
    finalidade_ate: datetime
    finalidade_encerrada: bool
    alvos: tuple[str, ...]

    @property
    def quantidade_alvos(self) -> int:
        return len(self.alvos)


@dataclass(frozen=True, slots=True)
class ResultadoExpurgo:
    ambiente: str
    alvo: str
    finalidade_encerrada: bool
    removidos: tuple[str, ...]


class CoordenacaoBackup(Protocol):
    def lock_backup(self) -> AbstractContextManager[None]: ...

    def solicitar_manutencao(self) -> None: ...

    def aguardar_jobs_ociosos(self, timeout_seconds: float) -> None: ...

    def lock_snapshot(self, timeout_seconds: float) -> AbstractContextManager[None]: ...

    def criar_staging(self, generation_id: str) -> Path: ...

    def criar_snapshot(
        self,
        staging: Path,
        generation_id: str,
        agora: datetime,
        modo: ModoBackup,
    ) -> ManifestoBackup: ...

    def limpar_staging(self, staging: Path) -> None: ...

    def liberar_manutencao(self) -> None: ...


class CifraBackup(Protocol):
    def cifrar(self, staging: Path, destino: str, geracao: str) -> None: ...

    def verificar(self, staging: Path, destino: str, geracao: str) -> None: ...

    def descartar_incompleta(self, destino: str, geracao: str) -> None: ...

    def marcar_completa(self, destino: str, manifesto: ManifestoBackup) -> None: ...


class GerarBackup:
    """Gera uma cópia consistente; uma nova execução nunca substitui a última."""

    def __init__(
        self,
        coordenacao: CoordenacaoBackup,
        cifra: CifraBackup,
        *,
        timeout_jobs_seconds: float = 300,
        timeout_lock_seconds: float = 60,
    ) -> None:
        if timeout_jobs_seconds <= 0 or timeout_lock_seconds <= 0:
            raise ValueError("Os prazos de backup devem ser positivos.")
        self._coordenacao = coordenacao
        self._cifra = cifra
        self._timeout_jobs = timeout_jobs_seconds
        self._timeout_lock = timeout_lock_seconds

    def executar(
        self, destino_local: str, agora: datetime, modo: ModoBackup
    ) -> ManifestoBackup:
        _exigir_utc(agora)
        if not destino_local.strip() or modo not in {
            "diario",
            "manual_pre_apresentacao",
        }:
            raise ValueError("Destino ou modo de backup inválido.")

        generation_id = _gerar_id()
        staging: Path | None = None
        manutencao_solicitada = False
        cifra_iniciada = False
        manifesto: ManifestoBackup | None = None
        try:
            with self._coordenacao.lock_backup():
                self._coordenacao.solicitar_manutencao()
                manutencao_solicitada = True
                try:
                    self._coordenacao.aguardar_jobs_ociosos(self._timeout_jobs)
                    with self._coordenacao.lock_snapshot(self._timeout_lock):
                        staging = self._coordenacao.criar_staging(generation_id)
                        manifesto = self._coordenacao.criar_snapshot(
                            staging, generation_id, agora, modo
                        )
                        if manifesto.geracao != generation_id:
                            raise ValueError(
                                "O manifesto não corresponde à geração solicitada."
                            )
                        cifra_iniciada = True
                        self._cifra.cifrar(staging, destino_local, generation_id)
                        self._cifra.verificar(staging, destino_local, generation_id)
                        self._coordenacao.limpar_staging(staging)
                        staging = None
                        self._cifra.marcar_completa(destino_local, manifesto)
                        return manifesto
                except Exception:
                    if cifra_iniciada:
                        self._cifra.descartar_incompleta(destino_local, generation_id)
                    raise
                finally:
                    try:
                        if staging is not None:
                            self._coordenacao.limpar_staging(staging)
                    finally:
                        if manutencao_solicitada:
                            self._coordenacao.liberar_manutencao()
                            manutencao_solicitada = False
        finally:
            # Safety net for failures while acquiring/entering the backup lock.
            if manutencao_solicitada:
                self._coordenacao.liberar_manutencao()


class ArchiveCompleto(Protocol):
    def exigir_geracao_completa(self, geracao: str) -> None: ...

    def iniciar_transporte(self, geracao: str, destino: str) -> None: ...

    def abortar_transporte(self, geracao: str, destino: str) -> None: ...

    def marcar_transporte_completo(
        self, geracao: str, destino: str, tamanho_bytes: int, sha256: str
    ) -> None: ...


class AdaptadorTransporte(Protocol):
    def copiar_e_verificar(self, geracao: str) -> tuple[int, str]: ...


class TransportarBackup:
    """Copia somente gerações completas e verifica antes de registrar sucesso."""

    def __init__(self, arquivo: ArchiveCompleto) -> None:
        self._arquivo = arquivo

    def executar(
        self,
        geracao: str,
        destino_adapter: AdaptadorTransporte,
        *,
        destino: str = "externo",
    ) -> ResultadoVerificado:
        if not geracao.strip() or not destino.strip():
            raise ValueError("Geração e destino de transporte são obrigatórios.")
        self._arquivo.exigir_geracao_completa(geracao)
        self._arquivo.iniciar_transporte(geracao, destino)
        try:
            tamanho, sha256 = destino_adapter.copiar_e_verificar(geracao)
        except Exception:
            with suppress(Exception):
                self._arquivo.abortar_transporte(geracao, destino)
            raise
        if tamanho <= 0 or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            with suppress(Exception):
                self._arquivo.abortar_transporte(geracao, destino)
            raise ValueError("O hash ou tamanho verificado do backup é inválido.")
        self._arquivo.marcar_transporte_completo(geracao, destino, tamanho, sha256)
        return ResultadoVerificado(
            geracao=geracao,
            destino=destino,
            tamanho_bytes=tamanho,
            sha256=sha256,
            verificado_em=datetime.now(UTC),
        )


class AdaptadorRestore(Protocol):
    def validar_alvo_descartavel(
        self, banco: str, autorizacao: AutorizacaoRestore
    ) -> None: ...

    def descriptografar(self, geracao: str) -> Path: ...

    def verificar_manifesto(self, staging: Path) -> ManifestoBackup: ...

    def restaurar_banco(self, staging: Path, banco: str) -> None: ...

    def restaurar_referencias(self, staging: Path, banco: str) -> None: ...

    def reaplicar_exclusoes(self, banco: str) -> int: ...

    def invalidar_sessoes_e_tokens(self, banco: str) -> int: ...

    def validar_restore(self, banco: str, manifesto: ManifestoBackup) -> None: ...

    def limpar_staging(self, staging: Path) -> None: ...


class RestaurarEnsaio:
    """Restaura apenas em alvo descartável explicitamente autorizado."""

    def __init__(self, adaptador: AdaptadorRestore) -> None:
        self._adaptador = adaptador

    def executar(
        self,
        geracao: str,
        banco_descartavel: str,
        autorizacao: AutorizacaoRestore,
    ) -> EvidenciaRestore:
        if not geracao.strip() or not banco_descartavel.strip():
            raise ValueError("Geração e banco de ensaio são obrigatórios.")
        autorizacao.exigir_alvo(banco_descartavel)
        self._adaptador.validar_alvo_descartavel(banco_descartavel, autorizacao)
        staging = self._adaptador.descriptografar(geracao)
        try:
            manifesto = self._adaptador.verificar_manifesto(staging)
            if manifesto.geracao != geracao:
                raise ValueError("O manifesto pertence a outra geração.")
            self._adaptador.restaurar_banco(staging, banco_descartavel)
            self._adaptador.restaurar_referencias(staging, banco_descartavel)
            exclusoes = self._adaptador.reaplicar_exclusoes(banco_descartavel)
            sessoes = self._adaptador.invalidar_sessoes_e_tokens(banco_descartavel)
            self._adaptador.validar_restore(banco_descartavel, manifesto)
            return EvidenciaRestore(
                geracao=geracao,
                banco=banco_descartavel,
                revisao_schema=manifesto.revisao_schema,
                arquivos_verificados=len(manifesto.arquivos),
                exclusoes_reaplicadas=exclusoes,
                sessoes_tokens_invalidos=sessoes,
                validado_em=datetime.now(UTC),
            )
        finally:
            self._adaptador.limpar_staging(staging)


class CatalogoExpurgo(Protocol):
    def planejar(
        self,
        agora: datetime,
        finalidade_ate: datetime,
        max_geracoes: int,
        retencao_logs: timedelta,
    ) -> tuple[str, ...]: ...

    def aplicar(self, alvo: str) -> None: ...


class ExpurgarWeb:
    """Planeja expurgo sem efeitos; aplicar exige confirmação do ambiente/alvo."""

    def __init__(
        self,
        catalogo: CatalogoExpurgo,
        *,
        ambiente: str,
        alvo: str,
        finalidade_ate: datetime,
        max_geracoes: int = 3,
        retencao_logs: timedelta = timedelta(days=3),
    ) -> None:
        _exigir_utc(finalidade_ate)
        if (
            not ambiente.strip()
            or not alvo.strip()
            or max_geracoes < 1
            or retencao_logs <= timedelta(0)
        ):
            raise ValueError("A configuração de expurgo é inválida.")
        self._catalogo = catalogo
        self._ambiente = ambiente
        self._alvo = alvo
        self._finalidade_ate = finalidade_ate
        self._max_geracoes = max_geracoes
        self._retencao_logs = retencao_logs

    def planejar(self, agora: datetime) -> PlanoExpurgo:
        _exigir_utc(agora)
        encerrada = agora >= self._finalidade_ate
        alvos = self._catalogo.planejar(
            agora,
            self._finalidade_ate,
            self._max_geracoes,
            self._retencao_logs,
        )
        return PlanoExpurgo(
            ambiente=self._ambiente,
            alvo=self._alvo,
            planejado_em=agora,
            finalidade_ate=self._finalidade_ate,
            finalidade_encerrada=encerrada,
            alvos=alvos,
        )

    def aplicar(self, plano: PlanoExpurgo, *, confirmacao: str) -> ResultadoExpurgo:
        if plano.ambiente != self._ambiente or plano.alvo != self._alvo:
            raise ValueError("O plano de expurgo pertence a outro ambiente ou alvo.")
        esperado = f"APLICAR-EXPURGO-{self._ambiente}-{self._alvo}"
        if confirmacao != esperado:
            raise ValueError("A confirmação do ambiente/alvo não corresponde.")
        removidos: list[str] = []
        for alvo in plano.alvos:
            self._catalogo.aplicar(alvo)
            removidos.append(alvo)
        return ResultadoExpurgo(
            ambiente=self._ambiente,
            alvo=self._alvo,
            finalidade_encerrada=plano.finalidade_encerrada,
            removidos=tuple(removidos),
        )


def _exigir_utc(instante: datetime) -> None:
    if instante.tzinfo is None or instante.utcoffset() != timedelta(0):
        raise ValueError("O horário deve ser datetime aware em UTC.")


def _gerar_id() -> str:
    from uuid import uuid4

    return uuid4().hex
