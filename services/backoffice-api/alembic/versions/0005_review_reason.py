"""motif de revue des dossiers : alerte du modèle, plainte, ou cas choisi par la file de revue (incertitude,
nouveauté, réseau, échantillon témoin) -> mesure non biaisée des fraudes manquées et apport de chaque source

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("review_reason", sa.String(length=16), server_default="ALERTE", nullable=False))
    op.create_index(op.f("ix_cases_review_reason"), "cases", ["review_reason"])
    op.execute("UPDATE cases SET review_reason = 'PLAINTE' WHERE action = 'APPROVE' AND resolution_note LIKE 'Plainte client%'")
    op.execute("UPDATE cases SET review_reason = 'REVUE' WHERE action = 'APPROVE' AND resolution_note LIKE 'Revue d''analyste%'")


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_review_reason"), table_name="cases")
    op.drop_column("cases", "review_reason")
