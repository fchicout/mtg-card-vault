"""The vault: what a collector owns, and the rules that keep it consistent (FR-VLT-01..07)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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


def unit_price(prices: Prices, finish: Finish) -> Decimal | None:
    """The USD price that matches the finish; None when the source has none (never zero)."""
    return {
        Finish.NONFOIL: prices.usd,
        Finish.FOIL: prices.usd_foil,
        Finish.ETCHED: prices.usd_etched,
    }[finish]
