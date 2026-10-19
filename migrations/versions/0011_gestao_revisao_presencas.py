"""gestao web, revisao manual e estado versionado da presenca

Revision ID: 0011
Revises: 0010
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "presencas",
        sa.Column(
            "status",
            sa.String(length=12),
            server_default=sa.text("'presente'"),
            nullable=False,
        ),
    )
    op.add_column(
        "presencas",
        sa.Column(
            "origem",
            sa.String(length=12),
            server_default=sa.text("'legado'"),
            nullable=False,
        ),
    )
    op.add_column(
        "presencas",
        sa.Column("versao", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.add_column(
        "presencas", sa.Column("horario_evidencia", sa.DateTime(timezone=True))
    )
    op.add_column("presencas", sa.Column("corrigida_em", sa.DateTime(timezone=True)))
    op.add_column("presencas", sa.Column("corrigida_por_conta_id", sa.BigInteger()))
    op.execute(
        sa.text(
            "UPDATE presencas SET origem = 'biometrica' "
            "WHERE sessao_id IS NOT NULL AND tentativa_id IS NOT NULL"
        )
    )
    op.drop_constraint(
        "ck_presencas_sessao_tentativa_coerentes", "presencas", type_="check"
    )
    op.create_check_constraint(
        "ck_presencas_sessao_tentativa_coerentes",
        "presencas",
        "(sessao_id IS NULL AND tentativa_id IS NULL) OR "
        "(sessao_id IS NOT NULL AND turma_id IS NOT NULL AND "
        "((tentativa_id IS NOT NULL AND origem = 'biometrica') OR "
        "(tentativa_id IS NULL AND origem = 'manual' AND corrigida_em IS NOT NULL)))",
    )
    op.create_check_constraint(
        "ck_presencas_status_presenca_valido",
        "presencas",
        "status IN ('presente', 'anulada')",
    )
    op.create_check_constraint(
        "ck_presencas_origem_presenca_valida",
        "presencas",
        "origem IN ('biometrica', 'manual', 'legado')",
    )
    op.create_check_constraint(
        "ck_presencas_versao_presenca_positiva", "presencas", "versao > 0"
    )
    op.create_check_constraint(
        "ck_presencas_correcao_presenca_coerente",
        "presencas",
        "(corrigida_em IS NULL AND corrigida_por_conta_id IS NULL) OR "
        "(corrigida_em IS NOT NULL AND corrigida_por_conta_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_presencas_anulacao_presenca_auditada",
        "presencas",
        "status != 'anulada' OR corrigida_em IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_presencas_corrigida_por_conta",
        "presencas",
        "contas_web",
        ["corrigida_por_conta_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint(
        "ck_tentativas_presenca_web_ordinal_valido",
        "tentativas_presenca_web",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tentativas_presenca_web_ordinal_valido",
        "tentativas_presenca_web",
        "ordinal >= 1",
    )

    op.create_table(
        "revisoes_presenca_web",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("turma_id", sa.BigInteger(), nullable=False),
        sa.Column("sessao_id", sa.BigInteger(), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=False),
        sa.Column("estado", sa.String(length=12), nullable=False),
        sa.Column("justificativa_solicitacao", sa.String(length=500), nullable=False),
        sa.Column("via_acessivel", sa.Boolean(), nullable=False),
        sa.Column("solicitada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("versao_presenca_base", sa.Integer(), nullable=False),
        sa.Column("decisao", sa.String(length=12), nullable=True),
        sa.Column("justificativa_decisao", sa.String(length=500), nullable=True),
        sa.Column("decidida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decidida_por_conta_id", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "estado IN ('aberta', 'decidida')",
            name="ck_revisoes_presenca_web_estado_valido",
        ),
        sa.CheckConstraint(
            "length(btrim(justificativa_solicitacao)) BETWEEN 1 AND 500",
            name="ck_revisoes_presenca_web_justificativa_solicitacao_valida",
        ),
        sa.CheckConstraint(
            "versao_presenca_base >= 0",
            name="ck_revisoes_presenca_web_versao_base_valida",
        ),
        sa.CheckConstraint(
            "(estado = 'aberta' AND decisao IS NULL AND decidida_em IS NULL "
            "AND decidida_por_conta_id IS NULL AND justificativa_decisao IS NULL) OR "
            "(estado = 'decidida' AND decisao IN ('presente', 'anulada') "
            "AND decidida_em IS NOT NULL AND decidida_por_conta_id IS NOT NULL "
            "AND justificativa_decisao IS NOT NULL)",
            name="ck_revisoes_presenca_web_decisao_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["sessao_id", "turma_id"],
            ["sessoes_presenca_web.id", "sessoes_presenca_web.turma_id"],
            name="fk_revisoes_presenca_sessao_turma",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turma_id", "aluno_id"],
            ["aluno_turma.turma_id", "aluno_turma.aluno_id"],
            name="fk_revisoes_presenca_vinculo",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["decidida_por_conta_id"],
            ["contas_web.id"],
            name="fk_revisoes_presenca_decidida_por",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_revisoes_presenca_web"),
    )
    op.create_index(
        "uq_revisoes_presenca_aberta",
        "revisoes_presenca_web",
        ["sessao_id", "aluno_id"],
        unique=True,
        postgresql_where=sa.text("estado = 'aberta'"),
    )
    op.create_index(
        "ix_revisoes_presenca_turma_estado",
        "revisoes_presenca_web",
        ["turma_id", "estado"],
    )
    op.create_index(
        "ix_revisoes_presenca_aluno_sessao",
        "revisoes_presenca_web",
        ["aluno_id", "sessao_id"],
    )


def downgrade() -> None:
    conn = op.get_bind()
    possui_estado_novo = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM revisoes_presenca_web) OR "
            "EXISTS (SELECT 1 FROM presencas WHERE status != 'presente' "
            "OR origem != 'legado' OR versao != 1 OR horario_evidencia IS NOT NULL "
            "OR corrigida_em IS NOT NULL OR corrigida_por_conta_id IS NOT NULL) OR "
            "EXISTS (SELECT 1 FROM tentativas_presenca_web WHERE ordinal > 3) OR "
            "EXISTS (SELECT 1 FROM eventos_auditoria_web "
            "WHERE acao = 'quota_presenca_reativada')"
        )
    ).scalar_one()
    if possui_estado_novo:
        raise RuntimeError(
            "Downgrade 0011 recusado: existem revisões, correções, presença web "
            "ou reativações de quota; preserve os registros antes de reverter."
        )

    op.drop_index(
        "ix_revisoes_presenca_aluno_sessao", table_name="revisoes_presenca_web"
    )
    op.drop_index(
        "ix_revisoes_presenca_turma_estado", table_name="revisoes_presenca_web"
    )
    op.drop_index("uq_revisoes_presenca_aberta", table_name="revisoes_presenca_web")
    op.drop_table("revisoes_presenca_web")
    op.drop_constraint(
        "ck_tentativas_presenca_web_ordinal_valido",
        "tentativas_presenca_web",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tentativas_presenca_web_ordinal_valido",
        "tentativas_presenca_web",
        "ordinal BETWEEN 1 AND 3",
    )
    op.drop_constraint(
        "fk_presencas_corrigida_por_conta", "presencas", type_="foreignkey"
    )
    for nome in (
        "ck_presencas_anulacao_presenca_auditada",
        "ck_presencas_correcao_presenca_coerente",
        "ck_presencas_versao_presenca_positiva",
        "ck_presencas_origem_presenca_valida",
        "ck_presencas_status_presenca_valido",
    ):
        op.drop_constraint(nome, "presencas", type_="check")
    op.drop_constraint(
        "ck_presencas_sessao_tentativa_coerentes", "presencas", type_="check"
    )
    op.create_check_constraint(
        "ck_presencas_sessao_tentativa_coerentes",
        "presencas",
        "(sessao_id IS NULL AND tentativa_id IS NULL) OR "
        "(sessao_id IS NOT NULL AND tentativa_id IS NOT NULL AND turma_id IS NOT NULL)",
    )
    for nome in (
        "corrigida_por_conta_id",
        "corrigida_em",
        "horario_evidencia",
        "versao",
        "origem",
        "status",
    ):
        op.drop_column("presencas", nome)
