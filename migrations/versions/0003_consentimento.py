"""consentimento do titular

Dado biometrico e dado pessoal sensivel (LGPD art. 5, II). Seu tratamento
exige consentimento especifico e destacado do titular (art. 11, I) -- e
registrar quando esse consentimento foi dado e o minimo para conseguir
demonstra-lo depois.

Nullable de proposito: linhas anteriores a esta fase nao tem o dado, e
fingir uma data para elas seria pior do que admitir a lacuna. A aplicacao,
essa sim, nao cadastra sem consentimento.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alunos",
        sa.Column("consentimento_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alunos", "consentimento_em")
