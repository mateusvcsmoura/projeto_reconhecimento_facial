"""solicitacoes pendentes e referencias faciais versionadas

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "solicitacoes_cadastro_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("tipo", sa.String(16), nullable=False),
        sa.Column("estado", sa.String(24), nullable=False),
        sa.Column("convite_ref", sa.String(128), nullable=True),
        sa.Column("turma_id", sa.BigInteger(), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=True),
        sa.Column("matricula", sa.String(32), nullable=True),
        sa.Column("nome", sa.String(255), nullable=True),
        sa.Column("consentimento_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consentimento_versao", sa.String(64), nullable=True),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decidida_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decidida_por_conta_id", sa.BigInteger(), nullable=True),
        sa.Column("metodo_identidade", sa.String(40), nullable=True),
        sa.Column("justificativa", sa.String(500), nullable=True),
        sa.Column("limpa_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "tipo IN ('cadastro', 'atualizacao')",
            name="ck_solicitacoes_cadastro_web_tipo_valido",
        ),
        sa.CheckConstraint(
            "estado IN ('em_coleta', 'em_validacao', 'pendente_aprovacao', "
            "'aprovada', 'rejeitada', 'cancelada', 'expirada')",
            name="ck_solicitacoes_cadastro_web_estado_valido",
        ),
        sa.CheckConstraint(
            "(tipo = 'cadastro' AND aluno_id IS NULL AND matricula IS NOT NULL "
            "AND nome IS NOT NULL AND convite_ref IS NOT NULL) OR "
            "(tipo = 'atualizacao' AND aluno_id IS NOT NULL AND matricula IS NULL "
            "AND nome IS NULL AND convite_ref IS NULL)",
            name="ck_solicitacoes_cadastro_web_identificacao_coerente",
        ),
        sa.CheckConstraint(
            "(consentimento_em IS NULL AND consentimento_versao IS NULL) OR "
            "(consentimento_em IS NOT NULL AND consentimento_versao IS NOT NULL "
            "AND length(consentimento_versao) > 0)",
            name="ck_solicitacoes_cadastro_web_consentimento_coerente",
        ),
        sa.CheckConstraint(
            "expira_em > criada_em",
            name="ck_solicitacoes_cadastro_web_expiracao_valida",
        ),
        sa.ForeignKeyConstraint(
            ["aluno_id"],
            ["alunos.id"],
            name="fk_solicitacoes_cadastro_web_aluno_id_alunos",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["turma_id"],
            ["turmas.id"],
            name="fk_solicitacoes_cadastro_web_turma_id_turmas",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_solicitacoes_cadastro_web"),
    )
    op.create_index(
        "ix_solicitacoes_cadastro_web_turma_estado",
        "solicitacoes_cadastro_web",
        ["turma_id", "estado"],
    )
    op.create_index(
        "ix_solicitacoes_cadastro_web_estado_expira",
        "solicitacoes_cadastro_web",
        ["estado", "expira_em"],
    )
    op.create_index(
        "ix_solicitacoes_cadastro_web_aluno",
        "solicitacoes_cadastro_web",
        ["aluno_id"],
    )

    op.create_table(
        "conjuntos_referencias_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("solicitacao_id", sa.BigInteger(), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=True),
        sa.Column("versao", sa.Integer(), nullable=True),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("job_id", sa.String(36), nullable=False),
        sa.Column("embedding_modelo", sa.String(64), nullable=False),
        sa.Column("embedding_dim", sa.SmallInteger(), nullable=False),
        sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ativado_em", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "estado IN ('pendente', 'ativo', 'substituido', 'descartado')",
            name="ck_conjuntos_referencias_web_estado_valido",
        ),
        sa.CheckConstraint(
            "(estado = 'pendente' AND aluno_id IS NULL AND versao IS NULL) OR "
            "(estado = 'descartado' AND ((aluno_id IS NULL AND versao IS NULL) OR "
            "(aluno_id IS NOT NULL AND versao IS NOT NULL AND versao > 0))) OR "
            "(estado IN ('ativo', 'substituido') AND aluno_id IS NOT NULL "
            "AND versao IS NOT NULL AND versao > 0)",
            name="ck_conjuntos_referencias_web_versao_coerente",
        ),
        sa.CheckConstraint(
            "embedding_dim = 512",
            name="ck_conjuntos_referencias_web_embedding_dim_512",
        ),
        sa.ForeignKeyConstraint(
            ["aluno_id"],
            ["alunos.id"],
            name="fk_conjuntos_referencias_web_aluno_id_alunos",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["solicitacao_id"],
            ["solicitacoes_cadastro_web.id"],
            name="fk_conj_ref_solicitacao",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conjuntos_referencias_web"),
        sa.UniqueConstraint(
            "aluno_id",
            "versao",
            name="uq_conjuntos_referencias_web_aluno_versao",
        ),
        sa.UniqueConstraint("job_id", name="uq_conjuntos_referencias_web_job"),
        sa.UniqueConstraint(
            "solicitacao_id",
            name="uq_conjuntos_referencias_web_solicitacao",
        ),
    )
    op.create_index(
        "uq_conjuntos_referencias_web_aluno_ativo",
        "conjuntos_referencias_web",
        ["aluno_id"],
        unique=True,
        postgresql_where=sa.text("estado = 'ativo'"),
    )
    op.create_index(
        "ix_conjuntos_referencias_web_solicitacao_estado",
        "conjuntos_referencias_web",
        ["solicitacao_id", "estado"],
    )
    op.create_index(
        "ix_conjuntos_referencias_web_aluno_estado",
        "conjuntos_referencias_web",
        ["aluno_id", "estado"],
    )

    op.create_table(
        "referencias_faciais_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("conjunto_id", sa.BigInteger(), nullable=False),
        sa.Column("ordinal", sa.SmallInteger(), nullable=False),
        sa.Column("caminho_privado_relativo", sa.String(512), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        sa.Column("embedding_modelo", sa.String(64), nullable=False),
        sa.Column("embedding_dim", sa.SmallInteger(), nullable=False),
        sa.Column("consentimento_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consentimento_versao", sa.String(64), nullable=False),
        sa.Column("capturada_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 3",
            name="ck_referencias_faciais_web_ordinal_valido",
        ),
        sa.CheckConstraint(
            "embedding_dim = 512",
            name="ck_referencias_faciais_web_embedding_dim_512",
        ),
        sa.CheckConstraint(
            "length(embedding) = 2048",
            name="ck_referencias_faciais_web_embedding_float32_512",
        ),
        sa.CheckConstraint(
            "length(caminho_privado_relativo) > 0",
            name="ck_referencias_faciais_web_caminho_nao_vazio",
        ),
        sa.CheckConstraint(
            "length(embedding_modelo) > 0",
            name="ck_referencias_faciais_web_modelo_nao_vazio",
        ),
        sa.CheckConstraint(
            "length(consentimento_versao) > 0",
            name="ck_referencias_faciais_web_consentimento_versao_valida",
        ),
        sa.ForeignKeyConstraint(
            ["conjunto_id"],
            ["conjuntos_referencias_web.id"],
            name="fk_ref_facial_conjunto",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_referencias_faciais_web"),
        sa.UniqueConstraint(
            "conjunto_id",
            "ordinal",
            name="uq_referencias_faciais_web_conjunto_ordinal",
        ),
    )
    op.create_index(
        "ix_referencias_faciais_web_conjunto",
        "referencias_faciais_web",
        ["conjunto_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    possui_dados = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM solicitacoes_cadastro_web) "
            "OR EXISTS (SELECT 1 FROM conjuntos_referencias_web) "
            "OR EXISTS (SELECT 1 FROM referencias_faciais_web)"
        )
    ).scalar_one()
    if possui_dados:
        raise RuntimeError(
            "Downgrade recusado: há solicitações ou referências web. "
            "Preserve os dados e prepare um rollback explícito."
        )
    op.drop_index(
        "ix_referencias_faciais_web_conjunto", table_name="referencias_faciais_web"
    )
    op.drop_table("referencias_faciais_web")
    op.drop_index(
        "ix_conjuntos_referencias_web_aluno_estado",
        table_name="conjuntos_referencias_web",
    )
    op.drop_index(
        "ix_conjuntos_referencias_web_solicitacao_estado",
        table_name="conjuntos_referencias_web",
    )
    op.drop_index(
        "uq_conjuntos_referencias_web_aluno_ativo",
        table_name="conjuntos_referencias_web",
    )
    op.drop_table("conjuntos_referencias_web")
    op.drop_index(
        "ix_solicitacoes_cadastro_web_aluno", table_name="solicitacoes_cadastro_web"
    )
    op.drop_index(
        "ix_solicitacoes_cadastro_web_estado_expira",
        table_name="solicitacoes_cadastro_web",
    )
    op.drop_index(
        "ix_solicitacoes_cadastro_web_turma_estado",
        table_name="solicitacoes_cadastro_web",
    )
    op.drop_table("solicitacoes_cadastro_web")
