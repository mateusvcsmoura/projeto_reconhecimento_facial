"""schema inicial

Gerada por autogenerate e revisada manualmente. Ajustes feitos sobre a
saida automatica:

  * chaves primarias como GENERATED ALWAYS AS IDENTITY (o autogenerate
    emitia apenas BIGSERIAL implicito);
  * comentarios explicando as decisoes de modelagem;
  * downgrade verificado (drop na ordem inversa da FK).

Diferencas em relacao ao SQLite de origem, e o porque:

  * `alunos.matricula` separada da PK. No SQLite, `id` acumulava chave
    primaria + matricula + `biometria_id`.
  * `alunos.biometria_id` removida: era copia literal de `id`.
  * `alunos.foto_path` (caminho absoluto) vira `foto_arquivo` (relativo a
    STORAGE_DIR). O caminho absoluto tornava o banco nao portavel.
  * `presencas.data_hora TEXT` vira `registrado_em TIMESTAMPTZ` +
    `data_referencia DATE`.
  * UNIQUE(aluno_id, data_referencia): a regra "uma presenca por dia"
    passa a ser garantida pelo banco.
  * FOREIGN KEY com ON DELETE CASCADE: viabiliza a exclusao de aluno.

Revision ID: 0001
Revises:
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alunos",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("matricula", sa.String(length=32), nullable=False),
        sa.Column("nome", sa.String(length=255), nullable=False),
        # Relativo a STORAGE_DIR. NULL quando o aluno ainda nao tem imagem
        # de referencia utilizavel.
        sa.Column("foto_arquivo", sa.String(length=255), nullable=True),
        sa.Column(
            "criado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(btrim(matricula)) > 0", name=op.f("ck_alunos_matricula_nao_vazia")
        ),
        sa.CheckConstraint(
            "length(btrim(nome)) > 0", name=op.f("ck_alunos_nome_nao_vazio")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alunos")),
        sa.UniqueConstraint("matricula", name="uq_alunos_matricula"),
    )

    op.create_table(
        "presencas",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("aluno_id", sa.BigInteger(), nullable=False),
        # Instante exato do registro.
        sa.Column("registrado_em", sa.DateTime(timezone=True), nullable=False),
        # "Dia" da regra de negocio, calculado pela aplicacao em APP_TIMEZONE.
        # Coluna propria porque `AT TIME ZONE <literal>` sobre timestamptz e
        # STABLE, nao IMMUTABLE, e nao pode ser coluna gerada nem indexada.
        sa.Column("data_referencia", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["aluno_id"],
            ["alunos.id"],
            name=op.f("fk_presencas_aluno_id_alunos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_presencas")),
        sa.UniqueConstraint(
            "aluno_id", "data_referencia", name="uq_presencas_aluno_dia"
        ),
    )

    op.create_index(
        "ix_presencas_data_referencia",
        "presencas",
        ["data_referencia"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_presencas_data_referencia", table_name="presencas")
    # presencas antes de alunos: a FK aponta para alunos.
    op.drop_table("presencas")
    op.drop_table("alunos")
