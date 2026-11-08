"""Refreshing the prices (and data) of cards that someone owns (US-022, FR-PRC-04, ADR-012).

Used by the daily job for every owned card and by the lazy refresh for a few stale ones. Cards
are fetched from the source in batches of 75; each batch is committed on its own, so a failure
later in the run never undoes what is already stored. A failed batch leaves its cards as they were.
"""

import logging
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from mtgvault.application.ports import CardDataProvider, UnitOfWork
from mtgvault.domain.errors import DomainError

_log = logging.getLogger("mtgvault.pricing")
BATCH_SIZE = 75
ABORT_AFTER_FAILED_BATCHES = 3  # an outage: stop asking instead of waiting for every batch


@dataclass(frozen=True)
class RefreshSummary:
    updated: int = 0  # prices differ from what was stored
    unchanged: int = 0  # refreshed, same prices
    not_found: int = 0  # the source no longer knows the card; stored data is kept
    failed: int = 0  # cards of batches that could not be fetched or stored
    batches: int = 0
    aborted: bool = False
    seconds: float = 0.0

    @property
    def refreshed(self) -> int:
        return self.updated + self.unchanged


class PriceRefresher:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        provider: CardDataProvider,
        clock: Callable[[], datetime],
        timer: Callable[[], float] = time.monotonic,
    ) -> None:
        self._uow = unit_of_work_factory
        self._provider = provider
        self._clock = clock
        self._timer = timer

    def refresh_all(self, should_stop: Callable[[], bool] = lambda: False) -> RefreshSummary:
        """Every owned card, page by page. ``should_stop`` is checked between batches."""
        return self._run(self._owned_batches(), should_stop)

    def refresh(self, card_ids: Sequence[UUID]) -> RefreshSummary:
        """The given cards only (the lazy refresh)."""
        unique = list(dict.fromkeys(card_ids))
        batches = (unique[i : i + BATCH_SIZE] for i in range(0, len(unique), BATCH_SIZE))
        return self._run(batches, lambda: False)

    # ------------------------------------------------------------------ internals
    def _owned_batches(self) -> Iterator[list[UUID]]:
        after: UUID | None = None
        while True:
            with self._uow() as unit:
                batch = unit.cards.owned_ids(after, BATCH_SIZE)
            if not batch:
                return
            after = batch[-1]
            yield batch

    def _run(
        self, batches: Iterable[list[UUID]], should_stop: Callable[[], bool]
    ) -> RefreshSummary:
        started = self._timer()
        totals = {"updated": 0, "unchanged": 0, "not_found": 0, "failed": 0, "batches": 0}
        failures_in_a_row, aborted = 0, False
        for batch in batches:
            if should_stop():
                break
            totals["batches"] += 1
            try:
                updated, unchanged, missing = self._refresh_batch(batch)
            except DomainError as error:
                totals["failed"] += len(batch)
                failures_in_a_row += 1
                _log.warning("price batch failed: %s", type(error).__name__)
                if failures_in_a_row >= ABORT_AFTER_FAILED_BATCHES:
                    aborted = True
                    break
                continue
            failures_in_a_row = 0
            totals["updated"] += updated
            totals["unchanged"] += unchanged
            totals["not_found"] += missing
        return RefreshSummary(**totals, aborted=aborted, seconds=round(self._timer() - started, 3))

    def _refresh_batch(self, batch: list[UUID]) -> tuple[int, int, int]:
        found = self._provider.lookup(batch)  # no transaction is open during the call
        now = self._clock()
        with self._uow() as unit:
            before = unit.cards.prices_of([card.id for card in found.cards])
            unit.cards.upsert_snapshots(found.cards, now)
            unit.commit()
        updated = sum(1 for card in found.cards if before.get(card.id) != card.prices)
        return updated, len(found.cards) - updated, len(found.not_found)
