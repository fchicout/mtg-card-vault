"""Vault use cases (US-005..US-011, UC-03..UC-06). The user id always comes from the token."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.lazy_refresh import MAX_PER_REQUEST, LazyPriceRefresher
from mtgvault.application.ports import UnitOfWork
from mtgvault.application.vault_query import VaultQuery
from mtgvault.domain.card import Card
from mtgvault.domain.errors import (
    FieldError,
    NotFound,
    RateLimited,
    UpstreamUnavailable,
    ValidationFailed,
)
from mtgvault.domain.vault import (
    CardSnapshot,
    Condition,
    Finish,
    VaultItem,
    VaultSummary,
    validate_finish,
    validate_quantity,
)

_log = logging.getLogger("mtgvault.pricing")
DEFAULT_STALE_AFTER = timedelta(hours=24)
_NO_ENTRY = "No such entry."


def _utc_now() -> datetime:
    return datetime.now(UTC)


class VaultService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        catalog: CatalogService,
        clock: Callable[[], datetime] = _utc_now,
        stale_after: timedelta = DEFAULT_STALE_AFTER,
        lazy: LazyPriceRefresher | None = None,
    ) -> None:
        self._uow = unit_of_work_factory
        self._catalog = catalog
        self._clock = clock
        self._stale_after = stale_after
        self._lazy = lazy

    # ------------------------------------------------------------------ add
    def add(
        self, user_id: UUID, card_id: UUID, quantity: int, condition: Condition, finish: Finish
    ) -> tuple[VaultItem, bool]:
        """Create the entry or add to the existing one; returns it and whether it was created."""
        validate_quantity(quantity)
        card, fresh = self._resolve(card_id)  # no database transaction is open during the call
        validate_finish(finish, card.finishes)
        now = self._clock()
        with self._uow() as unit:
            if fresh:
                unit.cards.upsert_snapshot(card, now)
            entry, created = unit.vault.add_or_merge(
                user_id, card_id, quantity, condition, finish, now
            )
            item = unit.vault.get_item(user_id, entry.id)
            unit.commit()
        if item is None:  # pragma: no cover  # the row was just written in this transaction
            raise NotFound(_NO_ENTRY)
        return item, created

    def _resolve(self, card_id: UUID) -> tuple[Card, bool]:
        """The printing from the catalogue, or from the local snapshot while the source is down."""
        try:
            return self._catalog.get(card_id), True
        except (UpstreamUnavailable, RateLimited):
            with self._uow() as unit:
                snapshot = unit.cards.get(card_id)
            if snapshot is None:
                raise
            return snapshot.card, False

    # ------------------------------------------------------------------ read
    def list(self, user_id: UUID, query: VaultQuery) -> tuple[list[VaultItem], int]:
        with self._uow() as unit:
            return unit.vault.list_items(user_id, query)

    def summary(self, user_id: UUID) -> VaultSummary:
        with self._uow() as unit:
            return unit.vault.summary(user_id)

    def get(self, user_id: UUID, entry_id: UUID) -> VaultItem:
        with self._uow() as unit:
            item = unit.vault.get_item(user_id, entry_id)
        if item is None:
            raise NotFound(_NO_ENTRY)
        return item

    # ------------------------------------------------------------------ change
    def edit(
        self,
        user_id: UUID,
        entry_id: UUID,
        quantity: int | None,
        condition: Condition | None,
        finish: Finish | None,
    ) -> tuple[VaultItem, bool]:
        """Change an entry; the second value says that it merged into another entry."""
        if quantity is None and condition is None and finish is None:
            raise ValidationFailed(
                "Nothing to change.",
                (FieldError("quantity", "Send quantity, condition or finish."),),
            )
        if quantity is not None:
            validate_quantity(quantity)
        now = self._clock()
        with self._uow() as unit:
            current = unit.vault.get_item(user_id, entry_id)
            if current is None:
                raise NotFound(_NO_ENTRY)
            if finish is not None:
                validate_finish(finish, current.snapshot.card.finishes)
            result = unit.vault.update(user_id, entry_id, quantity, condition, finish, now)
            if result is None:  # pragma: no cover  # deleted between the two statements
                raise NotFound(_NO_ENTRY)
            entry, merged = result
            item = unit.vault.get_item(user_id, entry.id)
            unit.commit()
        if item is None:  # pragma: no cover
            raise NotFound(_NO_ENTRY)
        return item, merged

    def remove(self, user_id: UUID, entry_id: UUID) -> None:
        with self._uow() as unit:
            removed = unit.vault.delete(user_id, entry_id)
            unit.commit()
        if not removed:
            raise NotFound(_NO_ENTRY)

    # ------------------------------------------------------------------ prices
    def prices_stale(self, snapshot: CardSnapshot) -> bool:
        """Prices older than the threshold, or never refreshed, are shown as stale (FR-DAT-03)."""
        updated = snapshot.prices_updated_at
        return updated is None or self._clock() - updated >= self._stale_after

    def owned_prices(self, subject: str, card_id: UUID) -> CardSnapshot | None:
        """The stored copy of a printing the user owns (its price freshness), else None.

        An extra on the card page: when the database cannot answer, the page still works.
        """
        try:
            with self._uow() as unit:
                user_id = unit.users.id_of(subject)
                return None if user_id is None else unit.vault.owned_snapshot(user_id, card_id)
        except Exception:
            _log.warning("could not read the stored prices", exc_info=True)
            return None

    def refresh_stale_prices(self, user_id: UUID) -> None:
        """Refresh, in this process, the user's printings whose prices are stale (FR-PRC-05).

        Best effort and meant for a background task: it talks to the data source, may take a while
        and never raises.
        """
        if self._lazy is None:
            return
        try:
            with self._uow() as unit:
                ids = unit.vault.stale_card_ids(
                    user_id, self._clock() - self._stale_after, MAX_PER_REQUEST
                )
            if ids:
                self._lazy.refresh_now(ids)
        except Exception:
            _log.exception("could not look for stale prices")

    def refresh_card_if_stale(self, card_id: UUID) -> None:
        """Refresh one printing when we hold a snapshot of it and its prices are stale."""
        if self._lazy is None:
            return
        try:
            with self._uow() as unit:
                snapshot = unit.cards.get(card_id)
            if snapshot is not None and self.prices_stale(snapshot):
                self._lazy.refresh_now([card_id])
        except Exception:
            _log.exception("could not look for stale prices")
