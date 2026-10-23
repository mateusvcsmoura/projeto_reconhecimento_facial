"""Persistência transacional de solicitações e versões biométricas web."""

from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass
from typing import overload
from uuid import UUID

from sqlalchemy import Engine, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain.entities.face_embedding import FaceEmbedding
from src.domain.entities.referencia_facial import ReferenciaParaPersistir
from src.domain.entities.solicitacao_cadastro import (
    ResultadoAprovacao,
    SolicitacaoCadastro,
)
from src.domain.errors import AnexoJaProcessado
from src.domain.services.autorizacao import AtorWeb, AutorizarTurma
from src.infrastructure.database import models
from src.infrastructure.database.engine import sessao

logger = logging.getLogger(__name__)


@overload
def _utc(instante: dt.datetime) -> dt.datetime: ...


@overload
def _utc(instante: None) -> None: ...


def _utc(instante: dt.datetime | None) -> dt.datetime | None:
    if instante is None:
        return None
    if instante.tzinfo is None or instante.utcoffset() is None:
        # SQLite não preserva o offset mesmo quando a coluna o declara.
        return instante.replace(tzinfo=dt.UTC)
    return instante.astimezone(dt.UTC)


@dataclass(frozen=True, slots=True)
class ReferenciaAtiva:
    """Projeção interna para worker; não deve ser serializada para professor."""

    aluno_id: int
    conjunto_id: int
    versao: int
    embedding: FaceEmbedding
    ordinal: int


def _para_solicitacao(
    linha: models.SolicitacaoCadastroWeb,
    link_criado_em: dt.datetime | None = None,
) -> SolicitacaoCadastro:
    return SolicitacaoCadastro(
        id=linha.id,
        tipo=linha.tipo,  # type: ignore[arg-type]
        estado=linha.estado,  # type: ignore[arg-type]
        turma_id=linha.turma_id,
        aluno_id=linha.aluno_id,
        matricula=linha.matricula,
        nome=linha.nome,
        expira_em=_utc(linha.expira_em),  # type: ignore[arg-type]
        consentimento_em=_utc(linha.consentimento_em),
        consentimento_versao=linha.consentimento_versao,
        desafio_nonce_hash=linha.desafio_nonce_hash,
        desafio_direcao=linha.desafio_direcao,
        desafio_expira_em=_utc(linha.desafio_expira_em),
        criada_em=_utc(linha.criada_em),
        link_criado_em=_utc(link_criado_em),
    )


def _ator_atual(session: Session, ator: AtorWeb, *, bloquear: bool = True) -> AtorWeb:
    consulta = select(models.ContaWeb).where(models.ContaWeb.id == ator.conta_id)
    if bloquear:
        consulta = consulta.with_for_update()
    conta = session.scalar(consulta)
    if conta is None or not conta.ativa or conta.troca_senha_obrigatoria:
        raise PermissionError("A conta não está autorizada para esta operação.")
    professor_consulta = select(models.ProfessorWeb).where(
        models.ProfessorWeb.conta_id == conta.id
    )
    if bloquear:
        professor_consulta = professor_consulta.with_for_update()
    professor = session.scalar(professor_consulta)
    return AtorWeb(
        conta_id=conta.id,
        papel=conta.papel,
        ativa=conta.ativa,
        troca_senha_obrigatoria=conta.troca_senha_obrigatoria,
        professor_id=professor.id if professor is not None else None,
    )


def _turma_ativa(session: Session, turma_id: int) -> models.Turma:
    turma = session.scalar(
        select(models.Turma).where(models.Turma.id == turma_id).with_for_update()
    )
    if turma is None or turma.excluida_em is not None:
        raise ValueError("A turma não está ativa.")
    return turma


def _auditar(
    session: Session,
    *,
    ator_id: int | None,
    acao: str,
    alvo_tipo: str,
    alvo_id: int,
    instante: dt.datetime,
    justificativa: str | None = None,
    antes: dict[str, object] | None = None,
    depois: dict[str, object] | None = None,
) -> None:
    session.add(
        models.EventoAuditoriaWeb(
            ator_conta_id=ator_id,
            acao=acao,
            alvo_tipo=alvo_tipo,
            alvo_id=str(alvo_id),
            instante=instante,
            justificativa=justificativa,
            antes=antes,
            depois=depois,
        )
    )


def _exigir_trinca(
    session: Session, conjunto: models.ConjuntoReferenciasWeb
) -> list[models.ReferenciaFacialWeb]:
    referencias = session.scalars(
        select(models.ReferenciaFacialWeb)
        .where(models.ReferenciaFacialWeb.conjunto_id == conjunto.id)
        .order_by(models.ReferenciaFacialWeb.ordinal)
        .with_for_update()
    ).all()
    if [referencia.ordinal for referencia in referencias] != [1, 2, 3]:
        raise ValueError("A aprovação exige as três referências técnicas.")
    if any(
        referencia.embedding_dim != 512
        or len(referencia.embedding) != 2048
        or referencia.embedding_modelo != conjunto.embedding_modelo
        for referencia in referencias
    ):
        raise ValueError("O conjunto de referências está inconsistente.")
    return list(referencias)


def _vincular(
    session: Session, turma_id: int, aluno_id: int, agora: dt.datetime
) -> None:
    vinculo = session.scalar(
        select(models.AlunoTurma)
        .where(models.AlunoTurma.turma_id == turma_id)
        .where(models.AlunoTurma.aluno_id == aluno_id)
        .with_for_update()
    )
    if vinculo is None:
        session.add(
            models.AlunoTurma(
                turma_id=turma_id,
                aluno_id=aluno_id,
                ativo=True,
                vinculado_em=agora,
                desvinculado_em=None,
            )
        )
    elif not vinculo.ativo:
        vinculo.ativo = True
        vinculo.vinculado_em = agora
        vinculo.desvinculado_em = None


class PostgresSolicitacaoRepository:
    """Repositório PostgreSQL; métodos também aceitam engines de teste SQLite."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def criar_cadastro(
        self,
        *,
        convite_ref: str,
        turma_id: int,
        matricula: str,
        nome: str,
        consentimento_em: dt.datetime,
        consentimento_versao: str,
        expira_em: dt.datetime,
        criado_em: dt.datetime,
        credencial_acesso_hash: str | None = None,
        desafio_nonce_hash: str | None = None,
        desafio_direcao: str | None = None,
        desafio_expira_em: dt.datetime | None = None,
    ) -> SolicitacaoCadastro:
        link_id: UUID | None = None
        instante = _utc(criado_em)
        expiracao = _utc(expira_em)
        credencial: models.CredencialLinkCadastroWeb | None = None
        with sessao(self._engine) as session:
            if credencial_acesso_hash is not None:
                try:
                    link_id = UUID(convite_ref)
                except ValueError as erro:
                    raise PermissionError("O link não está disponível.") from erro
                link = session.scalar(
                    select(models.LinkCadastroWeb)
                    .where(models.LinkCadastroWeb.id == link_id)
                    .with_for_update()
                )
                credencial = session.scalar(
                    select(models.CredencialLinkCadastroWeb)
                    .where(
                        models.CredencialLinkCadastroWeb.token_hash
                        == credencial_acesso_hash
                    )
                    .with_for_update()
                )
                if (
                    link is None
                    or link.finalidade != "cadastro"
                    or link.revogado_em is not None
                    or _utc(link.expira_em) <= instante
                    or _utc(link.finalidade_ate) <= instante
                    or link.turma_id != turma_id
                    or credencial is None
                    or credencial.link_id != link.id
                    or credencial.solicitacao_id is not None
                    or _utc(credencial.expira_em) <= instante
                    or expiracao > _utc(link.finalidade_ate)
                ):
                    raise PermissionError("O link não está disponível.")
            if expiracao <= instante:
                raise ValueError("A solicitação deve expirar no futuro.")
            turma = _turma_ativa(session, turma_id)
            if turma.responsavel_professor_id is None:
                raise ValueError("A turma ainda não possui professor responsável.")
            linha = models.SolicitacaoCadastroWeb(
                tipo="cadastro",
                estado="em_coleta",
                convite_ref=convite_ref,
                link_id=link_id,
                turma_id=turma_id,
                matricula=matricula,
                nome=nome,
                consentimento_em=consentimento_em,
                consentimento_versao=consentimento_versao,
                expira_em=expira_em,
                criada_em=criado_em,
                desafio_nonce_hash=desafio_nonce_hash,
                desafio_direcao=desafio_direcao,
                desafio_expira_em=desafio_expira_em,
            )
            session.add(linha)
            session.flush()
            if credencial is not None:
                credencial.solicitacao_id = linha.id
                credencial.expira_em = expiracao
            _auditar(
                session,
                ator_id=None,
                acao="solicitacao_cadastro_web_criada",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=linha.id,
                instante=instante,
                depois={"estado": "em_coleta", "turma_id": turma_id},
            )
            resultado = _para_solicitacao(linha)
        return resultado

    def obter_solicitacao(self, solicitacao_id: int) -> SolicitacaoCadastro:
        with sessao(self._engine) as session:
            linha = session.get(models.SolicitacaoCadastroWeb, solicitacao_id)
            if linha is None:
                raise LookupError("Solicitação não encontrada.")
            return _para_solicitacao(linha)

    def associar_job_cadastro(
        self,
        solicitacao_id: int,
        job_id: uuid.UUID,
        credencial_hash: str,
        *,
        agora: dt.datetime,
    ) -> None:
        instante = _utc(agora)
        with sessao(self._engine) as session:
            link_id = session.scalar(
                select(models.SolicitacaoCadastroWeb.link_id).where(
                    models.SolicitacaoCadastroWeb.id == solicitacao_id
                )
            )
            link = None
            if link_id is not None:
                link = session.scalar(
                    select(models.LinkCadastroWeb)
                    .where(models.LinkCadastroWeb.id == link_id)
                    .with_for_update()
                )
            credencial = session.scalar(
                select(models.CredencialLinkCadastroWeb)
                .where(models.CredencialLinkCadastroWeb.token_hash == credencial_hash)
                .with_for_update()
            )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if (
                linha is None
                or (
                    link_id is not None
                    and (link is None or link.revogado_em is not None)
                )
                or (link is not None and _utc(link.expira_em) <= instante)
                or (link is not None and _utc(link.finalidade_ate) <= instante)
                or (
                    link_id is not None
                    and (
                        credencial is None
                        or credencial.link_id != link_id
                        or credencial.solicitacao_id != solicitacao_id
                        or _utc(credencial.expira_em) <= instante
                    )
                )
                or (
                    link_id is None
                    and (
                        linha.credencial_captura_hash != credencial_hash
                        or linha.credencial_captura_expira_em is None
                        or _utc(linha.credencial_captura_expira_em) <= instante
                    )
                )
                or linha.tipo not in {"cadastro", "atualizacao"}
                or linha.estado != "em_coleta"
                or linha.job_id is not None
                or linha.consentimento_em is None
                or linha.consentimento_versao is None
                or _utc(linha.expira_em) <= instante
            ):
                raise PermissionError("A solicitação não está autorizada.")
            linha.job_id = job_id
            linha.estado = "em_validacao"
            session.flush()
            _auditar(
                session,
                ator_id=None,
                acao="job_cadastro_web_associado",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=solicitacao_id,
                instante=instante,
                depois={"estado": "em_validacao", "job_id": str(job_id)},
            )

    def registrar_consentimento_atualizacao(
        self,
        solicitacao_id: int,
        credencial_hash: str,
        versao: str,
        *,
        agora: dt.datetime,
        desafio_nonce_hash: str,
        desafio_direcao: str,
        desafio_expira_em: dt.datetime,
    ) -> SolicitacaoCadastro:
        instante = _utc(agora)
        aviso = versao.strip()
        if (
            not aviso
            or len(aviso) > 64
            or len(desafio_nonce_hash) != 64
            or any(
                caractere not in "0123456789abcdef" for caractere in desafio_nonce_hash
            )
            or desafio_direcao not in {"esquerda", "direita"}
        ):
            raise ValueError("A versão do aviso é inválida.")
        prazo_desafio = _utc(desafio_expira_em)
        if prazo_desafio is None or prazo_desafio <= instante:
            raise ValueError("O prazo do desafio é inválido.")
        with sessao(self._engine) as session:
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if (
                linha is None
                or linha.tipo != "atualizacao"
                or linha.estado != "em_coleta"
                or linha.link_id is not None
                or linha.credencial_captura_hash != credencial_hash
                or linha.credencial_captura_expira_em is None
                or _utc(linha.credencial_captura_expira_em) <= instante
                or _utc(linha.expira_em) <= instante
            ):
                raise PermissionError("A solicitação não está disponível.")
            if linha.consentimento_em is not None:
                raise ValueError("O consentimento já foi registrado.")
            if prazo_desafio > _utc(linha.expira_em):
                raise ValueError("O prazo do desafio excede a solicitação.")
            linha.consentimento_em = instante
            linha.consentimento_versao = aviso
            linha.desafio_nonce_hash = desafio_nonce_hash
            linha.desafio_direcao = desafio_direcao
            linha.desafio_expira_em = prazo_desafio
            session.flush()
            _auditar(
                session,
                ator_id=None,
                acao="consentimento_atualizacao_biometrica_registrado",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=solicitacao_id,
                instante=instante,
                depois={"consentimento_versao": aviso},
            )
            resultado = _para_solicitacao(linha)
        return resultado

    def renovar_desafio_coleta(
        self,
        solicitacao_id: int,
        *,
        agora: dt.datetime,
        desafio_nonce_hash: str,
        desafio_direcao: str,
        desafio_expira_em: dt.datetime,
    ) -> SolicitacaoCadastro:
        """Troca o nonce enquanto nenhuma captura foi enviada; o anterior morre."""
        instante = _utc(agora)
        prazo_desafio = _utc(desafio_expira_em)
        if (
            len(desafio_nonce_hash) != 64
            or any(
                caractere not in "0123456789abcdef" for caractere in desafio_nonce_hash
            )
            or desafio_direcao not in {"esquerda", "direita"}
            or prazo_desafio is None
            or prazo_desafio <= instante
        ):
            raise ValueError("O desafio é inválido.")
        with sessao(self._engine) as session:
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if linha is None:
                raise PermissionError("A solicitação não está disponível.")
            if (
                linha.tipo not in {"cadastro", "atualizacao"}
                or linha.estado != "em_coleta"
                or linha.consentimento_em is None
                or _utc(linha.expira_em) <= instante
                or prazo_desafio > _utc(linha.expira_em)
            ):
                raise ValueError("A coleta não está disponível.")
            linha.desafio_nonce_hash = desafio_nonce_hash
            linha.desafio_direcao = desafio_direcao
            linha.desafio_expira_em = prazo_desafio
            session.flush()
            resultado = _para_solicitacao(linha)
        return resultado

    def cancelar_coleta_cadastro(
        self,
        solicitacao_id: int,
        job_id: uuid.UUID,
        *,
        motivo: str,
        agora: dt.datetime,
    ) -> None:
        instante = _utc(agora)
        with sessao(self._engine) as session:
            link_id = session.scalar(
                select(models.SolicitacaoCadastroWeb.link_id).where(
                    models.SolicitacaoCadastroWeb.id == solicitacao_id
                )
            )
            if link_id is not None:
                session.scalar(
                    select(models.LinkCadastroWeb)
                    .where(models.LinkCadastroWeb.id == link_id)
                    .with_for_update()
                )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if (
                linha is None
                or linha.estado != "em_validacao"
                or linha.job_id != job_id
            ):
                return
            linha.estado = "cancelada"
            linha.decidida_em = instante
            linha.justificativa = motivo[:500]
            session.flush()
            _auditar(
                session,
                ator_id=None,
                acao="coleta_cadastro_web_cancelada",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=solicitacao_id,
                instante=instante,
                depois={"estado": "cancelada", "codigo": motivo[:64]},
            )

    def listar_cadastros_turma(
        self,
        ator: AtorWeb,
        turma_id: int,
        *,
        estado: str = "pendente_aprovacao",
        limite: int = 50,
    ) -> tuple[SolicitacaoCadastro, ...]:
        if estado not in {"em_coleta", "em_validacao", "pendente_aprovacao"}:
            raise ValueError("Estado de solicitação inválido.")
        if not 1 <= limite <= 100:
            raise ValueError("O limite da consulta é inválido.")
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            turma = _turma_ativa(session, turma_id)
            AutorizarTurma.exigir(atual, turma, "consultar cadastros web")
            linhas = session.execute(
                select(models.SolicitacaoCadastroWeb, models.LinkCadastroWeb.criado_em)
                .outerjoin(
                    models.LinkCadastroWeb,
                    models.LinkCadastroWeb.id == models.SolicitacaoCadastroWeb.link_id,
                )
                .where(models.SolicitacaoCadastroWeb.turma_id == turma_id)
                .where(models.SolicitacaoCadastroWeb.tipo == "cadastro")
                .where(models.SolicitacaoCadastroWeb.estado == estado)
                .order_by(models.SolicitacaoCadastroWeb.criada_em)
                .limit(limite)
            ).all()
            return tuple(
                _para_solicitacao(linha, link_criado_em)
                for linha, link_criado_em in linhas
            )

    def estado_do_job(self, solicitacao_id: int, job_id: uuid.UUID) -> str | None:
        with sessao(self._engine) as session:
            resultado = session.execute(
                select(models.SolicitacaoCadastroWeb.estado)
                .join(
                    models.ConjuntoReferenciasWeb,
                    models.ConjuntoReferenciasWeb.solicitacao_id
                    == models.SolicitacaoCadastroWeb.id,
                )
                .where(models.ConjuntoReferenciasWeb.job_id == str(job_id))
                .where(models.ConjuntoReferenciasWeb.solicitacao_id == solicitacao_id)
            ).scalar_one_or_none()
            return resultado

    def anexar_referencias(
        self,
        solicitacao_id: int,
        *,
        job_id: uuid.UUID,
        referencias: tuple[ReferenciaParaPersistir, ...],
        consentimento_em: dt.datetime,
        consentimento_versao: str,
        agora: dt.datetime,
    ) -> str:
        if len(referencias) != 3:
            raise ValueError("São necessárias exatamente três referências.")
        modelos = {item.embedding.modelo for item in referencias}
        if len(modelos) != 1:
            raise ValueError("As referências devem usar o mesmo modelo.")
        modelo = next(iter(modelos))
        with sessao(self._engine) as session:
            link_id = session.scalar(
                select(models.SolicitacaoCadastroWeb.link_id).where(
                    models.SolicitacaoCadastroWeb.id == solicitacao_id
                )
            )
            link = None
            if link_id is not None:
                link = session.scalar(
                    select(models.LinkCadastroWeb)
                    .where(models.LinkCadastroWeb.id == link_id)
                    .with_for_update()
                )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if linha is None or (link_id is not None and link is None):
                raise LookupError("Solicitação não encontrada.")
            existente = session.scalar(
                select(models.ConjuntoReferenciasWeb).where(
                    models.ConjuntoReferenciasWeb.job_id == str(job_id)
                )
            )
            if existente is not None:
                if existente.solicitacao_id != solicitacao_id:
                    raise ValueError("O job já foi associado a outra solicitação.")
                raise AnexoJaProcessado(linha.estado)
            else:
                estado_coleta_esperado = (
                    "em_validacao"
                    if linha.tipo == "atualizacao" or link is not None
                    else "em_coleta"
                )
                if (
                    (link is not None and link.revogado_em is not None)
                    or linha.estado != estado_coleta_esperado
                    or (
                        estado_coleta_esperado == "em_validacao"
                        and linha.job_id != job_id
                    )
                    or _utc(linha.expira_em) <= agora
                ):
                    raise ValueError("A solicitação não está aberta para coleta.")
                if linha.tipo == "cadastro":
                    consentimento = _utc(linha.consentimento_em)
                    versao = linha.consentimento_versao
                    if consentimento is None or versao is None:
                        raise ValueError("A coleta exige consentimento registrado.")
                else:
                    consentimento = _utc(consentimento_em)
                    versao = consentimento_versao.strip()
                    if not versao:
                        raise ValueError("A coleta exige consentimento registrado.")
                    linha.consentimento_em = consentimento
                    linha.consentimento_versao = versao
                if (
                    consentimento is None
                    or consentimento.tzinfo is None
                    or consentimento.utcoffset() is None
                ):
                    raise ValueError("O consentimento precisa ter fuso horário.")
                conjunto = models.ConjuntoReferenciasWeb(
                    solicitacao_id=solicitacao_id,
                    estado="pendente",
                    job_id=str(job_id),
                    embedding_modelo=modelo,
                    embedding_dim=512,
                    criado_em=agora,
                )
                session.add(conjunto)
                session.flush()
                for referencia in referencias:
                    if (
                        referencia.embedding.modelo != modelo
                        or referencia.embedding.dimensao != 512
                    ):
                        raise ValueError(
                            "O embedding de uma referência é incompatível."
                        )
                    session.add(
                        models.ReferenciaFacialWeb(
                            conjunto_id=conjunto.id,
                            ordinal=referencia.ordinal,
                            caminho_privado_relativo=referencia.caminho_privado_relativo,
                            embedding=referencia.embedding.para_bytes(),
                            embedding_modelo=modelo,
                            embedding_dim=512,
                            consentimento_em=_utc(consentimento),
                            consentimento_versao=versao,
                            capturada_em=agora,
                        )
                    )
                linha.estado = "pendente_aprovacao"
                session.flush()
                _auditar(
                    session,
                    ator_id=None,
                    acao="referencias_web_anexadas",
                    alvo_tipo="solicitacao_cadastro_web",
                    alvo_id=solicitacao_id,
                    instante=agora,
                    depois={
                        "estado": "pendente_aprovacao",
                        "quantidade_referencias": 3,
                    },
                )
                estado = linha.estado
        return estado

    def solicitar_atualizacao_biometrica(
        self,
        ator: AtorWeb,
        aluno_id: int,
        turma_id: int,
        *,
        expira_em: dt.datetime,
        agora: dt.datetime,
        credencial_captura_hash: str | None = None,
    ) -> SolicitacaoCadastro:
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            turma = _turma_ativa(session, turma_id)
            AutorizarTurma.exigir(atual, turma, "solicitar atualização biométrica")
            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.id == aluno_id)
                .with_for_update()
            )
            if aluno is None:
                raise LookupError("Aluno não encontrado.")
            vinculo = session.scalar(
                select(models.AlunoTurma)
                .where(models.AlunoTurma.turma_id == turma_id)
                .where(models.AlunoTurma.aluno_id == aluno_id)
                .with_for_update()
            )
            if vinculo is None or not vinculo.ativo:
                raise PermissionError("O aluno não está vinculado à turma.")
            linha = models.SolicitacaoCadastroWeb(
                tipo="atualizacao",
                estado="em_coleta",
                turma_id=turma_id,
                aluno_id=aluno_id,
                expira_em=expira_em,
                criada_em=agora,
                credencial_captura_hash=credencial_captura_hash,
                credencial_captura_expira_em=(
                    expira_em if credencial_captura_hash is not None else None
                ),
            )
            session.add(linha)
            session.flush()
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="atualizacao_biometrica_solicitada",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=linha.id,
                instante=agora,
                depois={"tipo": "atualizacao", "turma_id": turma_id},
            )
            resultado = _para_solicitacao(linha)
        return resultado

    def aprovar_cadastro(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        metodo_identidade: str,
        justificativa: str,
        agora: dt.datetime,
    ) -> ResultadoAprovacao:
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            link_id = session.scalar(
                select(models.SolicitacaoCadastroWeb.link_id).where(
                    models.SolicitacaoCadastroWeb.id == solicitacao_id
                )
            )
            link = None
            if link_id is not None:
                link = session.scalar(
                    select(models.LinkCadastroWeb)
                    .where(models.LinkCadastroWeb.id == link_id)
                    .with_for_update()
                )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if (
                linha is None
                or linha.tipo != "cadastro"
                or (link_id is not None and link is None)
            ):
                raise LookupError("Solicitação de cadastro não encontrada.")
            if link is not None and link.revogado_em is not None:
                raise ValueError("O link associado foi revogado.")
            turma = _turma_ativa(session, linha.turma_id)
            AutorizarTurma.exigir(atual, turma, "aprovar cadastro web")
            if linha.estado != "pendente_aprovacao" or _utc(linha.expira_em) <= agora:
                raise ValueError("A solicitação não está disponível para aprovação.")
            if not linha.consentimento_em or not linha.consentimento_versao:
                raise ValueError("O consentimento precisa estar registrado.")
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.solicitacao_id == linha.id)
                .with_for_update()
            )
            if conjunto is None or conjunto.estado != "pendente":
                raise ValueError("A solicitação não possui conjunto pendente.")
            _exigir_trinca(session, conjunto)

            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.matricula == linha.matricula)
                .with_for_update()
            )
            aluno_existente = aluno is not None
            if aluno is None:
                try:
                    with session.begin_nested():
                        aluno = models.Aluno(
                            matricula=linha.matricula,
                            nome=linha.nome,
                            foto_arquivo=None,
                            embedding=None,
                            embedding_modelo=None,
                            embedding_dim=None,
                            consentimento_em=linha.consentimento_em,
                        )
                        session.add(aluno)
                        session.flush()
                except IntegrityError:
                    # Outra aprovação pode ter inserido a matrícula após nosso
                    # SELECT. A UK global arbitra a corrida; reavaliar como existente.
                    aluno = session.scalar(
                        select(models.Aluno)
                        .where(models.Aluno.matricula == linha.matricula)
                        .with_for_update()
                    )
                    if aluno is None:
                        raise
                    aluno_existente = True
            if aluno is None:
                raise RuntimeError("Falha interna ao criar aluno.")
            if aluno_existente and aluno.consentimento_em is None:
                raise ValueError(
                    "O cadastro global existente não possui consentimento operacional."
                )

            _vincular(session, linha.turma_id, aluno.id, agora)
            if aluno_existente:
                # Nenhum dado global do aluno é substituído por dados do link.
                conjunto.estado = "descartado"
                conjunto.aluno_id = None
                conjunto.versao = None
            else:
                conjunto.estado = "ativo"
                conjunto.aluno_id = aluno.id
                conjunto.versao = 1
                conjunto.ativado_em = agora
            linha.estado = "aprovada"
            linha.decidida_em = agora
            linha.decidida_por_conta_id = atual.conta_id
            linha.metodo_identidade = metodo_identidade
            linha.justificativa = justificativa
            session.flush()
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="cadastro_web_aprovado",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=linha.id,
                instante=agora,
                justificativa=justificativa,
                antes={"estado": "pendente_aprovacao"},
                depois={
                    "estado": "aprovada",
                    "aluno_id": aluno.id,
                    "turma_id": linha.turma_id,
                    "aluno_existente": aluno_existente,
                    "metodo_identidade": metodo_identidade,
                    "conjunto_ativo": not aluno_existente,
                },
            )
            resultado = ResultadoAprovacao(
                aluno_id=aluno.id,
                turma_id=linha.turma_id,
                aluno_existente=aluno_existente,
            )
        return resultado

    def rejeitar_cadastro_web(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        justificativa: str,
        agora: dt.datetime,
    ) -> None:
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            link_id = session.scalar(
                select(models.SolicitacaoCadastroWeb.link_id).where(
                    models.SolicitacaoCadastroWeb.id == solicitacao_id
                )
            )
            if link_id is not None:
                session.scalar(
                    select(models.LinkCadastroWeb)
                    .where(models.LinkCadastroWeb.id == link_id)
                    .with_for_update()
                )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if linha is None or linha.tipo != "cadastro":
                raise LookupError("Solicitação de cadastro não encontrada.")
            if atual.papel != "admin":
                turma = _turma_ativa(session, linha.turma_id)
                AutorizarTurma.exigir(atual, turma, "rejeitar cadastro web")
            if linha.estado != "pendente_aprovacao":
                raise ValueError("A solicitação não está pendente de aprovação.")
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.solicitacao_id == linha.id)
                .with_for_update()
            )
            if conjunto is not None and conjunto.estado == "pendente":
                conjunto.estado = "descartado"
                conjunto.aluno_id = None
                conjunto.versao = None
            linha.estado = "rejeitada"
            linha.decidida_em = agora
            linha.decidida_por_conta_id = atual.conta_id
            linha.justificativa = justificativa
            session.flush()
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="cadastro_web_rejeitado",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=linha.id,
                instante=agora,
                justificativa=justificativa,
                antes={"estado": "pendente_aprovacao"},
                depois={
                    "estado": "rejeitada",
                    "conjunto_descartado": conjunto is not None,
                },
            )

    def aprovar_atualizacao_biometrica(
        self,
        ator: AtorWeb,
        solicitacao_id: int,
        *,
        justificativa: str,
        agora: dt.datetime,
    ) -> int:
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            if atual.papel != "admin":
                raise PermissionError(
                    "Somente administrador pode aprovar atualização biométrica."
                )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if (
                linha is None
                or linha.tipo != "atualizacao"
                or linha.estado != "pendente_aprovacao"
                or _utc(linha.expira_em) <= agora
            ):
                raise ValueError("A atualização não está disponível para aprovação.")
            if linha.consentimento_em is None or linha.consentimento_versao is None:
                raise ValueError("A atualização exige consentimento do titular.")
            aluno = session.scalar(
                select(models.Aluno)
                .where(models.Aluno.id == linha.aluno_id)
                .with_for_update()
            )
            if aluno is None:
                raise LookupError("Aluno não encontrado.")
            conjunto_novo = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.solicitacao_id == linha.id)
                .with_for_update()
            )
            if conjunto_novo is None or conjunto_novo.estado != "pendente":
                raise ValueError("A atualização não possui conjunto pendente.")
            _exigir_trinca(session, conjunto_novo)
            ativos = session.scalars(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.aluno_id == aluno.id)
                .where(models.ConjuntoReferenciasWeb.estado == "ativo")
                .order_by(models.ConjuntoReferenciasWeb.id)
                .with_for_update()
            ).all()
            versao_atual = (
                session.scalar(
                    select(func.max(models.ConjuntoReferenciasWeb.versao)).where(
                        models.ConjuntoReferenciasWeb.aluno_id == aluno.id
                    )
                )
                or 0
            )
            for conjunto_antigo in ativos:
                conjunto_antigo.estado = "substituido"
            conjunto_novo.estado = "ativo"
            conjunto_novo.aluno_id = aluno.id
            conjunto_novo.versao = versao_atual + 1
            conjunto_novo.ativado_em = agora
            linha.estado = "aprovada"
            linha.decidida_em = agora
            linha.decidida_por_conta_id = atual.conta_id
            linha.metodo_identidade = "aprovacao_administrativa"
            linha.justificativa = justificativa
            session.flush()
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="atualizacao_biometrica_aprovada",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=linha.id,
                instante=agora,
                justificativa=justificativa,
                antes={"versao": versao_atual, "quantidade_ativa": len(ativos)},
                depois={"versao": versao_atual + 1, "conjunto_id": conjunto_novo.id},
            )
            resultado = conjunto_novo.versao
        return resultado

    def descartar_candidato_com_falha_sql(
        self, ator: AtorWeb, solicitacao_id: int, *, agora: dt.datetime
    ) -> tuple[str, ...]:
        """Descarta só a coleta candidata após rollback; a versão ativa é intocada."""
        with sessao(self._engine) as session:
            atual = _ator_atual(session, ator)
            if atual.papel != "admin":
                raise PermissionError(
                    "Somente administrador pode descartar atualização."
                )
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if linha is None or linha.tipo != "atualizacao":
                raise LookupError("Atualização biométrica não encontrada.")
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.solicitacao_id == linha.id)
                .with_for_update()
            )
            if conjunto is None or conjunto.estado != "pendente":
                return ()
            caminhos = tuple(
                session.scalars(
                    select(models.ReferenciaFacialWeb.caminho_privado_relativo)
                    .where(models.ReferenciaFacialWeb.conjunto_id == conjunto.id)
                    .order_by(models.ReferenciaFacialWeb.ordinal)
                ).all()
            )
            conjunto.estado = "descartado"
            conjunto.aluno_id = None
            conjunto.versao = None
            linha.estado = "cancelada"
            linha.decidida_em = agora
            linha.decidida_por_conta_id = atual.conta_id
            linha.justificativa = "Nova coleta necessária após falha de ativação."
            session.flush()
            _auditar(
                session,
                ator_id=atual.conta_id,
                acao="atualizacao_biometrica_cancelada_falha_sql",
                alvo_tipo="solicitacao_cadastro_web",
                alvo_id=linha.id,
                instante=agora,
                justificativa=linha.justificativa,
                antes={"estado": "pendente_aprovacao"},
                depois={"estado": "cancelada", "conjunto_descartado": True},
            )
            return caminhos

    def obter_referencias_ativas(
        self, aluno_ids: tuple[int, ...] | None = None
    ) -> tuple[ReferenciaAtiva, ...]:
        """Leitura interna do worker; consulta somente a versão marcada ativa."""
        with sessao(self._engine) as session:
            consulta = (
                select(models.ConjuntoReferenciasWeb, models.ReferenciaFacialWeb)
                .join(
                    models.ReferenciaFacialWeb,
                    models.ReferenciaFacialWeb.conjunto_id
                    == models.ConjuntoReferenciasWeb.id,
                )
                .where(models.ConjuntoReferenciasWeb.estado == "ativo")
                .order_by(
                    models.ConjuntoReferenciasWeb.aluno_id,
                    models.ReferenciaFacialWeb.ordinal,
                )
            )
            if aluno_ids is not None:
                if not aluno_ids:
                    return ()
                consulta = consulta.where(
                    models.ConjuntoReferenciasWeb.aluno_id.in_(aluno_ids)
                )
            linhas = session.execute(consulta).all()
            return tuple(
                ReferenciaAtiva(
                    aluno_id=conjunto.aluno_id,
                    conjunto_id=conjunto.id,
                    versao=conjunto.versao,
                    embedding=FaceEmbedding.de_bytes(
                        referencia.embedding, referencia.embedding_modelo
                    ),
                    ordinal=referencia.ordinal,
                )
                for conjunto, referencia in linhas
                if conjunto.aluno_id is not None and conjunto.versao is not None
            )

    def limpar_arquivos_provisorios(self, solicitacao_id: int) -> tuple[str, ...]:
        with sessao(self._engine) as session:
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb).where(
                    models.ConjuntoReferenciasWeb.solicitacao_id == solicitacao_id
                )
            )
            if conjunto is None or conjunto.estado != "descartado":
                return ()
            return tuple(
                session.scalars(
                    select(models.ReferenciaFacialWeb.caminho_privado_relativo)
                    .where(models.ReferenciaFacialWeb.conjunto_id == conjunto.id)
                    .order_by(models.ReferenciaFacialWeb.ordinal)
                ).all()
            )

    def confirmar_limpeza_provisoria(
        self, solicitacao_id: int, *, agora: dt.datetime
    ) -> None:
        with sessao(self._engine) as session:
            linha = session.scalar(
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.id == solicitacao_id)
                .with_for_update()
            )
            if linha is None:
                raise LookupError("Solicitação não encontrada.")
            conjunto = session.scalar(
                select(models.ConjuntoReferenciasWeb)
                .where(models.ConjuntoReferenciasWeb.solicitacao_id == linha.id)
                .with_for_update()
            )
            if conjunto is not None:
                if conjunto.estado != "descartado":
                    raise ValueError("A limpeza não pode remover um conjunto ativo.")
                session.query(models.ReferenciaFacialWeb).filter_by(
                    conjunto_id=conjunto.id
                ).delete(synchronize_session=False)
            linha.limpa_em = _utc(agora)

    def preparar_limpeza_provisoria(
        self, agora: dt.datetime, limite: int
    ) -> tuple[int, ...]:
        with sessao(self._engine) as session:
            estados_abertos = ("em_coleta", "em_validacao", "pendente_aprovacao")
            conjunto_descartado = (
                select(models.ConjuntoReferenciasWeb.id)
                .where(
                    models.ConjuntoReferenciasWeb.solicitacao_id
                    == models.SolicitacaoCadastroWeb.id,
                    models.ConjuntoReferenciasWeb.estado == "descartado",
                )
                .exists()
            )
            elegivel = or_(
                models.SolicitacaoCadastroWeb.estado.in_(
                    ("rejeitada", "cancelada", "expirada")
                ),
                and_(
                    models.SolicitacaoCadastroWeb.estado.in_(estados_abertos),
                    models.SolicitacaoCadastroWeb.expira_em <= agora,
                ),
                and_(
                    models.SolicitacaoCadastroWeb.estado == "aprovada",
                    conjunto_descartado,
                ),
            )
            consulta = (
                select(models.SolicitacaoCadastroWeb)
                .where(models.SolicitacaoCadastroWeb.limpa_em.is_(None), elegivel)
                .order_by(models.SolicitacaoCadastroWeb.expira_em)
                .limit(limite)
                .with_for_update(skip_locked=True)
            )
            linhas = session.scalars(consulta).all()
            ids: list[int] = []
            for linha in linhas:
                conjunto = session.scalar(
                    select(models.ConjuntoReferenciasWeb)
                    .where(models.ConjuntoReferenciasWeb.solicitacao_id == linha.id)
                    .with_for_update()
                )
                if conjunto is None:
                    encerrada = linha.estado in (
                        "rejeitada",
                        "cancelada",
                        "expirada",
                        "aprovada",
                    )
                    expirou = (
                        linha.estado
                        in ("em_coleta", "em_validacao", "pendente_aprovacao")
                        and _utc(linha.expira_em) <= agora
                    )
                    if encerrada or expirou:
                        if expirou:
                            estado_anterior = linha.estado
                            linha.estado = "expirada"
                            linha.decidida_em = agora
                            _auditar(
                                session,
                                ator_id=None,
                                acao="solicitacao_cadastro_web_expirada",
                                alvo_tipo="solicitacao_cadastro_web",
                                alvo_id=linha.id,
                                instante=agora,
                                antes={"estado": estado_anterior},
                                depois={"estado": "expirada"},
                            )
                        linha.limpa_em = agora
                    continue
                if conjunto.estado in ("ativo", "substituido"):
                    continue
                aprovado_existente = (
                    linha.estado == "aprovada" and conjunto.estado == "descartado"
                )
                encerrada = linha.estado in ("rejeitada", "cancelada", "expirada")
                expirou = (
                    linha.estado in ("em_coleta", "em_validacao", "pendente_aprovacao")
                    and _utc(linha.expira_em) <= agora
                )
                if aprovado_existente or encerrada or expirou:
                    if expirou:
                        estado_anterior = linha.estado
                        linha.estado = "expirada"
                        linha.decidida_em = agora
                        _auditar(
                            session,
                            ator_id=None,
                            acao="solicitacao_cadastro_web_expirada",
                            alvo_tipo="solicitacao_cadastro_web",
                            alvo_id=linha.id,
                            instante=agora,
                            antes={"estado": estado_anterior},
                            depois={"estado": "expirada"},
                        )
                    conjunto.estado = "descartado"
                    ids.append(linha.id)
            return tuple(ids)
