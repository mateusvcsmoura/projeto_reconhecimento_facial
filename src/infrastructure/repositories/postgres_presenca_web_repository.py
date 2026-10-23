"""Persistencia transacional de sessoes e presencas web por sessao."""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from dataclasses import replace
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import CursorResult, Engine, Result
from sqlalchemy.orm import Session, sessionmaker

from src.application.services.fila_facial import EstadoJobFacial, JobFacial
from src.domain.entities.sessao_presenca import SessaoPresenca
from src.domain.entities.tentativa_presenca import (
    EstadoTentativaPresenca,
    ResultadoPresencaPersistida,
    TentativaPresenca,
)
from src.domain.services.autorizacao import AtorWeb, AutorizarTurma
from src.domain.services.face_recognition import ResultadoFacial
from src.infrastructure.database import models


class TentativaIndisponivel(RuntimeError):
    """A sessao, matricula, link ou emissao nao pode ser usada."""


class QuotaTentativasEsgotada(RuntimeError):
    """As tres emissoes autorizadas da sessao ja foram consumidas."""


class TentativaAtiva(RuntimeError):
    """Ja existe uma tentativa ativa para esta pessoa nesta sessao."""


class CapturaRepetidaDiferente(RuntimeError):
    """Uma etapa ja recebida foi repetida com bytes diferentes."""


def _utc(instante: dt.datetime) -> dt.datetime:
    if instante.tzinfo is None or instante.utcoffset() is None:
        raise ValueError("O instante deve conter fuso horario.")
    return instante.astimezone(dt.UTC)


def _linhas_afetadas(resultado: Result[Any]) -> int:
    """DELETE devolve CursorResult; o tipo genérico de execute() não expõe rowcount."""
    return cast("CursorResult[Any]", resultado).rowcount


def _utc_armazenado(instante: dt.datetime) -> dt.datetime:
    """Valores lidos do banco são UTC; o SQLite dos testes os devolve sem fuso."""
    if instante.tzinfo is None or instante.utcoffset() is None:
        instante = instante.replace(tzinfo=dt.UTC)
    return instante.astimezone(dt.UTC)


def _para_sessao(linha: models.SessaoPresencaWeb) -> SessaoPresenca:
    return SessaoPresenca(
        id=linha.id,
        turma_id=linha.turma_id,
        criada_por_conta_id=linha.criada_por_conta_id,
        titulo=linha.titulo,
        inicio_em=_utc_armazenado(linha.inicio_em),
        fim_em=_utc_armazenado(linha.fim_em),
        criada_em=_utc_armazenado(linha.criada_em),
        revogada_em=_utc_armazenado(linha.revogada_em) if linha.revogada_em else None,
        revogada_por_conta_id=linha.revogada_por_conta_id,
        versao=linha.versao,
    )


def _para_tentativa(linha: models.TentativaPresencaWeb) -> TentativaPresenca:
    return TentativaPresenca(
        id=linha.id,
        sessao_id=linha.sessao_id,
        turma_id=linha.turma_id,
        aluno_id=linha.aluno_id,
        ordinal=linha.ordinal,
        estado=EstadoTentativaPresenca(linha.estado),
        iniciada_em=_utc(linha.iniciada_em),
        prazo_envio=_utc(linha.prazo_envio),
        versao_sessao=linha.versao_sessao,
        conjunto_id=linha.conjunto_id,
        versao_referencia=linha.versao_referencia,
        recebida_em=_utc(linha.recebida_em) if linha.recebida_em else None,
        concluida_em=_utc(linha.concluida_em) if linha.concluida_em else None,
        motivo_tecnico=linha.motivo_tecnico,
    )


class PostgresPresencaWebRepository:
    """Usa locks de linha e constraints como autoridade de concorrencia."""

    def __init__(
        self,
        engine_or_factory: Engine | sessionmaker[Session],
        *,
        timezone_name: str = "America/Sao_Paulo",
    ) -> None:
        self._engine = (
            engine_or_factory if isinstance(engine_or_factory, Engine) else None
        )
        self._session_factory = (
            sessionmaker(bind=engine_or_factory, expire_on_commit=False, future=True)
            if isinstance(engine_or_factory, Engine)
            else engine_or_factory
        )
        self._timezone = ZoneInfo(timezone_name)

    def criar_sessao(self, ator: AtorWeb, sessao_web: SessaoPresenca) -> SessaoPresenca:
        with self._factory()() as session, session.begin():
            atual = self._ator_atual(session, ator)
            turma = session.scalar(
                select(models.Turma)
                .where(models.Turma.id == sessao_web.turma_id)
                .with_for_update()
            )
            if turma is None or turma.excluida_em is not None:
                raise LookupError("Turma indisponivel.")
            AutorizarTurma.exigir(atual, turma, "criar sessao de presenca")
            linha = models.SessaoPresencaWeb(
                turma_id=turma.id,
                criada_por_conta_id=atual.conta_id,
                titulo=sessao_web.titulo,
                inicio_em=sessao_web.inicio_em,
                fim_em=sessao_web.fim_em,
                criada_em=sessao_web.criada_em,
                versao=1,
            )
            session.add(linha)
            session.flush()
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="sessao_presenca_criada",
                alvo_tipo="sessao_presenca_web",
                alvo_id=str(linha.id),
                instante=sessao_web.criada_em,
                depois={
                    "turma_id": turma.id,
                    "inicio_em": sessao_web.inicio_em.isoformat(),
                },
            )
            return _para_sessao(linha)

    def obter_sessao_autorizada(
        self, ator: AtorWeb, sessao_id: int
    ) -> SessaoPresenca | None:
        with self._factory()() as session, session.begin():
            atual = self._ator_atual(session, ator)
            linha = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == sessao_id)
                .with_for_update()
            )
            if linha is None:
                return None
            turma = session.get(models.Turma, linha.turma_id)
            if turma is None:
                return None
            AutorizarTurma.exigir(atual, turma, "gerenciar sessao de presenca")
            return _para_sessao(linha)

    def consultar_contexto_inicio(
        self,
        *,
        sessao_id: int,
        turma_id: int,
        link_id: UUID,
        matricula: str,
        agora: dt.datetime,
    ) -> dict[str, object]:
        instante = _utc(agora)
        with self._factory()() as session, session.begin():
            sessao_linha = session.get(models.SessaoPresencaWeb, sessao_id)
            link = session.get(models.LinkCadastroWeb, link_id)
            aluno = session.scalar(
                select(models.Aluno).where(models.Aluno.matricula == matricula)
            )
            if (
                sessao_linha is None
                or sessao_linha.turma_id != turma_id
                or sessao_linha.revogada_em is not None
                or link is None
                or link.finalidade != "presenca"
                or link.sessao_id != sessao_id
                or link.turma_id != turma_id
                or link.revogado_em is not None
                or _utc(link.expira_em) <= instante
                or _utc(link.finalidade_ate) <= instante
                or aluno is None
            ):
                raise TentativaIndisponivel()
            if sessao_linha.inicio_em > instante or sessao_linha.fim_em <= instante:
                raise TentativaIndisponivel()
            turma = session.get(models.Turma, turma_id)
            vinculo = session.get(models.AlunoTurma, (turma_id, aluno.id))
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb).where(
                    models.ConjuntoReferenciasWeb.aluno_id == aluno.id,
                    models.ConjuntoReferenciasWeb.estado == "ativo",
                )
            )
            revisao = session.scalar(
                select(models.RevisaoPresencaWeb.id).where(
                    models.RevisaoPresencaWeb.sessao_id == sessao_id,
                    models.RevisaoPresencaWeb.aluno_id == aluno.id,
                )
            )
            if (
                turma is None
                or turma.excluida_em is not None
                or vinculo is None
                or not vinculo.ativo
                or conjunto is None
                or conjunto.versao is None
                or revisao is not None
            ):
                raise TentativaIndisponivel()
            ordinais = tuple(
                session.scalars(
                    select(models.ReferenciaFacialWeb.ordinal)
                    .where(models.ReferenciaFacialWeb.conjunto_id == conjunto.id)
                    .order_by(models.ReferenciaFacialWeb.ordinal)
                )
            )
            if ordinais != (1, 2, 3):
                raise TentativaIndisponivel()
            return {
                "sessao": _para_sessao(sessao_linha),
                "aluno_id": aluno.id,
                "conjunto_id": conjunto.id,
                "versao_referencia": conjunto.versao,
            }

    def reservar_tentativa(
        self,
        *,
        job_id: UUID,
        sessao_id: int,
        turma_id: int,
        link_id: UUID,
        aluno_id: int,
        idempotencia_hash: str,
        iniciada_em: dt.datetime,
        prazo_envio: dt.datetime,
    ) -> tuple[TentativaPresenca, bool]:
        instante = _utc(iniciada_em)
        with self._factory()() as session, session.begin():
            sessao_linha = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == sessao_id)
                .with_for_update()
            )
            if (
                sessao_linha is None
                or sessao_linha.turma_id != turma_id
                or sessao_linha.revogada_em is not None
            ):
                raise TentativaIndisponivel()
            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.id == aluno_id)
                .with_for_update()
            )
            if aluno is None:
                raise TentativaIndisponivel()
            existente_idem = session.scalar(
                select(models.TentativaPresencaWeb).where(
                    models.TentativaPresencaWeb.sessao_id == sessao_id,
                    models.TentativaPresencaWeb.aluno_id == aluno_id,
                    models.TentativaPresencaWeb.idempotencia_hash == idempotencia_hash,
                )
            )
            if existente_idem is not None:
                if existente_idem.link_id != link_id:
                    raise TentativaIndisponivel()
                return _para_tentativa(existente_idem), True
            presenca_existente = session.scalar(
                select(models.Presenca.id).where(
                    models.Presenca.sessao_id == sessao_id,
                    models.Presenca.aluno_id == aluno_id,
                )
            )
            if presenca_existente is not None:
                raise TentativaIndisponivel()
            revisao_existente = session.scalar(
                select(models.RevisaoPresencaWeb.id).where(
                    models.RevisaoPresencaWeb.sessao_id == sessao_id,
                    models.RevisaoPresencaWeb.aluno_id == aluno_id,
                )
            )
            if revisao_existente is not None:
                raise TentativaIndisponivel()
            if instante < _utc(sessao_linha.inicio_em) or instante >= _utc(
                sessao_linha.fim_em
            ):
                raise TentativaIndisponivel()
            link = session.scalar(
                select(models.LinkCadastroWeb)
                .where(models.LinkCadastroWeb.id == link_id)
                .with_for_update()
            )
            turma = session.scalar(
                select(models.Turma)
                .where(models.Turma.id == turma_id)
                .with_for_update()
            )
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == turma_id,
                    models.AlunoTurma.aluno_id == aluno_id,
                )
                .with_for_update()
            )
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(
                    models.ConjuntoReferenciasWeb.aluno_id == aluno_id,
                    models.ConjuntoReferenciasWeb.estado == "ativo",
                )
                .with_for_update()
            )
            if (
                link is None
                or link.finalidade != "presenca"
                or link.sessao_id != sessao_id
                or link.turma_id != turma_id
                or link.revogado_em is not None
                or _utc(link.expira_em) <= instante
                or _utc(link.finalidade_ate) <= instante
                or turma is None
                or turma.excluida_em is not None
                or vinculo is None
                or not vinculo.ativo
                or conjunto is None
                or conjunto.versao is None
            ):
                raise TentativaIndisponivel()
            ativa = session.scalar(
                select(models.TentativaPresencaWeb)
                .where(
                    models.TentativaPresencaWeb.sessao_id == sessao_id,
                    models.TentativaPresencaWeb.aluno_id == aluno_id,
                    models.TentativaPresencaWeb.estado.in_(
                        ["iniciada", "recebida", "enfileirada", "processando"]
                    ),
                )
                .with_for_update()
            )
            if ativa is not None:
                raise TentativaAtiva()
            contagem = int(
                session.scalar(
                    select(func.count())
                    .select_from(models.TentativaPresencaWeb)
                    .where(
                        models.TentativaPresencaWeb.sessao_id == sessao_id,
                        models.TentativaPresencaWeb.aluno_id == aluno_id,
                    )
                )
                or 0
            )
            limite_tentativas = self._limite_tentativas(session, sessao_id, aluno_id)
            if contagem >= limite_tentativas:
                raise QuotaTentativasEsgotada()
            job = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == job_id)
                .with_for_update()
            )
            ordinais = tuple(
                session.scalars(
                    select(models.ReferenciaFacialWeb.ordinal)
                    .where(models.ReferenciaFacialWeb.conjunto_id == conjunto.id)
                    .order_by(models.ReferenciaFacialWeb.ordinal)
                )
            )
            if (
                job is None
                or job.tipo != "presenca"
                or job.estado != EstadoJobFacial.RECEBIDA.value
                or ordinais != (1, 2, 3)
            ):
                raise TentativaIndisponivel()
            linha = models.TentativaPresencaWeb(
                id=job_id,
                sessao_id=sessao_id,
                turma_id=turma_id,
                aluno_id=aluno_id,
                ordinal=contagem + 1,
                conjunto_id=conjunto.id,
                versao_referencia=conjunto.versao,
                versao_sessao=sessao_linha.versao,
                link_id=link_id,
                idempotencia_hash=idempotencia_hash,
                estado=EstadoTentativaPresenca.INICIADA.value,
                iniciada_em=instante,
                prazo_envio=_utc(prazo_envio),
            )
            session.add(linha)
            session.flush()
            return _para_tentativa(linha), False

    def registrar_captura(
        self,
        *,
        tentativa_id: UUID,
        credencial_hash: str,
        ordinal: int,
        payload_hash: str,
        recebida_em: dt.datetime,
    ) -> bool:
        instante = _utc(recebida_em)
        with self._factory()() as session, session.begin():
            tentativa = session.scalar(
                select(models.TentativaPresencaWeb)
                .where(models.TentativaPresencaWeb.id == tentativa_id)
                .with_for_update()
            )
            job = session.scalar(
                select(models.JobFacialWeb)
                .where(
                    models.JobFacialWeb.id == tentativa_id,
                    models.JobFacialWeb.credencial_hash == credencial_hash,
                )
                .with_for_update()
            )
            if tentativa is None or job is None:
                raise TentativaIndisponivel()
            anterior = session.get(
                models.RecebimentoTentativaPresencaWeb, (tentativa_id, ordinal)
            )
            if anterior is not None:
                if anterior.payload_hash != payload_hash:
                    raise CapturaRepetidaDiferente()
                return False
            if (
                tentativa.estado not in {"iniciada", "recebida"}
                or job.estado != EstadoJobFacial.RECEBIDA.value
                or instante > _utc(tentativa.prazo_envio)
            ):
                raise TentativaIndisponivel()
            count = int(
                session.scalar(
                    select(func.count())
                    .select_from(models.RecebimentoTentativaPresencaWeb)
                    .where(
                        models.RecebimentoTentativaPresencaWeb.tentativa_id
                        == tentativa_id
                    )
                )
                or 0
            )
            if ordinal != count + 1:
                raise TentativaIndisponivel()
            session.add(
                models.RecebimentoTentativaPresencaWeb(
                    tentativa_id=tentativa_id,
                    ordinal=ordinal,
                    payload_hash=payload_hash,
                    recebido_em=instante,
                )
            )
            tentativa.estado = EstadoTentativaPresenca.RECEBIDA.value
            tentativa.recebida_em = tentativa.recebida_em or instante
            session.flush()
            return True

    def consultar_tentativa(
        self, tentativa_id: UUID, credencial_hash: str
    ) -> dict[str, object] | None:
        with self._factory()() as session:
            row = session.execute(
                select(models.TentativaPresencaWeb, models.JobFacialWeb.estado)
                .join(
                    models.JobFacialWeb,
                    models.JobFacialWeb.id == models.TentativaPresencaWeb.id,
                )
                .where(
                    models.TentativaPresencaWeb.id == tentativa_id,
                    models.JobFacialWeb.credencial_hash == credencial_hash,
                )
            ).one_or_none()
            if row is None:
                return None
            tentativa, estado_job = row
            sessao_linha = session.get(models.SessaoPresencaWeb, tentativa.sessao_id)
            if sessao_linha is None:
                return None
            return {
                "tentativa": _para_tentativa(tentativa),
                "link_id": tentativa.link_id,
                "estado_job": EstadoJobFacial(estado_job),
                "sessao": _para_sessao(sessao_linha),
                "recebimentos": int(
                    session.scalar(
                        select(func.count())
                        .select_from(models.RecebimentoTentativaPresencaWeb)
                        .where(
                            models.RecebimentoTentativaPresencaWeb.tentativa_id
                            == tentativa_id
                        )
                    )
                    or 0
                ),
            }

    def rejeitar_tentativa(
        self, tentativa_id: UUID, motivo: str, *, agora: dt.datetime
    ) -> None:
        instante = _utc(agora)
        with self._factory()() as session, session.begin():
            linha = session.scalar(
                select(models.TentativaPresencaWeb)
                .where(models.TentativaPresencaWeb.id == tentativa_id)
                .with_for_update()
            )
            if linha is not None and linha.estado not in {
                EstadoTentativaPresenca.CONCLUIDA.value,
                EstadoTentativaPresenca.EXPIRADA.value,
                EstadoTentativaPresenca.REJEITADA.value,
            }:
                linha.estado = EstadoTentativaPresenca.REJEITADA.value
                linha.concluida_em = instante
                linha.motivo_tecnico = motivo[:64]

    def limitar_requisicao(
        self,
        chave_hash: str,
        *,
        agora: dt.datetime,
        limite: int,
        janela: dt.timedelta,
    ) -> int | None:
        instante = _utc(agora)
        with self._factory()() as session, session.begin():
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:bucket, 1515))"),
                {"bucket": chave_hash},
            )
            linha = session.scalar(
                select(models.LimitePresencaWeb)
                .where(models.LimitePresencaWeb.chave_hash == chave_hash)
                .with_for_update()
            )
            if linha is None:
                linha = models.LimitePresencaWeb(
                    chave_hash=chave_hash,
                    janela_iniciada_em=instante,
                    quantidade=0,
                    atualizado_em=instante,
                )
                session.add(linha)
                session.flush()
            if linha.bloqueado_ate is not None and _utc(linha.bloqueado_ate) > instante:
                return max(
                    1, math.ceil((_utc(linha.bloqueado_ate) - instante).total_seconds())
                )
            if _utc(linha.janela_iniciada_em) + janela <= instante:
                linha.janela_iniciada_em = instante
                linha.quantidade = 0
                linha.bloqueado_ate = None
            if linha.quantidade >= limite:
                linha.bloqueado_ate = instante + janela
                linha.atualizado_em = instante
                return max(1, math.ceil(janela.total_seconds()))
            linha.quantidade += 1
            linha.atualizado_em = instante
            session.execute(
                delete(models.LimitePresencaWeb).where(
                    models.LimitePresencaWeb.atualizado_em
                    < instante - dt.timedelta(days=1)
                )
            )
            return None

    def revogar_sessao(
        self, ator: AtorWeb, sessao_id: int, *, agora: dt.datetime
    ) -> tuple[int, tuple[UUID, ...]]:
        instante = _utc(agora)
        ids_limpar: list[UUID] = []
        with self._factory()() as session, session.begin():
            atual = self._ator_atual(session, ator)
            linha = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == sessao_id)
                .with_for_update()
            )
            if linha is None:
                raise LookupError("Sessao nao encontrada.")
            turma = session.get(models.Turma, linha.turma_id)
            if turma is None:
                raise LookupError("Sessao nao encontrada.")
            AutorizarTurma.exigir(atual, turma, "revogar sessao de presenca")
            if linha.revogada_em is not None:
                return 0, ()
            linha.revogada_em = instante
            linha.revogada_por_conta_id = atual.conta_id
            linha.versao += 1
            jobs = list(
                session.scalars(
                    select(models.JobFacialWeb)
                    .join(
                        models.TentativaPresencaWeb,
                        models.TentativaPresencaWeb.id == models.JobFacialWeb.id,
                    )
                    .where(
                        models.TentativaPresencaWeb.sessao_id == sessao_id,
                        models.TentativaPresencaWeb.estado.in_(
                            ["iniciada", "recebida", "enfileirada", "processando"]
                        ),
                    )
                    .with_for_update(of=models.JobFacialWeb)
                )
            )
            canceladas = 0
            for job in jobs:
                tentativa = session.get(models.TentativaPresencaWeb, job.id)
                if job.estado == EstadoJobFacial.PROCESSANDO.value:
                    job.cancelamento_solicitado = True
                else:
                    job.estado = EstadoJobFacial.CANCELADA.value
                    job.resultado_codigo = "sessao_revogada"
                    job.manifesto = None
                    job.finalizada_em = instante
                    ids_limpar.append(job.id)
                job.atualizada_em = instante
                if tentativa is not None:
                    tentativa.estado = EstadoTentativaPresenca.REJEITADA.value
                    tentativa.concluida_em = instante
                    tentativa.motivo_tecnico = "sessao_revogada"
                    canceladas += 1
            session.execute(
                update(models.LinkCadastroWeb)
                .where(
                    models.LinkCadastroWeb.sessao_id == sessao_id,
                    models.LinkCadastroWeb.revogado_em.is_(None),
                )
                .values(
                    revogado_em=instante,
                    revogado_por_conta_id=atual.conta_id,
                )
            )
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="sessao_presenca_revogada",
                alvo_tipo="sessao_presenca_web",
                alvo_id=str(sessao_id),
                instante=instante,
                depois={"tentativas_canceladas": canceladas, "versao": linha.versao},
            )
            return canceladas, tuple(ids_limpar)

    def editar_sessao(
        self,
        ator: AtorWeb,
        sessao_id: int,
        *,
        titulo: str,
        inicio_em: dt.datetime,
        fim_em: dt.datetime,
        fim_link: dt.datetime,
        agora: dt.datetime,
    ) -> SessaoPresenca:
        """Altera título/janela; nova janela invalida tentativas da versão anterior."""
        instante = _utc(agora)
        with self._factory()() as session, session.begin():
            atual = self._ator_atual(session, ator)
            linha = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == sessao_id)
                .with_for_update()
            )
            if linha is None:
                raise LookupError("Sessao nao encontrada.")
            turma = session.get(models.Turma, linha.turma_id)
            if turma is None:
                raise LookupError("Sessao nao encontrada.")
            AutorizarTurma.exigir(atual, turma, "editar sessao de presenca")
            if linha.revogada_em is not None:
                raise RuntimeError("Sessao revogada nao pode ser editada.")
            anterior = _para_sessao(linha)
            # A entidade revalida título e janela (ValueError se inválidos).
            editada = replace(
                anterior, titulo=titulo, inicio_em=inicio_em, fim_em=fim_em
            )
            janela_mudou = (editada.inicio_em, editada.fim_em) != (
                anterior.inicio_em,
                anterior.fim_em,
            )
            linha.titulo = editada.titulo
            linha.inicio_em = editada.inicio_em
            linha.fim_em = editada.fim_em
            if janela_mudou:
                linha.versao += 1
                limite = _utc(fim_link)
                # O mesmo link continua valendo para a nova janela.
                for link in session.scalars(
                    select(models.LinkCadastroWeb)
                    .where(
                        models.LinkCadastroWeb.sessao_id == sessao_id,
                        models.LinkCadastroWeb.revogado_em.is_(None),
                    )
                    .with_for_update()
                ):
                    if limite > _utc_armazenado(link.criado_em):
                        link.expira_em = limite
                        link.finalidade_ate = limite
                    else:
                        link.revogado_em = instante
                        link.revogado_por_conta_id = atual.conta_id
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="sessao_presenca_editada",
                alvo_tipo="sessao_presenca_web",
                alvo_id=str(sessao_id),
                instante=instante,
                depois={
                    "titulo": editada.titulo,
                    "inicio_em": editada.inicio_em.isoformat(),
                    "fim_em": editada.fim_em.isoformat(),
                    "versao": linha.versao,
                },
            )
            session.flush()
            return _para_sessao(linha)

    def excluir_sessao(
        self, ator: AtorWeb, sessao_id: int, *, agora: dt.datetime
    ) -> dict[str, object]:
        """Apaga a sessão e o que depende dela, na ordem exigida pelas FKs RESTRICT."""
        instante = _utc(agora)
        with self._factory()() as session, session.begin():
            atual = self._ator_atual(session, ator)
            linha = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == sessao_id)
                .with_for_update()
            )
            if linha is None:
                raise LookupError("Sessao nao encontrada.")
            turma = session.get(models.Turma, linha.turma_id)
            if turma is None:
                raise LookupError("Sessao nao encontrada.")
            AutorizarTurma.exigir(atual, turma, "excluir sessao de presenca")
            tentativas = tuple(
                session.scalars(
                    select(models.TentativaPresencaWeb.id).where(
                        models.TentativaPresencaWeb.sessao_id == sessao_id
                    )
                )
            )
            # Job id == tentativa id; o worker não pode perder a linha no meio do uso.
            if tentativas and session.scalar(
                select(func.count())
                .select_from(models.JobFacialWeb)
                .where(
                    models.JobFacialWeb.id.in_(tentativas),
                    models.JobFacialWeb.estado == EstadoJobFacial.PROCESSANDO.value,
                )
            ):
                raise RuntimeError("Aguarde as verificacoes em processamento.")
            presencas = session.execute(
                delete(models.Presenca).where(models.Presenca.sessao_id == sessao_id)
            )
            revisoes = session.execute(
                delete(models.RevisaoPresencaWeb).where(
                    models.RevisaoPresencaWeb.sessao_id == sessao_id
                )
            )
            session.execute(
                delete(models.TentativaPresencaWeb).where(
                    models.TentativaPresencaWeb.sessao_id == sessao_id
                )
            )
            if tentativas:
                session.execute(
                    delete(models.JobFacialWeb).where(
                        models.JobFacialWeb.id.in_(tentativas)
                    )
                )
            links = session.execute(
                delete(models.LinkCadastroWeb).where(
                    models.LinkCadastroWeb.sessao_id == sessao_id
                )
            )
            session.execute(
                delete(models.SessaoPresencaWeb).where(
                    models.SessaoPresencaWeb.id == sessao_id
                )
            )
            resultado: dict[str, object] = {
                "presencas": _linhas_afetadas(presencas),
                "tentativas": len(tentativas),
                "revisoes": _linhas_afetadas(revisoes),
                "links": _linhas_afetadas(links),
            }
            self._auditar(
                session,
                ator_id=atual.conta_id,
                acao="sessao_presenca_excluida",
                alvo_tipo="sessao_presenca_web",
                alvo_id=str(sessao_id),
                instante=instante,
                depois={**resultado, "turma_id": turma.id},
            )
            return {**resultado, "jobs_temporarios": tentativas}

    def concluir_presenca(
        self,
        job: JobFacial,
        decisao: ResultadoFacial,
        *,
        agora: dt.datetime,
    ) -> ResultadoPresencaPersistida | None:
        instante = _utc(agora)
        if job.lease is None:
            return None
        with self._factory()() as session, session.begin():
            tentativa_base = session.execute(
                select(
                    models.TentativaPresencaWeb.sessao_id,
                    models.TentativaPresencaWeb.turma_id,
                    models.TentativaPresencaWeb.aluno_id,
                    models.TentativaPresencaWeb.conjunto_id,
                    models.TentativaPresencaWeb.versao_referencia,
                    models.TentativaPresencaWeb.versao_sessao,
                    models.TentativaPresencaWeb.link_id,
                ).where(models.TentativaPresencaWeb.id == job.id)
            ).one_or_none()
            if tentativa_base is None:
                return None
            sessao_linha = session.scalar(
                select(models.SessaoPresencaWeb)
                .where(models.SessaoPresencaWeb.id == tentativa_base.sessao_id)
                .with_for_update()
            )
            job_linha = session.scalar(
                select(models.JobFacialWeb)
                .where(models.JobFacialWeb.id == job.id)
                .with_for_update()
            )
            tentativa = session.scalar(
                select(models.TentativaPresencaWeb)
                .where(models.TentativaPresencaWeb.id == job.id)
                .with_for_update()
            )
            if (
                sessao_linha is None
                or job_linha is None
                or tentativa is None
                or job_linha.estado != EstadoJobFacial.PROCESSANDO.value
                or job_linha.tipo != "presenca"
                or job_linha.dono_id
                != f"presenca:{tentativa.sessao_id}:{tentativa.aluno_id}"
                or job_linha.lease_hash
                != hashlib.sha256(job.lease.encode()).hexdigest()
                or job_linha.lease_expira_em is None
                or _utc(job_linha.lease_expira_em) <= instante
                or _utc(job_linha.prazo_execucao) <= instante
                or job_linha.cancelamento_solicitado
                or sessao_linha.revogada_em is not None
                or sessao_linha.versao != tentativa.versao_sessao
                or tentativa.estado != EstadoTentativaPresenca.PROCESSANDO.value
                or tentativa.recebida_em is None
                or _utc(tentativa.recebida_em) > _utc(tentativa.prazo_envio)
                or decisao.versao_referencia != tentativa.versao_referencia
            ):
                return None
            revisao = session.scalar(
                select(models.RevisaoPresencaWeb.id).where(
                    models.RevisaoPresencaWeb.sessao_id == tentativa.sessao_id,
                    models.RevisaoPresencaWeb.aluno_id == tentativa.aluno_id,
                )
            )
            if revisao is not None:
                return None
            turma = session.scalar(
                select(models.Turma)
                .where(models.Turma.id == tentativa.turma_id)
                .with_for_update()
            )
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(
                    models.AlunoTurma.turma_id == tentativa.turma_id,
                    models.AlunoTurma.aluno_id == tentativa.aluno_id,
                )
                .with_for_update()
            )
            link = session.scalar(
                select(models.LinkCadastroWeb)
                .where(models.LinkCadastroWeb.id == tentativa.link_id)
                .with_for_update()
            )
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.aluno_id == tentativa.aluno_id)
                .where(models.ConjuntoReferenciasWeb.estado == "ativo")
                .with_for_update()
            )
            desafio = session.scalar(
                select(models.DesafioVerificacaoWeb)
                .where(models.DesafioVerificacaoWeb.id == job.id)
                .with_for_update()
            )
            if (
                turma is None
                or turma.excluida_em is not None
                or vinculo is None
                or not vinculo.ativo
                or link is None
                or link.revogado_em is not None
                or link.sessao_id != sessao_linha.id
                or conjunto is None
                or conjunto.id != tentativa.conjunto_id
                or conjunto.versao != tentativa.versao_referencia
                or desafio is None
                or desafio.estado != "concluido"
                or desafio.etapa_validada != 3
                or desafio.etapa_recebida != 3
                or desafio.aluno_id != tentativa.aluno_id
                or desafio.conjunto_id != tentativa.conjunto_id
                or desafio.versao_referencia != tentativa.versao_referencia
            ):
                return None
            ordinais = tuple(
                session.scalars(
                    select(models.ReferenciaFacialWeb.ordinal)
                    .where(models.ReferenciaFacialWeb.conjunto_id == conjunto.id)
                    .order_by(models.ReferenciaFacialWeb.ordinal)
                )
            )
            if ordinais != (1, 2, 3):
                return None
            inserido = session.execute(
                pg_insert(models.Presenca)
                .values(
                    aluno_id=tentativa.aluno_id,
                    turma_id=tentativa.turma_id,
                    sessao_id=tentativa.sessao_id,
                    tentativa_id=tentativa.id,
                    registrado_em=instante,
                    data_referencia=instante.astimezone(self._timezone).date(),
                    status="presente",
                    origem="biometrica",
                    versao=1,
                    horario_evidencia=instante,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        models.Presenca.sessao_id,
                        models.Presenca.aluno_id,
                    ],
                    index_where=models.Presenca.sessao_id.is_not(None),
                )
                .returning(models.Presenca.id)
            ).scalar_one_or_none()
            presenca_id = inserido
            duplicada = inserido is None
            if duplicada:
                presenca_id = session.scalar(
                    select(models.Presenca.id).where(
                        models.Presenca.sessao_id == tentativa.sessao_id,
                        models.Presenca.aluno_id == tentativa.aluno_id,
                    )
                )
            if presenca_id is None:
                return None
            tentativa.estado = EstadoTentativaPresenca.CONCLUIDA.value
            tentativa.concluida_em = instante
            tentativa.motivo_tecnico = "presenca_ja_registrada" if duplicada else None
            job_linha.estado = EstadoJobFacial.CONCLUIDA.value
            job_linha.resultado_codigo = (
                "presenca_ja_registrada" if duplicada else "concluida"
            )
            job_linha.lease_hash = None
            job_linha.lease_expira_em = None
            job_linha.manifesto = None
            job_linha.atualizada_em = instante
            job_linha.finalizada_em = instante
            return ResultadoPresencaPersistida(int(presenca_id), duplicada)

    def _factory(self) -> sessionmaker[Session]:
        return self._session_factory

    @staticmethod
    def _limite_tentativas(session: Session, sessao_id: int, aluno_id: int) -> int:
        reativacoes = int(
            session.scalar(
                select(func.count())
                .select_from(models.EventoAuditoriaWeb)
                .where(
                    models.EventoAuditoriaWeb.acao == "quota_presenca_reativada",
                    models.EventoAuditoriaWeb.alvo_tipo == "sessao_aluno",
                    models.EventoAuditoriaWeb.alvo_id == f"{sessao_id}:{aluno_id}",
                )
            )
            or 0
        )
        return 3 * (reativacoes + 1)

    @staticmethod
    def _ator_atual(session: Session, ator: AtorWeb) -> AtorWeb:
        conta = session.scalar(
            select(models.ContaWeb)
            .where(models.ContaWeb.id == ator.conta_id)
            .with_for_update()
        )
        if conta is None or not conta.ativa or conta.troca_senha_obrigatoria:
            raise PermissionError("Conta nao autorizada.")
        professor = session.scalar(
            select(models.ProfessorWeb)
            .where(models.ProfessorWeb.conta_id == conta.id)
            .with_for_update()
        )
        return AtorWeb(
            conta_id=conta.id,
            papel=conta.papel,
            ativa=conta.ativa,
            troca_senha_obrigatoria=conta.troca_senha_obrigatoria,
            professor_id=professor.id if professor else None,
        )

    @staticmethod
    def _auditar(
        session: Session,
        *,
        ator_id: int,
        acao: str,
        alvo_tipo: str,
        alvo_id: str,
        instante: dt.datetime,
        depois: dict[str, object],
    ) -> None:
        session.add(
            models.EventoAuditoriaWeb(
                ator_conta_id=ator_id,
                acao=acao,
                alvo_tipo=alvo_tipo,
                alvo_id=alvo_id,
                instante=instante,
                depois=depois,
            )
        )
