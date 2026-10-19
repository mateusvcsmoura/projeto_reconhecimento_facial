"""links de cadastro, credenciais efemeras e vinculo de jobs

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "links_cadastro_web",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turma_id", sa.BigInteger(), nullable=False),
        sa.Column("emitido_por_conta_id", sa.BigInteger(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("finalidade", sa.String(16), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalidade_ate", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogado_por_conta_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_links_cadastro_web_token_hash_sha256",
        ),
        sa.CheckConstraint(
            "finalidade = 'cadastro'",
            name="ck_links_cadastro_web_finalidade_cadastro",
        ),
        sa.CheckConstraint(
            "expira_em > criado_em",
            name="ck_links_cadastro_web_expiracao_valida",
        ),
        sa.CheckConstraint(
            "finalidade_ate > criado_em",
            name="ck_links_cadastro_web_fim_finalidade_valido",
        ),
        sa.CheckConstraint(
            "(revogado_em IS NULL AND revogado_por_conta_id IS NULL) OR "
            "(revogado_em IS NOT NULL AND revogado_por_conta_id IS NOT NULL)",
            name="ck_links_cadastro_web_revogacao_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["turma_id"],
            ["turmas.id"],
            name="fk_links_cadastro_web_turma_id_turmas",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["emitido_por_conta_id"],
            ["contas_web.id"],
            name="fk_links_cadastro_web_emitido_por_conta_id_contas_web",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revogado_por_conta_id"],
            ["contas_web.id"],
            name="fk_links_cadastro_web_revogado_por_conta_id_contas_web",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_links_cadastro_web"),
        sa.UniqueConstraint("token_hash", name="uq_links_cadastro_web_token_hash"),
    )
    op.create_index(
        "ix_links_cadastro_web_turma_expira",
        "links_cadastro_web",
        ["turma_id", "expira_em"],
    )

    op.create_table(
        "credenciais_link_cadastro_web",
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("solicitacao_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_credenciais_link_cadastro_web_token_hash_sha256",
        ),
        sa.CheckConstraint(
            "expira_em > criada_em",
            name="ck_credenciais_link_cadastro_web_expiracao_valida",
        ),
        sa.ForeignKeyConstraint(
            ["link_id"],
            ["links_cadastro_web.id"],
            name="fk_credenciais_link_cadastro_web_link_id_links_cadastro_web",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["solicitacao_id"],
            ["solicitacoes_cadastro_web.id"],
            name="fk_cred_link_solicitacao",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_hash", name="pk_credenciais_link_cadastro_web"),
        sa.UniqueConstraint(
            "solicitacao_id",
            name="uq_credenciais_link_solicitacao",
        ),
    )
    op.create_index(
        "ix_credenciais_link_expira",
        "credenciais_link_cadastro_web",
        ["expira_em"],
    )

    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column("credencial_captura_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column(
            "credencial_captura_expira_em", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column("desafio_nonce_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column("desafio_direcao", sa.String(12), nullable=True),
    )
    op.add_column(
        "solicitacoes_cadastro_web",
        sa.Column("desafio_expira_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_solicitacoes_cadastro_web_link_id_links_cadastro_web",
        "solicitacoes_cadastro_web",
        "links_cadastro_web",
        ["link_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_solicitacoes_cadastro_web_job_id_jobs_faciais_web",
        "solicitacoes_cadastro_web",
        "jobs_faciais_web",
        ["job_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_solicitacoes_cadastro_web_job", "solicitacoes_cadastro_web", ["job_id"]
    )
    op.create_unique_constraint(
        "uq_solicitacoes_cadastro_web_credencial_captura",
        "solicitacoes_cadastro_web",
        ["credencial_captura_hash"],
    )
    op.create_check_constraint(
        "ck_solicitacoes_cadastro_web_credencial_captura_coerente",
        "solicitacoes_cadastro_web",
        "(credencial_captura_hash IS NULL AND "
        "credencial_captura_expira_em IS NULL) OR "
        "(length(credencial_captura_hash) = 64 AND "
        "credencial_captura_expira_em IS NOT NULL AND "
        "credencial_captura_expira_em > criada_em)",
    )
    op.create_check_constraint(
        "ck_solicitacoes_cadastro_web_desafio_cadastro_coerente",
        "solicitacoes_cadastro_web",
        "(desafio_nonce_hash IS NULL AND desafio_direcao IS NULL AND "
        "desafio_expira_em IS NULL) OR "
        "(length(desafio_nonce_hash) = 64 AND "
        "desafio_direcao IN ('esquerda', 'direita') AND "
        "desafio_expira_em IS NOT NULL AND desafio_expira_em > criada_em)",
    )
    op.create_index(
        "ix_solicitacoes_cadastro_web_link_estado",
        "solicitacoes_cadastro_web",
        ["link_id", "estado"],
    )
    op.create_index(
        "ix_solicitacoes_cadastro_web_desafio_expira",
        "solicitacoes_cadastro_web",
        ["desafio_expira_em"],
    )


def downgrade() -> None:
    possui_links = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM links_cadastro_web) "
                "OR EXISTS (SELECT 1 FROM credenciais_link_cadastro_web) "
                "OR EXISTS (SELECT 1 FROM solicitacoes_cadastro_web WHERE "
                "link_id IS NOT NULL OR job_id IS NOT NULL OR "
                "credencial_captura_hash IS NOT NULL OR "
                "desafio_nonce_hash IS NOT NULL)"
            )
        )
        .scalar_one()
    )
    if possui_links:
        raise RuntimeError(
            "Downgrade da migration 0009 recusado: links, credenciais, coletas "
            "ou desafios persistidos."
        )
    op.drop_index(
        "ix_solicitacoes_cadastro_web_link_estado",
        table_name="solicitacoes_cadastro_web",
    )
    op.drop_index(
        "ix_solicitacoes_cadastro_web_desafio_expira",
        table_name="solicitacoes_cadastro_web",
    )
    op.drop_constraint(
        "uq_solicitacoes_cadastro_web_job",
        "solicitacoes_cadastro_web",
        type_="unique",
    )
    op.drop_constraint(
        "ck_solicitacoes_cadastro_web_credencial_captura_coerente",
        "solicitacoes_cadastro_web",
        type_="check",
    )
    op.drop_constraint(
        "ck_solicitacoes_cadastro_web_desafio_cadastro_coerente",
        "solicitacoes_cadastro_web",
        type_="check",
    )
    op.drop_constraint(
        "uq_solicitacoes_cadastro_web_credencial_captura",
        "solicitacoes_cadastro_web",
        type_="unique",
    )
    op.drop_constraint(
        "fk_solicitacoes_cadastro_web_job_id_jobs_faciais_web",
        "solicitacoes_cadastro_web",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_solicitacoes_cadastro_web_link_id_links_cadastro_web",
        "solicitacoes_cadastro_web",
        type_="foreignkey",
    )
    op.drop_column("solicitacoes_cadastro_web", "job_id")
    op.drop_column("solicitacoes_cadastro_web", "credencial_captura_expira_em")
    op.drop_column("solicitacoes_cadastro_web", "credencial_captura_hash")
    op.drop_column("solicitacoes_cadastro_web", "desafio_expira_em")
    op.drop_column("solicitacoes_cadastro_web", "desafio_direcao")
    op.drop_column("solicitacoes_cadastro_web", "desafio_nonce_hash")
    op.drop_column("solicitacoes_cadastro_web", "link_id")
    op.drop_index(
        "ix_credenciais_link_expira", table_name="credenciais_link_cadastro_web"
    )
    op.drop_table("credenciais_link_cadastro_web")
    op.drop_index("ix_links_cadastro_web_turma_expira", table_name="links_cadastro_web")
    op.drop_table("links_cadastro_web")
