"""The vault: what a collector owns, and the rules that keep it consistent (FR-VLT-01..07)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID

from mtgvault.domain.card import Card, Prices
from mtgvault.domain.errors import FieldError, ValidationFailed

MAX_QUANTITY = 9999


class Condition(StrEnum):
    NM = "NM"
    LP = "LP"
    MP = "MP"
    HP = "HP"
    DMG = "DMG"


class Finish(StrEnum):
    NONFOIL = "nonfoil"
    FOIL = "foil"
    ETCHED = "etched"


class Currency(StrEnum):
    USD = "usd"
    EUR = "eur"


_CENT = Decimal("0.01")


@dataclass(frozen=True)
class VaultEntry:
    id: UUID
    user_id: UUID
    card_id: UUID
    quantity: int
    condition: Condition
    finish: Finish
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CardSnapshot:
    """The locally stored copy of a printing (FR-DAT-02) with its freshness."""

    card: Card
    prices_updated_at: datetime | None


@dataclass(frozen=True)
class VaultItem:
    """An entry together with its card snapshot, as listed."""

    entry: VaultEntry
    snapshot: CardSnapshot

    @property
    def unit_price(self) -> Decimal | None:
        return unit_price(self.snapshot.card.prices, self.entry.finish)

    @property
    def unit_price_eur(self) -> Decimal | None:
        return unit_price(self.snapshot.card.prices, self.entry.finish, Currency.EUR)

    @property
    def line_value_usd(self) -> Decimal | None:
        return line_value(self.unit_price, self.entry.quantity)

    @property
    def line_value_eur(self) -> Decimal | None:
        return line_value(self.unit_price_eur, self.entry.quantity)


@dataclass(frozen=True)
class VaultSummary:
    """What a collection is worth (FR-PRC-03). Unpriced entries add nothing to a value, so a
    non-zero ``unpriced_*`` count means the value is a lower bound."""

    total_cards: int
    entries: int
    value_usd: Decimal
    value_eur: Decimal
    unpriced_usd: int
    unpriced_eur: int
    oldest_prices_updated_at: datetime | None
    newest_prices_updated_at: datetime | None


def validate_quantity(quantity: int) -> int:
    if not 1 <= quantity <= MAX_QUANTITY:
        raise ValidationFailed(
            "Invalid quantity.",
            (FieldError("quantity", f"Use a number from 1 to {MAX_QUANTITY}."),),
        )
    return quantity


def validate_finish(finish: Finish, available: tuple[str, ...]) -> Finish:
    if finish.value not in available:
        allowed = ", ".join(available) or "none"
        raise ValidationFailed(
            "This printing is not available in that finish.",
            (FieldError("finish", f"Allowed finishes for this printing: {allowed}."),),
        )
    return finish


def merged_quantity(first: int, second: int) -> int:
    """The quantity of two merged entries; over the cap is a validation error, never a clamp."""
    total = first + second
    if total > MAX_QUANTITY:
        raise ValidationFailed(
            "The total would be too large.",
            (FieldError("quantity", f"A vault entry holds at most {MAX_QUANTITY} cards."),),
        )
    return total


def unit_price(prices: Prices, finish: Finish, currency: Currency = Currency.USD) -> Decimal | None:
    """The price in the currency that matches the finish; None when the source has none.

    A missing price is never zero (FR-PRC-02).
    """
    if currency is Currency.EUR:
        by_finish = {
            Finish.NONFOIL: prices.eur,
            Finish.FOIL: prices.eur_foil,
            Finish.ETCHED: prices.eur_etched,
        }
    else:
        by_finish = {
            Finish.NONFOIL: prices.usd,
            Finish.FOIL: prices.usd_foil,
            Finish.ETCHED: prices.usd_etched,
        }
    return by_finish[finish]


def line_value(price: Decimal | None, quantity: int) -> Decimal | None:
    """Unit price x quantity in exact decimals, to the cent; None stays None (unpriced)."""
    if price is None:
        return None
    return (price * quantity).quantize(_CENT, rounding=ROUND_HALF_UP)
