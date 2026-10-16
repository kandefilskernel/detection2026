"""sécurité du back-office : double authentification (TOTP), verrouillage après échecs de connexion, principe des
quatre yeux pour les déblocages importants, quota de débit propre à chaque institution partenaire

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bo_users", sa.Column("totp_secret", sa.String(length=255), nullable=True))
    op.add_column("bo_users", sa.Column("totp_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("bo_users", sa.Column("totp_last_step", sa.BigInteger(), nullable=True))
    op.add_column("bo_users", sa.Column("failed_logins", sa.Integer(), server_default="0", nullable=False))
    op.add_column("bo_users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "unblock_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("transaction_id", sa.String(length=64), nullable=False),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("bo_users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="EN_ATTENTE", nullable=False),
        sa.Column("decided_by", sa.Integer(), sa.ForeignKey("bo_users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_unblock_requests_case_id"), "unblock_requests", ["case_id"])
    op.create_index(op.f("ix_unblock_requests_status"), "unblock_requests", ["status"])
    # une seule demande en attente par dossier
    op.create_index("ux_unblock_pending_case", "unblock_requests", ["case_id"], unique=True,
                    postgresql_where=sa.text("status = 'EN_ATTENTE'"))

    op.add_column("institutions", sa.Column("rate_limit_per_s", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("institutions", "rate_limit_per_s")
    op.drop_index("ux_unblock_pending_case", table_name="unblock_requests")
    op.drop_index(op.f("ix_unblock_requests_status"), table_name="unblock_requests")
    op.drop_index(op.f("ix_unblock_requests_case_id"), table_name="unblock_requests")
    op.drop_table("unblock_requests")
    for col in ("locked_until", "failed_logins", "totp_last_step", "totp_enabled", "totp_secret"):
        op.drop_column("bo_users", col)
