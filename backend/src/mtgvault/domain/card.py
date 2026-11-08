"""Cards as the application sees them, independent of any data source (FR-CAT-03, ADR-006).

Prices are ``Decimal`` (never floats) and ``None`` when the source has no price: a missing price is
not a price of zero (FR-PRC-02).
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class Prices:
    usd: Decimal | None = None
    usd_foil: Decimal | None = None
    usd_etched: Decimal | None = None
    eur: Decimal | None = None
    eur_foil: Decimal | None = None
    eur_etched: Decimal | None = None


@dataclass(frozen=True)
class CardFace:
    """One face of a multi-faced card (transform, modal, split, reversible)."""

    name: str
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    image_small: str | None = None
    image_normal: str | None = None


@dataclass(frozen=True)
class Card:
    """One printing. For multi-faced cards the card-level fields describe the whole card."""

    id: UUID
    oracle_id: UUID | None
    name: str
    set_code: str
    set_name: str
    collector_number: str
    lang: str
    rarity: str
    layout: str
    type_line: str | None = None
    mana_cost: str | None = None
    oracle_text: str | None = None
    colors: tuple[str, ...] = ()
    finishes: tuple[str, ...] = ()
    image_small: str | None = None
    image_normal: str | None = None
    prices: Prices = Prices()
    faces: tuple[CardFace, ...] = ()


@dataclass(frozen=True)
class ResultPage[T]:
    """One page of a larger result. ``total`` is None when the source does not say."""

    items: tuple[T, ...]
    page: int
    has_more: bool
    total: int | None = None
