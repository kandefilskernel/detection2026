"""institutions partenaires (API ouverte aux opérateurs, banques et au régulateur) et rattachement des données

Revision ID: 0004
Revises: 0003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("providers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("key_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_institutions_code"), "institutions", ["code"], unique=True)
    op.create_index(op.f("ix_institutions_key_hash"), "institutions", ["key_hash"], unique=True)

    op.add_column("scored_transactions", sa.Column("institution", sa.String(length=32), nullable=True))
    op.create_index("ix_scored_institution_time", "scored_transactions", ["institution", "tx_time"])
    op.add_column("cases", sa.Column("institution", sa.String(length=32), nullable=True))
    op.create_index(op.f("ix_cases_institution"), "cases", ["institution"])
    # historique : transactions reçues avant l'API partenaires, par le format natif d'un opérateur
    op.execute("UPDATE scored_transactions SET institution = lower(operator) WHERE operator IS NOT NULL")
    op.execute("UPDATE scored_transactions SET institution = 'visa' WHERE institution IS NULL AND channel = 'VISA_VIRTUAL'")
    op.execute("UPDATE cases c SET institution = s.institution FROM scored_transactions s "
               "WHERE s.transaction_id = c.transaction_id")


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_institution"), table_name="cases")
    op.drop_column("cases", "institution")
    op.drop_index("ix_scored_institution_time", table_name="scored_transactions")
    op.drop_column("scored_transactions", "institution")
    op.drop_index(op.f("ix_institutions_key_hash"), table_name="institutions")
    op.drop_index(op.f("ix_institutions_code"), table_name="institutions")
    op.drop_table("institutions")
