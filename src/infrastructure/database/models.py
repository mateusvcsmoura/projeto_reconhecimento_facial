"""Modelos ORM -- schema PostgreSQL.

Colunas de consentimento e retencao entram na Fase 6, com sua propria
migration.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    LargeBinary,
    MetaData,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
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


class Aluno(Base):
    __tablename__ = "alunos"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)

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

    vinculos: Mapped[list[AlunoTurma]] = relationship(
        back_populates="turma", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint("length(btrim(materia)) > 0", name="materia_nao_vazia"),
        CheckConstraint(
            "periodo IN ('matutino', 'diurno', 'noturno')", name="periodo_valido"
        ),
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
