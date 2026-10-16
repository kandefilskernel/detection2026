"""politique de décision coût-sensible versionnée : chaque réglage (coûts par canal et par opérateur, seuils de
blocage et d'approbation directe) est conservé avec son auteur et sa justification ; une seule version active

Revision ID: 0007
Revises: 0006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "decision_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("bo_users.id"), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("simulation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_decision_policy_active", "decision_policies", ["is_active"], unique=True,
                    postgresql_where=sa.text("is_active"))


def downgrade() -> None:
    op.drop_index("ux_decision_policy_active", table_name="decision_policies")
    op.drop_table("decision_policies")
