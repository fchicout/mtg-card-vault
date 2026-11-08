"""PostgreSQL store of card snapshots: one atomic upsert per printing (FR-DAT-02, ADR-007)."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mtgvault.adapters.db.models import CardRow, VaultEntryRow
from mtgvault.application.vault_query import normalise
from mtgvault.domain.card import Card, Prices
from mtgvault.domain.vault import CardSnapshot

_PRICE_COLUMNS = ("usd", "usd_foil", "usd_etched", "eur", "eur_foil", "eur_etched")


def snapshot_from_row(row: CardRow) -> CardSnapshot:
    prices = Prices(**{name: _money(getattr(row, name)) for name in _PRICE_COLUMNS})
    card = Card(
        id=row.scryfall_id,
        oracle_id=row.oracle_id,
        name=row.name,
        set_code=row.set_code,
        set_name=row.set_name,
        collector_number=row.collector_number,
        lang=row.lang,
        rarity=row.rarity,
        layout=row.layout,
        type_line=row.type_line,
        mana_cost=row.mana_cost,
        colors=tuple(row.colors),
        finishes=tuple(row.finishes),
        image_small=row.image_uri_small,
        image_normal=row.image_uri_normal,
        prices=prices,
    )
    return CardSnapshot(card=card, prices_updated_at=row.prices_updated_at)


def _money(value: Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(value)


class SqlAlchemyCardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _values(card: Card, now: datetime) -> dict[str, Any]:
        return {
            "scryfall_id": card.id,
            "oracle_id": card.oracle_id,
            "name": card.name,
            "name_search": normalise(card.name),
            "set_code": card.set_code,
            "set_name": card.set_name,
            "collector_number": card.collector_number,
            "lang": card.lang,
            "rarity": card.rarity,
            "layout": card.layout,
            "type_line": card.type_line,
            "mana_cost": card.mana_cost,
            "colors": list(card.colors),
            "finishes": list(card.finishes),
            "image_uri_small": card.image_small,
            "image_uri_normal": card.image_normal,
            **{name: getattr(card.prices, name) for name in _PRICE_COLUMNS},
            "prices_updated_at": now,
            "data_updated_at": now,
        }

    def upsert_snapshot(self, card: Card, now: datetime) -> None:
        self.upsert_snapshots([card], now)

    def upsert_snapshots(self, cards: Sequence[Card], now: datetime) -> None:
        """One statement for the whole batch (the daily refresh sends 75 at a time)."""
        unique = {card.id: card for card in cards}  # one row per id: PostgreSQL refuses duplicates
        if not unique:
            return
        rows = [self._values(card, now) for card in unique.values()]
        statement = insert(CardRow).values(rows)
        statement = statement.on_conflict_do_update(
            index_elements=[CardRow.scryfall_id],
            set_={key: statement.excluded[key] for key in rows[0] if key != "scryfall_id"},
        )
        self._session.execute(statement)

    def owned_ids(self, after: UUID | None, limit: int) -> list[UUID]:
        """Ids of cards that at least one user owns, in id order, ``limit`` after ``after``."""
        statement = select(VaultEntryRow.card_id).distinct().order_by(VaultEntryRow.card_id)
        if after is not None:
            statement = statement.where(VaultEntryRow.card_id > after)
        return list(self._session.scalars(statement.limit(limit)))

    def prices_of(self, card_ids: Sequence[UUID]) -> dict[UUID, Prices]:
        rows = self._session.scalars(select(CardRow).where(CardRow.scryfall_id.in_(card_ids)))
        return {row.scryfall_id: snapshot_from_row(row).card.prices for row in rows}

    def get(self, card_id: UUID) -> CardSnapshot | None:
        row = self._session.get(CardRow, card_id)
        return None if row is None else snapshot_from_row(row)
