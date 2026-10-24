"""embeddings faciais

Gerada por autogenerate e revisada a mao: o autogenerate detectou as tres
colunas, mas -- como na 0001 -- nao emitiu a CheckConstraint.

Motivacao: o desenho anterior chamava
DeepFace.verify() para cada aluno a cada ciclo de comparacao, recalculando
do zero o embedding do frame E o da foto de referencia -- ate 2N inferencias
Facenet512 por ciclo, sendo N delas puro desperdicio, ja que as fotos de
referencia nao mudam.

Com o embedding persistido, o custo por ciclo passa a ser uma inferencia,
independente de N.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK_EMBEDDING = (
    "(embedding IS NULL AND embedding_modelo IS NULL AND embedding_dim IS NULL)"
    " OR "
    "(embedding IS NOT NULL AND embedding_modelo IS NOT NULL"
    " AND embedding_dim IS NOT NULL AND embedding_dim > 0)"
)


def upgrade() -> None:
    # Nullable: alunos cadastrados antes desta fase ficam sem embedding ate
    # o backfill rodar (scripts/backfill_embeddings.py).
    op.add_column(
        "alunos",
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "alunos",
        sa.Column("embedding_modelo", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "alunos",
        sa.Column("embedding_dim", sa.SmallInteger(), nullable=True),
    )

    # Os tres campos andam juntos: um vetor sem o modelo que o gerou e
    # inutilizavel, e comparar vetores de modelos diferentes produz
    # identificacao errada em silencio.
    # Nome SEM o prefixo: a naming_convention do MetaData ja adiciona
    # "ck_<tabela>_". Passar o nome completo aqui produziria
    # "ck_alunos_ck_alunos_embedding_completo" -- e o `alembic check` NAO
    # pegaria a divergencia, porque autogenerate nao compara CHECKs.
    op.create_check_constraint("embedding_completo", "alunos", _CHECK_EMBEDDING)


def downgrade() -> None:
    # Sem prefixo aqui tambem: drop_constraint passa pela mesma
    # naming_convention que create_check_constraint.
    op.drop_constraint("embedding_completo", "alunos", type_="check")
    op.drop_column("alunos", "embedding_dim")
    op.drop_column("alunos", "embedding_modelo")
    op.drop_column("alunos", "embedding")
