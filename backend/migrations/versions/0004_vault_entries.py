"""Vault entries: one row per (user, printing, condition, finish) (FR-VLT-06).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vault_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("card_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.SmallInteger(), nullable=False),
        sa.Column("condition", sa.String(length=3), nullable=False),
        sa.Column("finish", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_vault_entries"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_vault_entries_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["cards.scryfall_id"], name="fk_vault_entries_card_id_cards"
        ),
        sa.UniqueConstraint(
            "user_id", "card_id", "condition", "finish", name="uq_vault_entries_identity"
        ),
        sa.CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_vault_entries_quantity"),
        sa.CheckConstraint(
            "condition IN ('NM', 'LP', 'MP', 'HP', 'DMG')", name="ck_vault_entries_condition"
        ),
        sa.CheckConstraint(
            "finish IN ('nonfoil', 'foil', 'etched')", name="ck_vault_entries_finish"
        ),
    )
    op.create_index(
        "ix_vault_entries_user_created",
        "vault_entries",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_vault_entries_card_id", "vault_entries", ["card_id"])


def downgrade() -> None:
    op.drop_index("ix_vault_entries_card_id", table_name="vault_entries")
    op.drop_index("ix_vault_entries_user_created", table_name="vault_entries")
    op.drop_table("vault_entries")
