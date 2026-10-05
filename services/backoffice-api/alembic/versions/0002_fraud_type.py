"""typologie de fraude (fraud_type) sur les transactions scorées et les dossiers

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scored_transactions", sa.Column("fraud_type", sa.String(length=24), nullable=True))
    op.add_column("scored_transactions", sa.Column("fraud_type_probability", sa.Float(), nullable=True))
    op.create_index("ix_scored_fraud_type_time", "scored_transactions", ["fraud_type", "tx_time"])
    op.add_column("cases", sa.Column("fraud_type", sa.String(length=24), nullable=True))
    op.create_index(op.f("ix_cases_fraud_type"), "cases", ["fraud_type"])


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_fraud_type"), table_name="cases")
    op.drop_column("cases", "fraud_type")
    op.drop_index("ix_scored_fraud_type_time", table_name="scored_transactions")
    op.drop_column("scored_transactions", "fraud_type_probability")
    op.drop_column("scored_transactions", "fraud_type")
