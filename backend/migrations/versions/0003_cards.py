"""Cards: the shared, personal-data-free snapshot of owned printings (FR-DAT-02, ADR-007).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    money = sa.Numeric(10, 2)
    op.create_table(
        "cards",
        sa.Column("scryfall_id", sa.Uuid(), nullable=False),
        sa.Column("oracle_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_search", sa.Text(), nullable=False),
        sa.Column("set_code", sa.String(length=10), nullable=False),
        sa.Column("set_name", sa.Text(), nullable=False),
        sa.Column("collector_number", sa.String(length=20), nullable=False),
        sa.Column("lang", sa.String(length=10), nullable=False),
        sa.Column("rarity", sa.String(length=20), nullable=False),
        sa.Column("layout", sa.String(length=30), nullable=False),
        sa.Column("type_line", sa.Text(), nullable=True),
        sa.Column("mana_cost", sa.Text(), nullable=True),
        sa.Column("colors", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("finishes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("image_uri_small", sa.Text(), nullable=True),
        sa.Column("image_uri_normal", sa.Text(), nullable=True),
        sa.Column("usd", money, nullable=True),
        sa.Column("usd_foil", money, nullable=True),
        sa.Column("usd_etched", money, nullable=True),
        sa.Column("eur", money, nullable=True),
        sa.Column("eur_foil", money, nullable=True),
        sa.Column("eur_etched", money, nullable=True),
        sa.Column("prices_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("scryfall_id", name="pk_cards"),
    )
    op.create_index("ix_cards_oracle_id", "cards", ["oracle_id"])
    op.create_index("ix_cards_set_code", "cards", ["set_code"])


def downgrade() -> None:
    op.drop_index("ix_cards_set_code", table_name="cards")
    op.drop_index("ix_cards_oracle_id", table_name="cards")
    op.drop_table("cards")
