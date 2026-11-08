"""ORM tables. Import this module so Alembic's metadata sees every table."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from mtgvault.adapters.db.base import Base


class UserRow(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    # The identity provider's stable subject: the only identity key (FR-AUTH-05).
    sub: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CardRow(Base):
    """A printing someone owns: shared by all users, no personal data (FR-DAT-02)."""

    __tablename__ = "cards"
    __table_args__ = (
        Index("ix_cards_oracle_id", "oracle_id"),
        Index("ix_cards_set_code", "set_code"),
    )

    scryfall_id: Mapped[UUID] = mapped_column(primary_key=True)
    oracle_id: Mapped[UUID | None]
    name: Mapped[str] = mapped_column(Text)
    # Lower-case, accent-free copy of the name: the vault's "contains" search (FR-VLT-05).
    name_search: Mapped[str] = mapped_column(Text)
    set_code: Mapped[str] = mapped_column(String(10))
    set_name: Mapped[str] = mapped_column(Text)
    collector_number: Mapped[str] = mapped_column(String(20))
    lang: Mapped[str] = mapped_column(String(10))
    rarity: Mapped[str] = mapped_column(String(20))
    layout: Mapped[str] = mapped_column(String(30))
    type_line: Mapped[str | None] = mapped_column(Text)
    mana_cost: Mapped[str | None] = mapped_column(Text)
    colors: Mapped[list[str]] = mapped_column(ARRAY(Text))
    finishes: Mapped[list[str]] = mapped_column(ARRAY(Text))
    image_uri_small: Mapped[str | None] = mapped_column(Text)
    image_uri_normal: Mapped[str | None] = mapped_column(Text)
    usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    usd_foil: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    usd_etched: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eur: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eur_foil: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    eur_etched: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    prices_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    data_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class VaultEntryRow(Base):
    __tablename__ = "vault_entries"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "card_id", "condition", "finish", name="uq_vault_entries_identity"
        ),
        CheckConstraint("quantity BETWEEN 1 AND 9999", name="ck_vault_entries_quantity"),
        CheckConstraint(
            "condition IN ('NM', 'LP', 'MP', 'HP', 'DMG')", name="ck_vault_entries_condition"
        ),
        CheckConstraint("finish IN ('nonfoil', 'foil', 'etched')", name="ck_vault_entries_finish"),
        Index("ix_vault_entries_user_created", "user_id", text("created_at DESC")),
        Index("ix_vault_entries_card_id", "card_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_vault_entries_user_id_users")
    )
    card_id: Mapped[UUID] = mapped_column(
        ForeignKey("cards.scryfall_id", name="fk_vault_entries_card_id_cards")
    )
    quantity: Mapped[int] = mapped_column(SmallInteger)
    condition: Mapped[str] = mapped_column(String(3))
    finish: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
