"""Baseline: an empty schema that establishes the migration chain.

Revision ID: 0001
Revises:
Create Date: 2026-11-07
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to create yet: tables arrive with the features that need them."""


def downgrade() -> None:
    """Nothing to drop."""
