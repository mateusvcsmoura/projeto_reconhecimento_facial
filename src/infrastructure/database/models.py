"""Modelos ORM -- schema PostgreSQL.

Colunas de consentimento e retencao entram na Fase 6, com sua propria
migration.
"""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Nomes deterministicos para constraints e indices: sem isso o downgrade
# do Alembic depende de nomes gerados pelo banco e deixa de ser confiavel.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


BIGINT_ID = BigInteger().with_variant(Integer, "sqlite")


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)

    # Chave de negocio, vinda de fora do sistema. Separada da PK interna
    # porque no SQLite `id` acumulava PK + matricula + biometria_id.
    matricula: Mapped[str] = mapped_column(String(32), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    # Caminho RELATIVO a STORAGE_DIR. Caminho absoluto no banco torna o
    # dump nao portavel — foi o que quebrou os dados legados.
    foto_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Embedding facial: float32 little-endian, L2-normalizado.
    # Calculado uma vez, no cadastro, e reutilizado a cada reconhecimento.
    # O modelo fica gravado junto porque vetores de modelos diferentes nao
    # sao comparaveis -- misturar os dois produziria identificacao errada
    # em silencio.
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    embedding_modelo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_dim: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    # Momento em que o aluno consentiu com o tratamento do dado biometrico.
    # Nullable apenas para nao quebrar linhas anteriores a Fase 6; a
    # aplicacao nao cadastra sem consentimento.
    consentimento_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    presencas: Mapped[list[Presenca]] = relationship(
        back_populates="aluno", cascade="all, delete-orphan", passive_deletes=True
    )
    vinculos_turma: Mapped[list[AlunoTurma]] = relationship(
        back_populates="aluno", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("matricula", name="uq_alunos_matricula"),
        CheckConstraint("length(btrim(nome)) > 0", name="nome_nao_vazio"),
        CheckConstraint("length(btrim(matricula)) > 0", name="matricula_nao_vazia"),
        # Os tres campos do embedding andam juntos: ou todos preenchidos, ou
        # todos nulos. Um vetor sem o modelo que o gerou e inutilizavel.
        CheckConstraint(
            "(embedding IS NULL AND embedding_modelo IS NULL "
            "AND embedding_dim IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_modelo IS NOT NULL "
            "AND embedding_dim IS NOT NULL AND embedding_dim > 0)",
            name="embedding_completo",
        ),
    )


class Turma(Base):
    __tablename__ = "turmas"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    materia: Mapped[str] = mapped_column(String(120), nullable=False)
    periodo: Mapped[str] = mapped_column(String(10), nullable=False)
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    excluida_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    responsavel_professor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("professores_web.id", ondelete="RESTRICT"),
        nullable=True,
    )

    vinculos: Mapped[list[AlunoTurma]] = relationship(
        back_populates="turma", passive_deletes=True
    )
    responsavel: Mapped[ProfessorWeb | None] = relationship(
        back_populates="turmas_responsaveis"
    )

    __table_args__ = (
        CheckConstraint("length(btrim(materia)) > 0", name="materia_nao_vazia"),
        CheckConstraint(
            "periodo IN ('matutino', 'diurno', 'noturno')", name="periodo_valido"
        ),
        Index("ix_turmas_responsavel_professor_id", "responsavel_professor_id"),
    )


class ContaWeb(Base):
    """Conta de acesso ao runtime web; nao representa cadastro biometrico."""

    __tablename__ = "contas_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    usuario_normalizado: Mapped[str] = mapped_column(String(80), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    papel: Mapped[str] = mapped_column(String(16), nullable=False)
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    troca_senha_obrigatoria: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    versao_credencial: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    credencial_temporaria_expira_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credencial_temporaria_usada_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    professor: Mapped[ProfessorWeb | None] = relationship(
        back_populates="conta", uselist=False
    )
    sessoes: Mapped[list[SessaoAutenticacaoWeb]] = relationship(
        back_populates="conta", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint(
            "usuario_normalizado", name="uq_contas_web_usuario_normalizado"
        ),
        CheckConstraint("length(usuario_normalizado) > 0", name="usuario_nao_vazio"),
        CheckConstraint("papel IN ('professor', 'admin')", name="papel_valido"),
        CheckConstraint("versao_credencial > 0", name="versao_credencial_positiva"),
    )


class ProfessorWeb(Base):
    """Perfil de professor que pode ser responsavel por turmas web."""

    __tablename__ = "professores_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    conta_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contas_web.id", ondelete="RESTRICT"),
        nullable=False,
    )
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    conta: Mapped[ContaWeb] = relationship(back_populates="professor")
    turmas_responsaveis: Mapped[list[Turma]] = relationship(
        back_populates="responsavel"
    )

    __table_args__ = (UniqueConstraint("conta_id", name="uq_professores_web_conta_id"),)


class SessaoAutenticacaoWeb(Base):
    """Sessao opaca: so hashes do cookie e token CSRF sao persistidos."""

    __tablename__ = "sessoes_autenticacao_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    conta_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contas_web.id", ondelete="CASCADE"),
        nullable=False,
    )
    versao_credencial: Mapped[int] = mapped_column(Integer, nullable=False)
    criada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    atividade_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expira_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    conta: Mapped[ContaWeb] = relationship(back_populates="sessoes")

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_sessoes_autenticacao_web_token_hash"),
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256"),
        CheckConstraint("length(csrf_hash) = 64", name="csrf_hash_sha256"),
        CheckConstraint("expira_em > criada_em", name="expiracao_absoluta_valida"),
        Index("ix_sessoes_autenticacao_web_conta_id", "conta_id"),
        Index("ix_sessoes_autenticacao_web_expira_em", "expira_em"),
    )


class LimiteLoginWeb(Base):
    """Buckets de rate limit identificados por HMAC de conta e endereco IP."""

    __tablename__ = "limites_login_web"

    chave_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    janela_iniciada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    falhas: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    bloqueada_ate: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tentativa_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint("length(chave_hash) = 64", name="chave_hash_sha256"),
        CheckConstraint("falhas >= 0", name="falhas_nao_negativas"),
    )


class EventoAuditoriaWeb(Base):
    """Registro append-only sem credenciais, tokens ou dados biometricos."""

    __tablename__ = "eventos_auditoria_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    ator_conta_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    acao: Mapped[str] = mapped_column(String(100), nullable=False)
    alvo_tipo: Mapped[str] = mapped_column(String(64), nullable=False)
    alvo_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instante: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    justificativa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    antes: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    depois: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        CheckConstraint("length(acao) > 0", name="acao_nao_vazia"),
        CheckConstraint("length(alvo_tipo) > 0", name="alvo_tipo_nao_vazio"),
        CheckConstraint("length(alvo_id) > 0", name="alvo_id_nao_vazio"),
        Index("ix_eventos_auditoria_web_ator_instante", "ator_conta_id", "instante"),
        Index(
            "ix_eventos_auditoria_web_alvo_instante", "alvo_tipo", "alvo_id", "instante"
        ),
    )


class SessaoPresencaWeb(Base):
    """Janela de chamada criada por professor para uma turma."""

    __tablename__ = "sessoes_presenca_web"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    turma_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    criada_por_conta_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    titulo: Mapped[str] = mapped_column(String(120), nullable=False)
    inicio_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fim_em: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    criada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revogada_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revogada_por_conta_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    versao: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )

    __table_args__ = (
        UniqueConstraint("id", "turma_id", name="uq_sessoes_presenca_id_turma"),
        CheckConstraint(
            "length(btrim(titulo)) BETWEEN 1 AND 120", name="titulo_valido"
        ),
        CheckConstraint("fim_em > inicio_em", name="janela_valida"),
        CheckConstraint("versao > 0", name="versao_positiva"),
        CheckConstraint(
            "(revogada_em IS NULL AND revogada_por_conta_id IS NULL) OR "
            "(revogada_em IS NOT NULL AND revogada_por_conta_id IS NOT NULL)",
            name="revogacao_coerente",
        ),
        ForeignKeyConstraint(
            ["turma_id"],
            ["turmas.id"],
            name="fk_sessoes_presenca_turma",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["criada_por_conta_id"],
            ["contas_web.id"],
            name="fk_sessoes_presenca_criador",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["revogada_por_conta_id"],
            ["contas_web.id"],
            name="fk_sessoes_presenca_revogador",
            ondelete="RESTRICT",
        ),
        Index("ix_sessoes_presenca_turma_inicio", "turma_id", "inicio_em"),
    )


class LinkCadastroWeb(Base):
    """Convite compartilhavel com hash do token e finalidade fixa."""

    __tablename__ = "links_cadastro_web"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    turma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turmas.id", ondelete="RESTRICT"), nullable=False
    )
    emitido_por_conta_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("contas_web.id", ondelete="RESTRICT"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    finalidade: Mapped[str] = mapped_column(String(16), nullable=False)
    sessao_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expira_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finalidade_ate: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revogado_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revogado_por_conta_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contas_web.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_links_cadastro_web_token_hash"),
        UniqueConstraint(
            "id", "sessao_id", "turma_id", name="uq_links_cadastro_sessao_turma"
        ),
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256"),
        CheckConstraint(
            "(finalidade = 'cadastro' AND sessao_id IS NULL) OR "
            "(finalidade = 'presenca' AND sessao_id IS NOT NULL)",
            name="finalidade_sessao_coerente",
        ),
        CheckConstraint("expira_em > criado_em", name="expiracao_valida"),
        CheckConstraint("finalidade_ate > criado_em", name="fim_finalidade_valido"),
        CheckConstraint(
            "(revogado_em IS NULL AND revogado_por_conta_id IS NULL) OR "
            "(revogado_em IS NOT NULL AND revogado_por_conta_id IS NOT NULL)",
            name="revogacao_coerente",
        ),
        Index("ix_links_cadastro_web_turma_expira", "turma_id", "expira_em"),
        ForeignKeyConstraint(
            ["sessao_id", "turma_id"],
            ["sessoes_presenca_web.id", "sessoes_presenca_web.turma_id"],
            name="fk_links_presenca_sessao_turma",
            ondelete="RESTRICT",
        ),
    )


class CredencialLinkCadastroWeb(Base):
    """Credencial efemera, de uso unico para associar uma solicitacao ao link."""

    __tablename__ = "credenciais_link_cadastro_web"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    link_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("links_cadastro_web.id", ondelete="CASCADE"),
        nullable=False,
    )
    criada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expira_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    solicitacao_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "solicitacoes_cadastro_web.id",
            name="fk_cred_link_solicitacao",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("length(token_hash) = 64", name="token_hash_sha256"),
        CheckConstraint("expira_em > criada_em", name="expiracao_valida"),
        UniqueConstraint("solicitacao_id", name="uq_credenciais_link_solicitacao"),
        Index("ix_credenciais_link_expira", "expira_em"),
    )


class SolicitacaoCadastroWeb(Base):
    """Pedido isolado de cadastro/troca; nao e um Aluno ativo."""

    __tablename__ = "solicitacoes_cadastro_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), nullable=False)
    convite_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    link_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("links_cadastro_web.id", ondelete="RESTRICT"),
        nullable=True,
    )
    job_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs_faciais_web.id", ondelete="RESTRICT"),
        nullable=True,
    )
    credencial_captura_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    credencial_captura_expira_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    desafio_nonce_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    desafio_direcao: Mapped[str | None] = mapped_column(String(12), nullable=True)
    desafio_expira_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    turma_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turmas.id", ondelete="RESTRICT"), nullable=False
    )
    aluno_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alunos.id", ondelete="RESTRICT"), nullable=True
    )
    matricula: Mapped[str | None] = mapped_column(String(32), nullable=True)
    nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consentimento_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consentimento_versao: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expira_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    criada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decidida_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decidida_por_conta_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    metodo_identidade: Mapped[str | None] = mapped_column(String(40), nullable=True)
    justificativa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    limpa_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint("tipo IN ('cadastro', 'atualizacao')", name="tipo_valido"),
        CheckConstraint(
            "estado IN ('em_coleta', 'em_validacao', 'pendente_aprovacao', "
            "'aprovada', 'rejeitada', 'cancelada', 'expirada')",
            name="estado_valido",
        ),
        CheckConstraint(
            "(tipo = 'cadastro' AND aluno_id IS NULL AND matricula IS NOT NULL "
            "AND nome IS NOT NULL AND convite_ref IS NOT NULL) OR "
            "(tipo = 'atualizacao' AND aluno_id IS NOT NULL AND matricula IS NULL "
            "AND nome IS NULL AND convite_ref IS NULL)",
            name="identificacao_coerente",
        ),
        CheckConstraint(
            "(consentimento_em IS NULL AND consentimento_versao IS NULL) OR "
            "(consentimento_em IS NOT NULL AND consentimento_versao IS NOT NULL "
            "AND length(consentimento_versao) > 0)",
            name="consentimento_coerente",
        ),
        CheckConstraint("expira_em > criada_em", name="expiracao_valida"),
        CheckConstraint(
            "(credencial_captura_hash IS NULL AND "
            "credencial_captura_expira_em IS NULL) OR "
            "(length(credencial_captura_hash) = 64 AND "
            "credencial_captura_expira_em IS NOT NULL AND "
            "credencial_captura_expira_em > criada_em)",
            name="credencial_captura_coerente",
        ),
        CheckConstraint(
            "(desafio_nonce_hash IS NULL AND desafio_direcao IS NULL AND "
            "desafio_expira_em IS NULL) OR "
            "(length(desafio_nonce_hash) = 64 AND "
            "desafio_direcao IN ('esquerda', 'direita') AND "
            "desafio_expira_em IS NOT NULL AND desafio_expira_em > criada_em)",
            name="desafio_cadastro_coerente",
        ),
        UniqueConstraint(
            "credencial_captura_hash",
            name="uq_solicitacoes_cadastro_web_credencial_captura",
        ),
        Index("ix_solicitacoes_cadastro_web_turma_estado", "turma_id", "estado"),
        Index("ix_solicitacoes_cadastro_web_estado_expira", "estado", "expira_em"),
        Index("ix_solicitacoes_cadastro_web_aluno", "aluno_id"),
        UniqueConstraint("job_id", name="uq_solicitacoes_cadastro_web_job"),
        Index(
            "ix_solicitacoes_cadastro_web_link_estado",
            "link_id",
            "estado",
        ),
        Index(
            "ix_solicitacoes_cadastro_web_desafio_expira",
            "desafio_expira_em",
        ),
    )


class ConjuntoReferenciasWeb(Base):
    """Trinca pertencente a uma solicitação e, após aprovação, a uma versão."""

    __tablename__ = "conjuntos_referencias_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    solicitacao_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    aluno_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alunos.id", ondelete="RESTRICT"), nullable=True
    )
    versao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    job_id: Mapped[str] = mapped_column(String(36), nullable=False)
    embedding_modelo: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ativado_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["solicitacao_id"],
            ["solicitacoes_cadastro_web.id"],
            name="fk_conj_ref_solicitacao",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "solicitacao_id", name="uq_conjuntos_referencias_web_solicitacao"
        ),
        UniqueConstraint("job_id", name="uq_conjuntos_referencias_web_job"),
        UniqueConstraint(
            "aluno_id", "versao", name="uq_conjuntos_referencias_web_aluno_versao"
        ),
        UniqueConstraint(
            "id",
            "aluno_id",
            "versao",
            name="uq_conjuntos_referencias_id_aluno_versao",
        ),
        CheckConstraint(
            "estado IN ('pendente', 'ativo', 'substituido', 'descartado')",
            name="estado_valido",
        ),
        CheckConstraint(
            "(estado = 'pendente' AND aluno_id IS NULL AND versao IS NULL) OR "
            "(estado = 'descartado' AND ((aluno_id IS NULL AND versao IS NULL) OR "
            "(aluno_id IS NOT NULL AND versao IS NOT NULL AND versao > 0))) OR "
            "(estado IN ('ativo', 'substituido') AND aluno_id IS NOT NULL "
            "AND versao IS NOT NULL AND versao > 0)",
            name="versao_coerente",
        ),
        CheckConstraint("embedding_dim = 512", name="embedding_dim_512"),
        Index(
            "uq_conjuntos_referencias_web_aluno_ativo",
            "aluno_id",
            unique=True,
            postgresql_where=text("estado = 'ativo'"),
            sqlite_where=text("estado = 'ativo'"),
        ),
        Index(
            "ix_conjuntos_referencias_web_solicitacao_estado",
            "solicitacao_id",
            "estado",
        ),
        Index("ix_conjuntos_referencias_web_aluno_estado", "aluno_id", "estado"),
    )


class ReferenciaFacialWeb(Base):
    """Recorte privado e embedding normalizado; nunca retornado ao professor."""

    __tablename__ = "referencias_faciais_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    conjunto_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    caminho_privado_relativo: Mapped[str] = mapped_column(String(512), nullable=False)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    embedding_modelo: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    consentimento_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    consentimento_versao: Mapped[str] = mapped_column(String(64), nullable=False)
    capturada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["conjunto_id"],
            ["conjuntos_referencias_web.id"],
            name="fk_ref_facial_conjunto",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "conjunto_id", "ordinal", name="uq_referencias_faciais_web_conjunto_ordinal"
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 3", name="ordinal_valido"),
        CheckConstraint("embedding_dim = 512", name="embedding_dim_512"),
        CheckConstraint("length(embedding) = 2048", name="embedding_float32_512"),
        CheckConstraint(
            "length(caminho_privado_relativo) > 0", name="caminho_nao_vazio"
        ),
        CheckConstraint("length(embedding_modelo) > 0", name="modelo_nao_vazio"),
        CheckConstraint(
            "length(consentimento_versao) > 0", name="consentimento_versao_valida"
        ),
        Index("ix_referencias_faciais_web_conjunto", "conjunto_id"),
    )


class JobFacialWeb(Base):
    """Estado e referência temporária de um trabalho facial web."""

    __tablename__ = "jobs_faciais_web"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    dono_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    estado: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotencia_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    credencial_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    manifesto: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    bytes_reservados: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prazo_reserva: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    prazo_execucao: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    criada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    atualizada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    enfileirada_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    iniciada_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finalizada_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lease_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expira_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelamento_solicitado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    resultado_codigo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("length(dono_id) BETWEEN 1 AND 128", name="dono_valido"),
        CheckConstraint("tipo IN ('cadastro', 'presenca')", name="tipo_valido"),
        CheckConstraint(
            "estado IN ('recebida', 'enfileirada', 'processando', 'concluida', "
            "'rejeitada', 'cancelada', 'expirada')",
            name="estado_valido",
        ),
        CheckConstraint(
            "length(idempotencia_hash) = 64 AND length(credencial_hash) = 64",
            name="hashes_validos",
        ),
        CheckConstraint("bytes_reservados > 0", name="reserva_bytes_positiva"),
        CheckConstraint("prazo_reserva > criada_em", name="prazo_reserva_valido"),
        CheckConstraint("prazo_execucao > criada_em", name="prazo_execucao_valido"),
        CheckConstraint(
            "(estado = 'processando' AND lease_hash IS NOT NULL "
            "AND lease_expira_em IS NOT NULL AND manifesto IS NOT NULL) OR "
            "(estado <> 'processando' AND lease_hash IS NULL "
            "AND lease_expira_em IS NULL)",
            name="lease_coerente",
        ),
        CheckConstraint(
            "(estado IN ('enfileirada', 'processando') AND manifesto IS NOT NULL) "
            "OR estado IN ('recebida', 'concluida', 'rejeitada', 'cancelada', "
            "'expirada')",
            name="manifesto_coerente",
        ),
        UniqueConstraint(
            "dono_id",
            "tipo",
            "idempotencia_hash",
            name="uq_jobs_faciais_web_idempotencia",
        ),
        Index(
            "ix_jobs_faciais_web_fila_fifo",
            "estado",
            "enfileirada_em",
            "id",
        ),
        Index(
            "ix_jobs_faciais_web_prazos",
            "estado",
            "prazo_reserva",
            "prazo_execucao",
        ),
        Index(
            "uq_jobs_faciais_web_ativo",
            "estado",
            unique=True,
            postgresql_where=text("estado = 'processando'"),
            sqlite_where=text("estado = 'processando'"),
        ),
    )


class DesafioVerificacaoWeb(Base):
    """Estado efêmero, sem frames, landmarks ou embeddings do desafio 1:1."""

    __tablename__ = "desafios_verificacao_web"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("jobs_faciais_web.id", name="fk_desafio_job", ondelete="CASCADE"),
        primary_key=True,
    )
    aluno_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alunos.id", name="fk_desafio_aluno", ondelete="RESTRICT"),
        nullable=False,
    )
    conjunto_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "conjuntos_referencias_web.id",
            name="fk_desafio_conjunto",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    versao_referencia: Mapped[int] = mapped_column(Integer, nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    direcao: Mapped[str] = mapped_column(String(12), nullable=False)
    expira_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    etapa_validada: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    etapa_recebida: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    atualizada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    motivo: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        CheckConstraint("aluno_id > 0", name="aluno_positivo"),
        CheckConstraint("conjunto_id > 0", name="conjunto_positivo"),
        CheckConstraint("versao_referencia > 0", name="versao_positiva"),
        CheckConstraint("length(nonce_hash) = 64", name="nonce_hash_valido"),
        CheckConstraint("direcao IN ('esquerda', 'direita')", name="direcao_valida"),
        CheckConstraint(
            "etapa_validada BETWEEN 0 AND 3 AND etapa_recebida BETWEEN 0 AND 3",
            name="etapas_validas",
        ),
        CheckConstraint(
            "estado IN ('aguardando_etapa', 'etapa_recebida', 'concluido', "
            "'rejeitado', 'expirado')",
            name="estado_valido",
        ),
        CheckConstraint(
            "etapa_recebida = etapa_validada OR "
            "(estado IN ('etapa_recebida', 'rejeitado', 'expirado') "
            "AND etapa_recebida = etapa_validada + 1)",
            name="sequencia_coerente",
        ),
        Index("ix_desafios_verificacao_web_estado_expira", "estado", "expira_em"),
    )


class TentativaPresencaWeb(Base):
    """Emissão contável de verificação 1:1 vinculada a um job facial."""

    __tablename__ = "tentativas_presenca_web"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    sessao_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    turma_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    aluno_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    conjunto_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    versao_referencia: Mapped[int] = mapped_column(Integer, nullable=False)
    versao_sessao: Mapped[int] = mapped_column(Integer, nullable=False)
    link_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    idempotencia_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False)
    iniciada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    prazo_envio: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recebida_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    concluida_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_tecnico: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        ForeignKeyConstraint(
            ["id"],
            ["jobs_faciais_web.id"],
            name="fk_tentativas_presenca_job",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["sessao_id", "turma_id"],
            ["sessoes_presenca_web.id", "sessoes_presenca_web.turma_id"],
            name="fk_tentativas_presenca_sessao_turma",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["turma_id", "aluno_id"],
            ["aluno_turma.turma_id", "aluno_turma.aluno_id"],
            name="fk_tentativas_presenca_vinculo",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["conjunto_id", "aluno_id", "versao_referencia"],
            [
                "conjuntos_referencias_web.id",
                "conjuntos_referencias_web.aluno_id",
                "conjuntos_referencias_web.versao",
            ],
            name="fk_tentativas_presenca_conjunto_ativo",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["link_id", "sessao_id", "turma_id"],
            [
                "links_cadastro_web.id",
                "links_cadastro_web.sessao_id",
                "links_cadastro_web.turma_id",
            ],
            name="fk_tentativas_presenca_link_escopo",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "sessao_id", "aluno_id", "ordinal", name="uq_tentativas_presenca_ordinal"
        ),
        UniqueConstraint(
            "sessao_id",
            "aluno_id",
            "idempotencia_hash",
            name="uq_tentativas_presenca_idempotencia",
        ),
        CheckConstraint("ordinal >= 1", name="ordinal_valido"),
        CheckConstraint(
            "versao_referencia > 0 AND versao_sessao > 0", name="versoes_positivas"
        ),
        CheckConstraint(
            "length(idempotencia_hash) = 64", name="idempotencia_hash_valida"
        ),
        CheckConstraint(
            "estado IN ('iniciada', 'recebida', 'enfileirada', 'processando', "
            "'concluida', 'expirada', 'rejeitada')",
            name="estado_valido",
        ),
        CheckConstraint("prazo_envio > iniciada_em", name="prazo_valido"),
        CheckConstraint(
            "(estado IN ('iniciada', 'recebida', 'enfileirada', 'processando') "
            "AND concluida_em IS NULL) OR "
            "(estado IN ('concluida', 'expirada', 'rejeitada') "
            "AND concluida_em IS NOT NULL)",
            name="terminalidade_coerente",
        ),
        Index(
            "uq_tentativas_presenca_ativa",
            "sessao_id",
            "aluno_id",
            unique=True,
            postgresql_where=text(
                "estado IN ('iniciada', 'recebida', 'enfileirada', 'processando')"
            ),
            sqlite_where=text(
                "estado IN ('iniciada', 'recebida', 'enfileirada', 'processando')"
            ),
        ),
        Index("ix_tentativas_presenca_estado", "estado", "prazo_envio"),
    )


class LimitePresencaWeb(Base):
    """Contador agregado; chaves são hashes e nunca armazenam IP bruto."""

    __tablename__ = "limites_presenca_web"

    chave_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    janela_iniciada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    quantidade: Mapped[int] = mapped_column(Integer, nullable=False)
    bloqueado_ate: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        CheckConstraint("length(chave_hash) = 64", name="chave_hash_valida"),
        CheckConstraint("quantidade >= 0", name="quantidade_nao_negativa"),
        Index("ix_limites_presenca_atualizado", "atualizado_em"),
    )


class RecebimentoTentativaPresencaWeb(Base):
    """Hash do payload recebido por etapa; a imagem permanece temporária."""

    __tablename__ = "recebimentos_tentativa_presenca_web"

    tentativa_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    ordinal: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    recebido_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["tentativa_id"],
            ["tentativas_presenca_web.id"],
            name="fk_recebimentos_tentativa_web_tentativa",
            ondelete="CASCADE",
        ),
        CheckConstraint("ordinal BETWEEN 1 AND 3", name="ordinal_valido"),
        CheckConstraint("length(payload_hash) = 64", name="payload_hash_valido"),
    )


class AlunoTurma(Base):
    __tablename__ = "aluno_turma"

    turma_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("turmas.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    aluno_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alunos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ativo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    vinculado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    desvinculado_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    turma: Mapped[Turma] = relationship(back_populates="vinculos")
    aluno: Mapped[Aluno] = relationship(back_populates="vinculos_turma")

    __table_args__ = (
        CheckConstraint(
            "(ativo AND desvinculado_em IS NULL) OR "
            "(NOT ativo AND desvinculado_em IS NOT NULL)",
            name="estado_vinculo_coerente",
        ),
        Index("ix_aluno_turma_aluno_id", "aluno_id"),
    )


class Presenca(Base):
    __tablename__ = "presencas"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    aluno_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alunos.id", ondelete="CASCADE"),
        nullable=False,
    )
    turma_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("turmas.id", ondelete="RESTRICT"),
        nullable=True,
    )
    sessao_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    tentativa_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    # Instante exato do registro.
    registrado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # O "dia" da regra de negocio, calculado pela aplicacao em APP_TIMEZONE.
    # Coluna propria — nao expressao — porque `AT TIME ZONE <literal>` sobre
    # timestamptz e STABLE, nao IMMUTABLE, e portanto nao pode ser coluna
    # gerada nem indexada diretamente.
    data_referencia: Mapped[dt.date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'presente'")
    )
    origem: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'legado'")
    )
    versao: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1")
    )
    horario_evidencia: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    corrigida_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    corrigida_por_conta_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contas_web.id", ondelete="RESTRICT"),
        nullable=True,
    )

    aluno: Mapped[Aluno] = relationship(back_populates="presencas")

    __table_args__ = (
        CheckConstraint(
            "status IN ('presente', 'anulada')", name="status_presenca_valido"
        ),
        CheckConstraint(
            "origem IN ('biometrica', 'manual', 'legado')",
            name="origem_presenca_valida",
        ),
        CheckConstraint("versao > 0", name="versao_presenca_positiva"),
        CheckConstraint(
            "(corrigida_em IS NULL AND corrigida_por_conta_id IS NULL) OR "
            "(corrigida_em IS NOT NULL AND corrigida_por_conta_id IS NOT NULL)",
            name="correcao_presenca_coerente",
        ),
        CheckConstraint(
            "status != 'anulada' OR corrigida_em IS NOT NULL",
            name="anulacao_presenca_auditada",
        ),
        ForeignKeyConstraint(
            ["turma_id", "aluno_id"],
            ["aluno_turma.turma_id", "aluno_turma.aluno_id"],
            name="fk_presencas_turma_aluno_aluno_turma",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["sessao_id", "turma_id"],
            ["sessoes_presenca_web.id", "sessoes_presenca_web.turma_id"],
            name="fk_presencas_sessao_turma",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tentativa_id"],
            ["tentativas_presenca_web.id"],
            name="fk_presencas_tentativa",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "(sessao_id IS NULL AND tentativa_id IS NULL) OR "
            "(sessao_id IS NOT NULL AND turma_id IS NOT NULL AND "
            "((tentativa_id IS NOT NULL AND origem = 'biometrica') OR "
            "(tentativa_id IS NULL AND origem = 'manual' "
            "AND corrigida_em IS NOT NULL)))",
            name="sessao_tentativa_coerentes",
        ),
        Index(
            "uq_presencas_turma_aluno_dia",
            "turma_id",
            "aluno_id",
            "data_referencia",
            unique=True,
            postgresql_where=text("sessao_id IS NULL AND turma_id IS NOT NULL"),
            sqlite_where=text("sessao_id IS NULL AND turma_id IS NOT NULL"),
        ),
        Index(
            "uq_presencas_legado_aluno_dia",
            "aluno_id",
            "data_referencia",
            unique=True,
            postgresql_where=text("sessao_id IS NULL AND turma_id IS NULL"),
            sqlite_where=text("sessao_id IS NULL AND turma_id IS NULL"),
        ),
        Index(
            "uq_presencas_sessao_aluno",
            "sessao_id",
            "aluno_id",
            unique=True,
            postgresql_where=text("sessao_id IS NOT NULL"),
            sqlite_where=text("sessao_id IS NOT NULL"),
        ),
        UniqueConstraint("tentativa_id", name="uq_presencas_tentativa"),
        Index("ix_presencas_turma_data", "turma_id", "data_referencia"),
        Index("ix_presencas_data_referencia", "data_referencia"),
    )


class RevisaoPresencaWeb(Base):
    """Pedido de revisão de presença sem guardar qualquer dado biométrico."""

    __tablename__ = "revisoes_presenca_web"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    turma_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sessao_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    aluno_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    estado: Mapped[str] = mapped_column(String(12), nullable=False)
    justificativa_solicitacao: Mapped[str] = mapped_column(String(500), nullable=False)
    via_acessivel: Mapped[bool] = mapped_column(Boolean, nullable=False)
    solicitada_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    versao_presenca_base: Mapped[int] = mapped_column(Integer, nullable=False)
    decisao: Mapped[str | None] = mapped_column(String(12), nullable=True)
    justificativa_decisao: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    decidida_em: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decidida_por_conta_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("contas_web.id", ondelete="RESTRICT"),
        nullable=True,
    )

    __table_args__ = (
        CheckConstraint("estado IN ('aberta', 'decidida')", name="estado_valido"),
        CheckConstraint(
            "length(btrim(justificativa_solicitacao)) BETWEEN 1 AND 500",
            name="justificativa_solicitacao_valida",
        ),
        CheckConstraint("versao_presenca_base >= 0", name="versao_base_valida"),
        CheckConstraint(
            "(estado = 'aberta' AND decisao IS NULL AND decidida_em IS NULL "
            "AND decidida_por_conta_id IS NULL AND justificativa_decisao IS NULL) OR "
            "(estado = 'decidida' AND decisao IN ('presente', 'anulada') "
            "AND decidida_em IS NOT NULL AND decidida_por_conta_id IS NOT NULL "
            "AND justificativa_decisao IS NOT NULL)",
            name="decisao_coerente",
        ),
        ForeignKeyConstraint(
            ["sessao_id", "turma_id"],
            ["sessoes_presenca_web.id", "sessoes_presenca_web.turma_id"],
            name="fk_revisoes_presenca_sessao_turma",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["turma_id", "aluno_id"],
            ["aluno_turma.turma_id", "aluno_turma.aluno_id"],
            name="fk_revisoes_presenca_vinculo",
            ondelete="CASCADE",
        ),
        Index(
            "uq_revisoes_presenca_aberta",
            "sessao_id",
            "aluno_id",
            unique=True,
            postgresql_where=text("estado = 'aberta'"),
            sqlite_where=text("estado = 'aberta'"),
        ),
        Index("ix_revisoes_presenca_turma_estado", "turma_id", "estado"),
        Index("ix_revisoes_presenca_aluno_sessao", "aluno_id", "sessao_id"),
    )
