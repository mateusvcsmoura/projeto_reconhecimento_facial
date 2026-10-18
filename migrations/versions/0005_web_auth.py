"""contas, sessoes autenticadas, auditoria e responsavel web por turma

Revision ID: 0005
Revises: 0004
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contas_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("usuario_normalizado", sa.String(length=80), nullable=False),
        sa.Column("senha_hash", sa.String(length=512), nullable=False),
        sa.Column("papel", sa.String(length=16), nullable=False),
        sa.Column("ativa", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "troca_senha_obrigatoria",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "versao_credencial", sa.Integer(), server_default="1", nullable=False
        ),
        sa.Column(
            "credencial_temporaria_expira_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "credencial_temporaria_usada_em", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(usuario_normalizado) > 0",
            name="ck_contas_web_usuario_nao_vazio",
        ),
        sa.CheckConstraint(
            "papel IN ('professor', 'admin')", name="ck_contas_web_papel_valido"
        ),
        sa.CheckConstraint(
            "versao_credencial > 0",
            name="ck_contas_web_versao_credencial_positiva",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contas_web"),
        sa.UniqueConstraint(
            "usuario_normalizado", name="uq_contas_web_usuario_normalizado"
        ),
    )
    op.create_table(
        "professores_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("conta_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conta_id"],
            ["contas_web.id"],
            name="fk_professores_web_conta_id_contas_web",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_professores_web"),
        sa.UniqueConstraint("conta_id", name="uq_professores_web_conta_id"),
    )
    op.create_table(
        "sessoes_autenticacao_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("conta_id", sa.BigInteger(), nullable=False),
        sa.Column("versao_credencial", sa.Integer(), nullable=False),
        sa.Column("criada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("atividade_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(token_hash) = 64",
            name="ck_sessoes_autenticacao_web_token_hash_sha256",
        ),
        sa.CheckConstraint(
            "length(csrf_hash) = 64",
            name="ck_sessoes_autenticacao_web_csrf_hash_sha256",
        ),
        sa.CheckConstraint(
            "expira_em > criada_em",
            name="ck_sessoes_autenticacao_web_expiracao_absoluta_valida",
        ),
        sa.ForeignKeyConstraint(
            ["conta_id"],
            ["contas_web.id"],
            name="fk_sessoes_autenticacao_web_conta_id_contas_web",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessoes_autenticacao_web"),
        sa.UniqueConstraint(
            "token_hash", name="uq_sessoes_autenticacao_web_token_hash"
        ),
    )
    op.create_index(
        "ix_sessoes_autenticacao_web_conta_id",
        "sessoes_autenticacao_web",
        ["conta_id"],
    )
    op.create_index(
        "ix_sessoes_autenticacao_web_expira_em",
        "sessoes_autenticacao_web",
        ["expira_em"],
    )
    op.create_table(
        "limites_login_web",
        sa.Column("chave_hash", sa.String(length=64), nullable=False),
        sa.Column("janela_iniciada_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("falhas", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bloqueada_ate", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tentativa_em", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(chave_hash) = 64", name="ck_limites_login_web_chave_hash_sha256"
        ),
        sa.CheckConstraint(
            "falhas >= 0", name="ck_limites_login_web_falhas_nao_negativas"
        ),
        sa.PrimaryKeyConstraint("chave_hash", name="pk_limites_login_web"),
    )
    op.create_table(
        "eventos_auditoria_web",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("ator_conta_id", sa.BigInteger(), nullable=True),
        sa.Column("acao", sa.String(length=100), nullable=False),
        sa.Column("alvo_tipo", sa.String(length=64), nullable=False),
        sa.Column("alvo_id", sa.String(length=128), nullable=False),
        sa.Column("instante", sa.DateTime(timezone=True), nullable=False),
        sa.Column("justificativa", sa.String(length=500), nullable=True),
        sa.Column("antes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("depois", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "length(acao) > 0", name="ck_eventos_auditoria_web_acao_nao_vazia"
        ),
        sa.CheckConstraint(
            "length(alvo_tipo) > 0", name="ck_eventos_auditoria_web_alvo_tipo_nao_vazio"
        ),
        sa.CheckConstraint(
            "length(alvo_id) > 0", name="ck_eventos_auditoria_web_alvo_id_nao_vazio"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_eventos_auditoria_web"),
    )
    op.create_index(
        "ix_eventos_auditoria_web_ator_instante",
        "eventos_auditoria_web",
        ["ator_conta_id", "instante"],
    )
    op.create_index(
        "ix_eventos_auditoria_web_alvo_instante",
        "eventos_auditoria_web",
        ["alvo_tipo", "alvo_id", "instante"],
    )
    op.execute(
        """
        CREATE FUNCTION bloquear_alteracao_eventos_auditoria_web()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'eventos_auditoria_web e append-only';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_eventos_auditoria_web_append_only
        BEFORE UPDATE OR DELETE ON eventos_auditoria_web
        FOR EACH ROW EXECUTE FUNCTION bloquear_alteracao_eventos_auditoria_web()
        """
    )

    op.add_column(
        "turmas", sa.Column("responsavel_professor_id", sa.BigInteger(), nullable=True)
    )
    op.create_foreign_key(
        "fk_turmas_responsavel_professor_id_professores_web",
        "turmas",
        "professores_web",
        ["responsavel_professor_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_turmas_responsavel_professor_id", "turmas", ["responsavel_professor_id"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    possui_dados = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM contas_web) "
            "OR EXISTS (SELECT 1 FROM sessoes_autenticacao_web) "
            "OR EXISTS (SELECT 1 FROM eventos_auditoria_web) "
            "OR EXISTS (SELECT 1 FROM turmas "
            "WHERE responsavel_professor_id IS NOT NULL)"
        )
    ).scalar_one()
    if possui_dados:
        raise RuntimeError(
            "Downgrade recusado: ha contas, sessoes, auditoria ou turmas com "
            "responsavel web. Preserve os dados e prepare um rollback explicito."
        )

    op.drop_index("ix_turmas_responsavel_professor_id", table_name="turmas")
    op.drop_constraint(
        "fk_turmas_responsavel_professor_id_professores_web",
        "turmas",
        type_="foreignkey",
    )
    op.drop_column("turmas", "responsavel_professor_id")
    op.execute(
        "DROP TRIGGER trg_eventos_auditoria_web_append_only ON eventos_auditoria_web"
    )
    op.execute("DROP FUNCTION bloquear_alteracao_eventos_auditoria_web()")
    op.drop_index(
        "ix_eventos_auditoria_web_alvo_instante", table_name="eventos_auditoria_web"
    )
    op.drop_index(
        "ix_eventos_auditoria_web_ator_instante", table_name="eventos_auditoria_web"
    )
    op.drop_table("eventos_auditoria_web")
    op.drop_table("limites_login_web")
    op.drop_index(
        "ix_sessoes_autenticacao_web_expira_em", table_name="sessoes_autenticacao_web"
    )
    op.drop_index(
        "ix_sessoes_autenticacao_web_conta_id", table_name="sessoes_autenticacao_web"
    )
    op.drop_table("sessoes_autenticacao_web")
    op.drop_table("professores_web")
    op.drop_table("contas_web")
