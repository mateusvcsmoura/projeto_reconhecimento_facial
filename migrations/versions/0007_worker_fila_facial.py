"""fila FIFO e leases do worker facial web

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jobs_faciais_web",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dono_id", sa.String(128), nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("idempotencia_hash", sa.String(64), nullable=False),
        sa.Column("credencial_hash", sa.String(64), nullable=False),
        sa.Column(
            "manifesto",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=True,
        ),
        sa.Column("bytes_reservados", sa.BigInteger(), nullable=False),
        sa.Column("prazo_reserva", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prazo_execucao", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atualizada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enfileirada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalizada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_hash", sa.String(64), nullable=True),
        sa.Column("lease_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelamento_solicitado",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("resultado_codigo", sa.String(64), nullable=True),
        sa.CheckConstraint(
            "length(dono_id) BETWEEN 1 AND 128",
            name="ck_jobs_faciais_web_dono_valido",
        ),
        sa.CheckConstraint(
            "tipo IN ('cadastro', 'presenca')",
            name="ck_jobs_faciais_web_tipo_valido",
        ),
        sa.CheckConstraint(
            "estado IN ('recebida', 'enfileirada', 'processando', 'concluida', "
            "'rejeitada', 'cancelada', 'expirada')",
            name="ck_jobs_faciais_web_estado_valido",
        ),
        sa.CheckConstraint(
            "length(idempotencia_hash) = 64 AND length(credencial_hash) = 64",
            name="ck_jobs_faciais_web_hashes_validos",
        ),
        sa.CheckConstraint(
            "bytes_reservados > 0",
            name="ck_jobs_faciais_web_reserva_bytes_positiva",
        ),
        sa.CheckConstraint(
            "prazo_reserva > criada_em",
            name="ck_jobs_faciais_web_prazo_reserva_valido",
        ),
        sa.CheckConstraint(
            "prazo_execucao > criada_em",
            name="ck_jobs_faciais_web_prazo_execucao_valido",
        ),
        sa.CheckConstraint(
            "(estado = 'processando' AND lease_hash IS NOT NULL "
            "AND lease_expira_em IS NOT NULL AND manifesto IS NOT NULL) OR "
            "(estado <> 'processando' AND lease_hash IS NULL "
            "AND lease_expira_em IS NULL)",
            name="ck_jobs_faciais_web_lease_coerente",
        ),
        sa.CheckConstraint(
            "(estado IN ('enfileirada', 'processando') AND manifesto IS NOT NULL) "
            "OR estado IN ('recebida', 'concluida', 'rejeitada', 'cancelada', "
            "'expirada')",
            name="ck_jobs_faciais_web_manifesto_coerente",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs_faciais_web"),
        sa.UniqueConstraint(
            "dono_id",
            "tipo",
            "idempotencia_hash",
            name="uq_jobs_faciais_web_idempotencia",
        ),
    )
    op.create_index(
        "ix_jobs_faciais_web_fila_fifo",
        "jobs_faciais_web",
        ["estado", "enfileirada_em", "id"],
    )
    op.create_index(
        "ix_jobs_faciais_web_prazos",
        "jobs_faciais_web",
        ["estado", "prazo_reserva", "prazo_execucao"],
    )
    op.create_index(
        "uq_jobs_faciais_web_ativo",
        "jobs_faciais_web",
        ["estado"],
        unique=True,
        postgresql_where=sa.text("estado = 'processando'"),
    )


def downgrade() -> None:
    possui_jobs = (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM jobs_faciais_web)"))
        .scalar_one()
    )
    if possui_jobs:
        raise RuntimeError(
            "Downgrade recusado: há operações faciais registradas. "
            "Preserve os estados e faça rollback coordenado."
        )
    op.drop_index("uq_jobs_faciais_web_ativo", table_name="jobs_faciais_web")
    op.drop_index("ix_jobs_faciais_web_prazos", table_name="jobs_faciais_web")
    op.drop_index("ix_jobs_faciais_web_fila_fifo", table_name="jobs_faciais_web")
    op.drop_table("jobs_faciais_web")
