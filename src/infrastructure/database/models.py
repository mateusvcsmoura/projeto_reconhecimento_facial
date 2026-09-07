"""Modelos ORM — schema PostgreSQL do dominio atual.

Escopo deliberado: apenas as entidades que ja existem no sistema
(`alunos`, `presencas`). Colunas de embedding e consentimento entram nas
Fases 5 e 6, com suas proprias migrations.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Identity,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    func,
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

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )

    # Chave de negocio, vinda de fora do sistema. Separada da PK interna
    # porque no SQLite `id` acumulava PK + matricula + biometria_id.
    matricula: Mapped[str] = mapped_column(String(32), nullable=False)
    nome: Mapped[str] = mapped_column(String(255), nullable=False)

    # Caminho RELATIVO a STORAGE_DIR. Caminho absoluto no banco torna o
    # dump nao portavel — foi o que quebrou os dados legados.
    foto_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    criado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    presencas: Mapped[list["Presenca"]] = relationship(
        back_populates="aluno", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("matricula", name="uq_alunos_matricula"),
        CheckConstraint("length(btrim(nome)) > 0", name="nome_nao_vazio"),
        CheckConstraint("length(btrim(matricula)) > 0", name="matricula_nao_vazia"),
    )


class Presenca(Base):
    __tablename__ = "presencas"

    id: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), primary_key=True
    )
    aluno_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("alunos.id", ondelete="CASCADE"),
        nullable=False,
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
        # A regra "uma presenca por aluno por dia" passa a ser garantida pelo
        # banco. Substitui o SELECT-depois-INSERT do prototipo, que era
        # sujeito a corrida e cego para os dados legados.
        UniqueConstraint("aluno_id", "data_referencia", name="uq_presencas_aluno_dia"),
        Index("ix_presencas_data_referencia", "data_referencia"),
    )
