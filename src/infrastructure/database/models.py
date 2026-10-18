"""Modelos ORM -- schema PostgreSQL.

Colunas de consentimento e retencao entram na Fase 6, com sua propria
migration.
"""

from __future__ import annotations

import datetime as dt

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

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
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


class SolicitacaoCadastroWeb(Base):
    """Pedido isolado de cadastro/troca; nao e um Aluno ativo."""

    __tablename__ = "solicitacoes_cadastro_web"

    id: Mapped[int] = mapped_column(BIGINT_ID, Identity(always=True), primary_key=True)
    tipo: Mapped[str] = mapped_column(String(16), nullable=False)
    estado: Mapped[str] = mapped_column(String(24), nullable=False)
    convite_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
        Index("ix_solicitacoes_cadastro_web_turma_estado", "turma_id", "estado"),
        Index("ix_solicitacoes_cadastro_web_estado_expira", "estado", "expira_em"),
        Index("ix_solicitacoes_cadastro_web_aluno", "aluno_id"),
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

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
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

    # Instante exato do registro.
    registrado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # O "dia" da regra de negocio, calculado pela aplicacao em APP_TIMEZONE.
    # Coluna propria — nao expressao — porque `AT TIME ZONE <literal>` sobre
    # timestamptz e STABLE, nao IMMUTABLE, e portanto nao pode ser coluna
    # gerada nem indexada diretamente.
    data_referencia: Mapped[dt.date] = mapped_column(Date, nullable=False)

    aluno: Mapped[Aluno] = relationship(back_populates="presencas")

    __table_args__ = (
        ForeignKeyConstraint(
            ["turma_id", "aluno_id"],
            ["aluno_turma.turma_id", "aluno_turma.aluno_id"],
            name="fk_presencas_turma_aluno_aluno_turma",
            ondelete="CASCADE",
        ),
        # Presencas novas sao unicas dentro da turma; as linhas legadas com
        # turma_id NULL usam um indice unico parcial independente.
        UniqueConstraint(
            "turma_id",
            "aluno_id",
            "data_referencia",
            name="uq_presencas_turma_aluno_dia",
        ),
        Index(
            "uq_presencas_legado_aluno_dia",
            "aluno_id",
            "data_referencia",
            unique=True,
            postgresql_where=text("turma_id IS NULL"),
        ),
        Index("ix_presencas_turma_data", "turma_id", "data_referencia"),
        Index("ix_presencas_data_referencia", "data_referencia"),
    )
