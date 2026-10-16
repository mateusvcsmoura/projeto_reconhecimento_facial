"""turmas, vinculos e presencas contextualizadas

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "turmas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("materia", sa.String(length=120), nullable=False),
        sa.Column("periodo", sa.String(length=10), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("excluida_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(btrim(materia)) > 0", name="ck_turmas_materia_nao_vazia"
        ),
        sa.CheckConstraint(
            "periodo IN ('matutino', 'diurno', 'noturno')",
            name="ck_turmas_periodo_valido",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_turmas"),
    )
    op.create_table(
        "aluno_turma",
        sa.Column("turma_id", sa.BigInteger(), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "vinculado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("desvinculado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(ativo AND desvinculado_em IS NULL) OR "
            "(NOT ativo AND desvinculado_em IS NOT NULL)",
            name="ck_aluno_turma_estado_vinculo_coerente",
        ),
        sa.ForeignKeyConstraint(
            ["aluno_id"],
            ["alunos.id"],
            name="fk_aluno_turma_aluno_id_alunos",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turma_id"],
            ["turmas.id"],
            name="fk_aluno_turma_turma_id_turmas",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("turma_id", "aluno_id", name="pk_aluno_turma"),
    )
    op.create_index("ix_aluno_turma_aluno_id", "aluno_turma", ["aluno_id"])

    op.add_column("presencas", sa.Column("turma_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_presencas_turma_id_turmas",
        "presencas",
        "turmas",
        ["turma_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_presencas_turma_aluno_aluno_turma",
        "presencas",
        "aluno_turma",
        ["turma_id", "aluno_id"],
        ["turma_id", "aluno_id"],
        ondelete="CASCADE",
        match="SIMPLE",
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
    op.create_index(
        "ix_presencas_turma_data", "presencas", ["turma_id", "data_referencia"]
    )

    # As substitutas ja existem. A partir daqui escritores antigos precisam
    # ser interrompidos: eles ainda nomeiam a constraint global removida.
    op.drop_constraint("uq_presencas_aluno_dia", "presencas", type_="unique")


def downgrade() -> None:
    bind = op.get_bind()
    possui_dados_novos = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM turmas) "
            "OR EXISTS (SELECT 1 FROM aluno_turma) "
            "OR EXISTS (SELECT 1 FROM presencas WHERE turma_id IS NOT NULL)"
        )
    ).scalar_one()
    if possui_dados_novos:
        raise RuntimeError(
            "Downgrade recusado: existem dados de turmas, vinculos ou "
            "presencas associadas a turma. Exporte e avalie esses dados "
            "em um plano de rollback explicito antes de remover o schema."
        )

    # O preflight acima garante que todas as presencas restantes sao legadas;
    # a constraint global pode ser restaurada sem achatar dados novos.
    op.create_unique_constraint(
        "uq_presencas_aluno_dia", "presencas", ["aluno_id", "data_referencia"]
    )
    op.drop_index("ix_presencas_turma_data", table_name="presencas")
    op.drop_index("uq_presencas_legado_aluno_dia", table_name="presencas")
    op.drop_constraint("uq_presencas_turma_aluno_dia", "presencas", type_="unique")
    op.drop_constraint(
        "fk_presencas_turma_aluno_aluno_turma", "presencas", type_="foreignkey"
    )
    op.drop_constraint("fk_presencas_turma_id_turmas", "presencas", type_="foreignkey")
    op.drop_column("presencas", "turma_id")
    op.drop_index("ix_aluno_turma_aluno_id", table_name="aluno_turma")
    op.drop_table("aluno_turma")
    op.drop_table("turmas")
