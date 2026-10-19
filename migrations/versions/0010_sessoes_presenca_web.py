"""sessoes, tentativas e presenca por sessao

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessoes_presenca_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("turma_id", sa.BigInteger(), nullable=False),
        sa.Column("criada_por_conta_id", sa.BigInteger(), nullable=False),
        sa.Column("titulo", sa.String(length=120), nullable=False),
        sa.Column("inicio_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fim_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revogada_por_conta_id", sa.BigInteger(), nullable=True),
        sa.Column("versao", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "length(btrim(titulo)) BETWEEN 1 AND 120",
            name="ck_sessoes_presenca_web_titulo_valido",
        ),
        sa.CheckConstraint(
            "fim_em > inicio_em", name="ck_sessoes_presenca_web_janela_valida"
        ),
        sa.CheckConstraint(
            "versao > 0", name="ck_sessoes_presenca_web_versao_positiva"
        ),
        sa.CheckConstraint(
            "(revogada_em IS NULL AND revogada_por_conta_id IS NULL) OR "
            "(revogada_em IS NOT NULL AND revogada_por_conta_id IS NOT NULL)",
            name="ck_sessoes_presenca_web_revogacao_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["turma_id"],
            ["turmas.id"],
            name="fk_sessoes_presenca_turma",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["criada_por_conta_id"],
            ["contas_web.id"],
            name="fk_sessoes_presenca_criador",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["revogada_por_conta_id"],
            ["contas_web.id"],
            name="fk_sessoes_presenca_revogador",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessoes_presenca_web"),
        sa.UniqueConstraint("id", "turma_id", name="uq_sessoes_presenca_id_turma"),
    )
    op.create_index(
        "ix_sessoes_presenca_turma_inicio",
        "sessoes_presenca_web",
        ["turma_id", "inicio_em"],
    )

    op.add_column(
        "links_cadastro_web",
        sa.Column("sessao_id", sa.BigInteger(), nullable=True),
    )
    op.drop_constraint(
        "ck_links_cadastro_web_finalidade_cadastro",
        "links_cadastro_web",
        type_="check",
    )
    op.create_check_constraint(
        "ck_links_cadastro_web_finalidade_sessao_coerente",
        "links_cadastro_web",
        "(finalidade = 'cadastro' AND sessao_id IS NULL) OR "
        "(finalidade = 'presenca' AND sessao_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_links_presenca_sessao_turma",
        "links_cadastro_web",
        "sessoes_presenca_web",
        ["sessao_id", "turma_id"],
        ["id", "turma_id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_links_cadastro_sessao_turma",
        "links_cadastro_web",
        ["id", "sessao_id", "turma_id"],
    )

    op.create_unique_constraint(
        "uq_conjuntos_referencias_id_aluno_versao",
        "conjuntos_referencias_web",
        ["id", "aluno_id", "versao"],
    )
    op.create_table(
        "tentativas_presenca_web",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sessao_id", sa.BigInteger(), nullable=False),
        sa.Column("turma_id", sa.BigInteger(), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("conjunto_id", sa.BigInteger(), nullable=False),
        sa.Column("versao_referencia", sa.Integer(), nullable=False),
        sa.Column("versao_sessao", sa.Integer(), nullable=False),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotencia_hash", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prazo_envio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recebida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("concluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("motivo_tecnico", sa.String(length=64), nullable=True),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 3",
            name="ck_tentativas_presenca_web_ordinal_valido",
        ),
        sa.CheckConstraint(
            "versao_referencia > 0 AND versao_sessao > 0",
            name="ck_tentativas_presenca_web_versoes_positivas",
        ),
        sa.CheckConstraint(
            "length(idempotencia_hash) = 64",
            name="ck_tentativas_presenca_web_idempotencia_hash_valida",
        ),
        sa.CheckConstraint(
            "estado IN ('iniciada', 'recebida', 'enfileirada', 'processando', "
            "'concluida', 'expirada', 'rejeitada')",
            name="ck_tentativas_presenca_web_estado_valido",
        ),
        sa.CheckConstraint(
            "prazo_envio > iniciada_em",
            name="ck_tentativas_presenca_web_prazo_valido",
        ),
        sa.CheckConstraint(
            "(estado IN ('iniciada', 'recebida', 'enfileirada', 'processando') "
            "AND concluida_em IS NULL) OR "
            "(estado IN ('concluida', 'expirada', 'rejeitada') "
            "AND concluida_em IS NOT NULL)",
            name="ck_tentativas_presenca_web_terminalidade_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["id"],
            ["jobs_faciais_web.id"],
            name="fk_tentativas_presenca_job",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sessao_id", "turma_id"],
            ["sessoes_presenca_web.id", "sessoes_presenca_web.turma_id"],
            name="fk_tentativas_presenca_sessao_turma",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turma_id", "aluno_id"],
            ["aluno_turma.turma_id", "aluno_turma.aluno_id"],
            name="fk_tentativas_presenca_vinculo",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["conjunto_id", "aluno_id", "versao_referencia"],
            [
                "conjuntos_referencias_web.id",
                "conjuntos_referencias_web.aluno_id",
                "conjuntos_referencias_web.versao",
            ],
            name="fk_tentativas_presenca_conjunto_ativo",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["link_id", "sessao_id", "turma_id"],
            [
                "links_cadastro_web.id",
                "links_cadastro_web.sessao_id",
                "links_cadastro_web.turma_id",
            ],
            name="fk_tentativas_presenca_link_escopo",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tentativas_presenca_web"),
        sa.UniqueConstraint(
            "sessao_id", "aluno_id", "ordinal", name="uq_tentativas_presenca_ordinal"
        ),
        sa.UniqueConstraint(
            "sessao_id",
            "aluno_id",
            "idempotencia_hash",
            name="uq_tentativas_presenca_idempotencia",
        ),
    )
    op.create_index(
        "uq_tentativas_presenca_ativa",
        "tentativas_presenca_web",
        ["sessao_id", "aluno_id"],
        unique=True,
        postgresql_where=sa.text(
            "estado IN ('iniciada', 'recebida', 'enfileirada', 'processando')"
        ),
    )
    op.create_index(
        "ix_tentativas_presenca_estado",
        "tentativas_presenca_web",
        ["estado", "prazo_envio"],
    )
    op.create_table(
        "recebimentos_tentativa_presenca_web",
        sa.Column("tentativa_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("recebido_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 3",
            name="ck_recebimentos_tentativa_presenca_web_ordinal_valido",
        ),
        sa.CheckConstraint(
            "length(payload_hash) = 64",
            name="ck_recebimentos_tentativa_presenca_web_payload_hash_valido",
        ),
        sa.ForeignKeyConstraint(
            ["tentativa_id"],
            ["tentativas_presenca_web.id"],
            name="fk_recebimentos_tentativa_web_tentativa",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tentativa_id", "ordinal", name="pk_recebimentos_tentativa_presenca_web"
        ),
    )

    op.create_table(
        "limites_presenca_web",
        sa.Column("chave_hash", sa.String(length=64), nullable=False),
        sa.Column("janela_iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("bloqueado_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(chave_hash) = 64", name="ck_limites_presenca_web_chave_hash_valida"
        ),
        sa.CheckConstraint(
            "quantidade >= 0", name="ck_limites_presenca_web_quantidade_nao_negativa"
        ),
        sa.PrimaryKeyConstraint("chave_hash", name="pk_limites_presenca_web"),
    )
    op.create_index(
        "ix_limites_presenca_atualizado", "limites_presenca_web", ["atualizado_em"]
    )

    op.add_column("presencas", sa.Column("sessao_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "presencas",
        sa.Column("tentativa_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.drop_constraint("uq_presencas_turma_aluno_dia", "presencas", type_="unique")
    op.drop_index("uq_presencas_legado_aluno_dia", table_name="presencas")
    op.create_check_constraint(
        "ck_presencas_sessao_tentativa_coerentes",
        "presencas",
        "(sessao_id IS NULL AND tentativa_id IS NULL) OR "
        "(sessao_id IS NOT NULL AND tentativa_id IS NOT NULL AND turma_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_presencas_sessao_turma",
        "presencas",
        "sessoes_presenca_web",
        ["sessao_id", "turma_id"],
        ["id", "turma_id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_presencas_tentativa",
        "presencas",
        "tentativas_presenca_web",
        ["tentativa_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint("uq_presencas_tentativa", "presencas", ["tentativa_id"])
    op.create_index(
        "uq_presencas_turma_aluno_dia",
        "presencas",
        ["turma_id", "aluno_id", "data_referencia"],
        unique=True,
        postgresql_where=sa.text("sessao_id IS NULL AND turma_id IS NOT NULL"),
    )
    op.create_index(
        "uq_presencas_legado_aluno_dia",
        "presencas",
        ["aluno_id", "data_referencia"],
        unique=True,
        postgresql_where=sa.text("sessao_id IS NULL AND turma_id IS NULL"),
    )
    op.create_index(
        "uq_presencas_sessao_aluno",
        "presencas",
        ["sessao_id", "aluno_id"],
        unique=True,
        postgresql_where=sa.text("sessao_id IS NOT NULL"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    possui_dados = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM sessoes_presenca_web) OR "
            "EXISTS (SELECT 1 FROM tentativas_presenca_web) OR "
            "EXISTS (SELECT 1 FROM presencas WHERE sessao_id IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM links_cadastro_web WHERE finalidade = 'presenca')"
        )
    ).scalar_one()
    if possui_dados:
        raise RuntimeError(
            "Downgrade 0010 recusado: existem sessoes, tentativas, links ou "
            "presencas por sessao; exporte e avalie rollback sem perda."
        )

    op.drop_index("uq_presencas_sessao_aluno", table_name="presencas")
    op.drop_index("uq_presencas_legado_aluno_dia", table_name="presencas")
    op.drop_index("uq_presencas_turma_aluno_dia", table_name="presencas")
    op.drop_constraint("uq_presencas_tentativa", "presencas", type_="unique")
    op.drop_constraint("fk_presencas_tentativa", "presencas", type_="foreignkey")
    op.drop_constraint("fk_presencas_sessao_turma", "presencas", type_="foreignkey")
    op.drop_constraint(
        "ck_presencas_sessao_tentativa_coerentes", "presencas", type_="check"
    )
    op.create_unique_constraint(
        "uq_presencas_turma_aluno_dia",
        "presencas",
        ["turma_id", "aluno_id", "data_referencia"],
    )
    op.create_index(
        "uq_presencas_legado_aluno_dia",
        "presencas",
        ["aluno_id", "data_referencia"],
        unique=True,
        postgresql_where=sa.text("turma_id IS NULL"),
    )
    op.drop_column("presencas", "tentativa_id")
    op.drop_column("presencas", "sessao_id")

    op.drop_index("ix_limites_presenca_atualizado", table_name="limites_presenca_web")
    op.drop_table("limites_presenca_web")
    op.drop_table("recebimentos_tentativa_presenca_web")
    op.drop_index("ix_tentativas_presenca_estado", table_name="tentativas_presenca_web")
    op.drop_index("uq_tentativas_presenca_ativa", table_name="tentativas_presenca_web")
    op.drop_table("tentativas_presenca_web")
    op.drop_constraint(
        "uq_conjuntos_referencias_id_aluno_versao",
        "conjuntos_referencias_web",
        type_="unique",
    )
    op.drop_constraint(
        "uq_links_cadastro_sessao_turma", "links_cadastro_web", type_="unique"
    )
    op.drop_constraint(
        "fk_links_presenca_sessao_turma", "links_cadastro_web", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_links_cadastro_web_finalidade_sessao_coerente",
        "links_cadastro_web",
        type_="check",
    )
    op.create_check_constraint(
        "ck_links_cadastro_web_finalidade_cadastro",
        "links_cadastro_web",
        "finalidade = 'cadastro'",
    )
    op.drop_column("links_cadastro_web", "sessao_id")
    op.drop_index("ix_sessoes_presenca_turma_inicio", table_name="sessoes_presenca_web")
    op.drop_table("sessoes_presenca_web")
