"""estado temporário de desafio de verificação 1:1

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "desafios_verificacao_web",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=False),
        sa.Column("conjunto_id", sa.BigInteger(), nullable=False),
        sa.Column("versao_referencia", sa.Integer(), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("direcao", sa.String(12), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "etapa_validada",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "etapa_recebida",
            sa.SmallInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("motivo", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "aluno_id > 0", name="ck_desafios_verificacao_web_aluno_positivo"
        ),
        sa.CheckConstraint(
            "conjunto_id > 0", name="ck_desafios_verificacao_web_conjunto_positivo"
        ),
        sa.CheckConstraint(
            "versao_referencia > 0",
            name="ck_desafios_verificacao_web_versao_positiva",
        ),
        sa.CheckConstraint(
            "length(nonce_hash) = 64",
            name="ck_desafios_verificacao_web_nonce_hash_valido",
        ),
        sa.CheckConstraint(
            "direcao IN ('esquerda', 'direita')",
            name="ck_desafios_verificacao_web_direcao_valida",
        ),
        sa.CheckConstraint(
            "etapa_validada BETWEEN 0 AND 3 AND etapa_recebida BETWEEN 0 AND 3",
            name="ck_desafios_verificacao_web_etapas_validas",
        ),
        sa.CheckConstraint(
            "estado IN ('aguardando_etapa', 'etapa_recebida', 'concluido', "
            "'rejeitado', 'expirado')",
            name="ck_desafios_verificacao_web_estado_valido",
        ),
        sa.CheckConstraint(
            "etapa_recebida = etapa_validada OR "
            "(estado IN ('etapa_recebida', 'rejeitado', 'expirado') "
            "AND etapa_recebida = etapa_validada + 1)",
            name="ck_desafios_verificacao_web_sequencia_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["jobs_faciais_web.id"],
            name="fk_desafio_job",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["aluno_id"],
            ["alunos.id"],
            name="fk_desafio_aluno",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conjunto_id"],
            ["conjuntos_referencias_web.id"],
            name="fk_desafio_conjunto",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_desafios_verificacao_web"),
    )
    op.create_index(
        "ix_desafios_verificacao_web_estado_expira",
        "desafios_verificacao_web",
        ["estado", "expira_em"],
        unique=False,
    )


def downgrade() -> None:
    possui_desafios = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM desafios_verificacao_web)"))
        .scalar_one()
    )
    if possui_desafios:
        raise RuntimeError(
            "Downgrade da migration 0008 recusado: desafios persistidos."
        )
    op.drop_index(
        "ix_desafios_verificacao_web_estado_expira",
        table_name="desafios_verificacao_web",
    )
    op.drop_table("desafios_verificacao_web")
