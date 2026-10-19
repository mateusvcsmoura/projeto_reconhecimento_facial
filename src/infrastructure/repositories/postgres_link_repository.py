"""Persistência transacional de convites e credenciais de cadastro web."""

from __future__ import annotations

import datetime as dt
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from src.application.services.fila_facial import EstadoJobFacial
from src.domain.services.autorizacao import AtorWeb, AutorizarTurma
from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao


def _utc(valor: dt.datetime) -> dt.datetime:
    if valor.tzinfo is None or valor.utcoffset() is None:
        # SQLite remove o offset mesmo quando a coluna o declara.
        return valor.replace(tzinfo=dt.UTC)
    return valor.astimezone(dt.UTC)


def _ator_atual(session: Session, ator: AtorWeb) -> AtorWeb:
    conta = session.scalar(
        select(models.ContaWeb)
        .where(models.ContaWeb.id == ator.conta_id)
        .with_for_update()
    )
    if conta is None or not conta.ativa or conta.troca_senha_obrigatoria:
        raise PermissionError("A conta não está autorizada para esta operação.")
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


def _auditar(
    session: Session,
    *,
    ator_id: int | None,
    acao: str,
    alvo_id: UUID,
    instante: dt.datetime,
    depois: dict[str, object],
) -> None:
    session.add(
        models.EventoAuditoriaWeb(
            ator_conta_id=ator_id,
            acao=acao,
            alvo_tipo="link_cadastro_web",
            alvo_id=str(alvo_id),
            instante=instante,
            depois=depois,
        )
    )


class PostgresLinkRepository:
    """Serializa link, submissão e revogação usando locks PostgreSQL."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def criar_link(
        self,
        *,
        ator: AtorWeb,
        turma_id: int,
        finalidade: str,
        token_hash: str,
        criado_em: dt.datetime,
        expira_em: dt.datetime,
        finalidade_ate: dt.datetime,
    ) -> UUID:
        instante = _utc(criado_em)
        expiracao = _utc(expira_em)
        fim = _utc(finalidade_ate)
        if finalidade != "cadastro" or expiracao <= instante or fim <= instante:
            raise ValueError("O link ou finalidade são inválidos.")
        link_id = uuid4()
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            turma = session.scalar(
                select(models.Turma)
                .where(models.Turma.id == turma_id)
                .with_for_update()
            )
            if turma is None or turma.excluida_em is not None:
                raise LookupError("A turma não está disponível.")
            AutorizarTurma.exigir(atual, turma, "emitir link de cadastro")
            session.add(
                models.LinkCadastroWeb(
                    id=link_id,
                    turma_id=turma_id,
                    emitido_por_conta_id=atual.conta_id,
                    token_hash=token_hash,
                    finalidade=finalidade,
                    criado_em=instante,
                    expira_em=expiracao,
                    finalidade_ate=fim,
                )
            )
            session.flush()
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="link_cadastro_web_criado",
                alvo_id=link_id,
                instante=instante,
                depois={
                    "finalidade": finalidade,
                    "turma_id": turma_id,
                    "expira_em": expiracao.isoformat(),
                },
            )
        return link_id

    def trocar_token(
        self,
        *,
        token_hash: str,
        credencial_hash: str,
        agora: dt.datetime,
        credencial_expira_em: dt.datetime,
    ) -> dict[str, object] | None:
        instante = _utc(agora)
        with sessao(self._engine) as session:
            link = session.scalar(
                select(models.LinkCadastroWeb)
                .where(models.LinkCadastroWeb.token_hash == token_hash)
                .with_for_update()
            )
            if (
                link is None
                or link.finalidade != "cadastro"
                or link.revogado_em is not None
                or _utc(link.expira_em) <= instante
                or _utc(link.finalidade_ate) <= instante
            ):
                return None
            expiracao = min(_utc(credencial_expira_em), _utc(link.finalidade_ate))
            if expiracao <= instante:
                return None
            session.add(
                models.CredencialLinkCadastroWeb(
                    token_hash=credencial_hash,
                    link_id=link.id,
                    criada_em=instante,
                    expira_em=expiracao,
                )
            )
            session.flush()
            return {
                "link_id": link.id,
                "turma_id": link.turma_id,
                "finalidade": link.finalidade,
                "finalidade_ate": _utc(link.finalidade_ate),
                "credencial_expira_em": expiracao,
            }

    def contexto_credencial(
        self,
        credencial_hash: str,
        *,
        agora: dt.datetime,
        solicitacao_id: int | None = None,
        exigir_link_ativo: bool = True,
    ) -> dict[str, object] | None:
        instante = _utc(agora)
        with self._engine.connect() as connection:
            resultado = (
                connection.execute(
                    select(
                        models.CredencialLinkCadastroWeb.link_id,
                        models.CredencialLinkCadastroWeb.solicitacao_id,
                        models.CredencialLinkCadastroWeb.expira_em.label("cred_expira"),
                        models.LinkCadastroWeb.turma_id,
                        models.LinkCadastroWeb.finalidade,
                        models.LinkCadastroWeb.expira_em.label("link_expira"),
                        models.LinkCadastroWeb.finalidade_ate,
                        models.LinkCadastroWeb.revogado_em,
                    )
                    .join(
                        models.LinkCadastroWeb,
                        models.LinkCadastroWeb.id
                        == models.CredencialLinkCadastroWeb.link_id,
                    )
                    .where(
                        models.CredencialLinkCadastroWeb.token_hash == credencial_hash
                    )
                )
                .mappings()
                .one_or_none()
            )
        if resultado is None or _utc(resultado["cred_expira"]) <= instante:
            with self._engine.connect() as connection:
                atualizacao = (
                    connection.execute(
                        select(
                            models.SolicitacaoCadastroWeb.id,
                            models.SolicitacaoCadastroWeb.turma_id,
                            models.SolicitacaoCadastroWeb.estado,
                            models.SolicitacaoCadastroWeb.expira_em,
                            models.SolicitacaoCadastroWeb.credencial_captura_expira_em,
                        ).where(
                            models.SolicitacaoCadastroWeb.credencial_captura_hash
                            == credencial_hash,
                            models.SolicitacaoCadastroWeb.tipo == "atualizacao",
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
            if (
                atualizacao is None
                or solicitacao_id is None
                or atualizacao["id"] != solicitacao_id
                or atualizacao["credencial_captura_expira_em"] is None
                or _utc(atualizacao["credencial_captura_expira_em"]) <= instante
            ):
                return None
            expira_em = _utc(atualizacao["expira_em"])
            return {
                "link_id": None,
                "turma_id": atualizacao["turma_id"],
                "finalidade": "atualizacao",
                "finalidade_ate": expira_em,
                "expira_em": expira_em,
            }
        if solicitacao_id is None:
            if resultado["solicitacao_id"] is not None:
                return None
        elif resultado["solicitacao_id"] != solicitacao_id:
            return None
        if exigir_link_ativo and (
            resultado["revogado_em"] is not None
            or _utc(resultado["link_expira"]) <= instante
            or _utc(resultado["finalidade_ate"]) <= instante
        ):
            return None
        return {
            "link_id": resultado["link_id"],
            "turma_id": resultado["turma_id"],
            "finalidade": resultado["finalidade"],
            "finalidade_ate": _utc(resultado["finalidade_ate"]),
            "expira_em": _utc(resultado["link_expira"]),
        }

    def revogar(
        self, ator: AtorWeb, link_id: UUID, *, agora: dt.datetime
    ) -> tuple[int, tuple[int, ...]]:
        instante = _utc(agora)
        solicitacoes_canceladas: list[int] = []
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            link = session.scalar(
                select(models.LinkCadastroWeb)
                .where(models.LinkCadastroWeb.id == link_id)
                .with_for_update()
            )
            if link is None:
                raise LookupError("Link não encontrado.")
            turma = session.scalar(
                select(models.Turma)
                .where(models.Turma.id == link.turma_id)
                .with_for_update()
            )
            if turma is None or turma.excluida_em is not None:
                raise LookupError("Link não encontrado.")
            AutorizarTurma.exigir(atual, turma, "revogar link de cadastro")
            if link.revogado_em is not None:
                return 0, ()
            link.revogado_em = instante
            link.revogado_por_conta_id = atual.conta_id

            pendentes = session.scalars(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.link_id == link.id)
                .where(
                    models.SolicitacaoCadastroWeb.estado.in_(
                        ("em_coleta", "em_validacao", "pendente_aprovacao")
                    )
                )
                .order_by(models.SolicitacaoCadastroWeb.id)
                .with_for_update()
            ).all()
            for solicitacao in pendentes:
                estado_anterior = solicitacao.estado
                solicitacao.estado = "cancelada"
                solicitacao.decidida_em = instante
                solicitacao.decidida_por_conta_id = atual.conta_id
                solicitacao.justificativa = "Link de cadastro revogado."
                solicitacoes_canceladas.append(solicitacao.id)

                if solicitacao.job_id is not None:
                    job = session.scalar(
                        select(models.JobFacialWeb)
                        .where(models.JobFacialWeb.id == solicitacao.job_id)
                        .with_for_update()
                    )
                    if job is not None and job.estado in {
                        EstadoJobFacial.RECEBIDA.value,
                        EstadoJobFacial.ENFILEIRADA.value,
                        EstadoJobFacial.PROCESSANDO.value,
                    }:
                        if job.estado == EstadoJobFacial.PROCESSANDO.value:
                            job.cancelamento_solicitado = True
                        else:
                            job.estado = EstadoJobFacial.CANCELADA.value
                            job.resultado_codigo = "cancelada"
                            job.manifesto = None
                            job.finalizada_em = instante
                        job.atualizada_em = instante

                conjunto = session.scalar(
                    select(models.ConjuntoReferenciasWeb)
                    .where(
                        models.ConjuntoReferenciasWeb.solicitacao_id == solicitacao.id
                    )
                    .with_for_update()
                )
                if conjunto is not None and conjunto.estado == "pendente":
                    conjunto.estado = "descartado"
                    conjunto.aluno_id = None
                    conjunto.versao = None
                _auditar(
                    session,
                    ator_id=atual.conta_id,
                    acao="solicitacao_cadastro_web_cancelada_por_revogacao",
                    alvo_id=link.id,
                    instante=instante,
                    depois={
                        "solicitacao_id": solicitacao.id,
                        "estado_anterior": estado_anterior,
                        "estado": "cancelada",
                    },
                )
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="link_cadastro_web_revogado",
                alvo_id=link.id,
                instante=instante,
                depois={"solicitacoes_canceladas": len(solicitacoes_canceladas)},
            )
        return len(solicitacoes_canceladas), tuple(solicitacoes_canceladas)
