"""Orquestra reserva, limite de emissoes e desafio 1:1 de presenca."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from src.application.services.fila_facial import FilaFacial, TipoJobFacial
from src.application.use_cases.gerenciar_links import AcessoLinkEmitido
from src.domain.entities.tentativa_presenca import (
    TentativaPresenca,
    calcular_prazo_tentativa,
)
from src.domain.services.desafio_captura import ContextoDesafio, Desafio, DesafioCaptura


@dataclass(frozen=True, slots=True)
class TentativaIniciada:
    tentativa: TentativaPresenca
    credencial_captura: str
    desafio: Desafio | None


class RepositorioInicioTentativa(Protocol):
    def consultar_contexto_inicio(self, **kwargs: object) -> dict[str, object]: ...

    def reservar_tentativa(
        self, **kwargs: object
    ) -> tuple[TentativaPresenca, bool]: ...

    def rejeitar_tentativa(
        self, tentativa_id: UUID, motivo: str, *, agora: datetime
    ) -> None: ...


class IniciarTentativa:
    def __init__(
        self,
        repositorio: RepositorioInicioTentativa,
        fila: FilaFacial,
        desafios: DesafioCaptura,
    ) -> None:
        self._repositorio = repositorio
        self._fila = fila
        self._desafios = desafios

    def executar(
        self,
        acesso_link: AcessoLinkEmitido,
        matricula: str,
        chave_idempotente: str,
        *,
        agora: datetime,
    ) -> TentativaIniciada:
        instante = self._utc(agora)
        chave = chave_idempotente.strip()
        matricula_exata = matricula
        if (
            acesso_link.finalidade != "presenca"
            or acesso_link.sessao_id is None
            or not chave
            or len(chave) > 256
            or not isinstance(matricula_exata, str)
            or not matricula_exata
            or len(matricula_exata) > 32
        ):
            raise ValueError("A credencial, matricula ou chave e invalida.")
        contexto = self._repositorio.consultar_contexto_inicio(
            sessao_id=acesso_link.sessao_id,
            turma_id=acesso_link.turma_id,
            link_id=acesso_link.link_id,
            matricula=matricula_exata,
            agora=instante,
        )
        sessao = contexto.get("sessao")
        aluno_id = contexto.get("aluno_id")
        conjunto_id = contexto.get("conjunto_id")
        versao_referencia = contexto.get("versao_referencia")
        if (
            not isinstance(aluno_id, int)
            or not isinstance(conjunto_id, int)
            or not isinstance(versao_referencia, int)
        ):
            raise RuntimeError("O contexto de verificacao esta incompleto.")
        prazo = calcular_prazo_tentativa(sessao, instante)  # type: ignore[arg-type]
        dono_id = f"presenca:{acesso_link.sessao_id}:{aluno_id}"
        reserva = self._fila.reservar(
            TipoJobFacial.PRESENCA,
            dono_id,
            chave,
            prazo,
        )
        try:
            tentativa, repetida = self._repositorio.reservar_tentativa(
                job_id=reserva.id,
                sessao_id=acesso_link.sessao_id,
                turma_id=acesso_link.turma_id,
                link_id=acesso_link.link_id,
                aluno_id=aluno_id,
                idempotencia_hash=hashlib.sha256(chave.encode("utf-8")).hexdigest(),
                iniciada_em=instante,
                prazo_envio=prazo,
            )
        except Exception:
            self._fila.cancelar(reserva.id, reserva.credencial)
            raise
        desafio: Desafio | None = None
        if not repetida:
            try:
                desafio = self._desafios.emitir(
                    ContextoDesafio(
                        job_id=tentativa.id,
                        aluno_id=aluno_id,
                        conjunto_id=conjunto_id,
                        versao_referencia=versao_referencia,
                        prazo_recebimento=prazo,
                    ),
                    instante,
                )
            except Exception:
                self._repositorio.rejeitar_tentativa(
                    tentativa.id, "desafio_indisponivel", agora=instante
                )
                self._fila.cancelar(reserva.id, reserva.credencial)
                raise
        return TentativaIniciada(tentativa, reserva.credencial, desafio)

    @staticmethod
    def _utc(instante: datetime) -> datetime:
        if instante.tzinfo is None or instante.utcoffset() is None:
            raise ValueError("O instante deve conter fuso horario.")
        return instante.astimezone(UTC)
