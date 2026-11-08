"""Refreshing stale prices when they are looked at (US-023, FR-PRC-05).

The caller runs this after its response has been sent, so a slow or failing source never delays
the response. The guard keeps at most one refresh per card in flight in this process; the
daily job in the worker covers everything else.
"""

import logging
import threading
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from mtgvault.application.price_refresh import RefreshSummary

_log = logging.getLogger("mtgvault.pricing")
MAX_PER_REQUEST = 75  # one batch at most per request


class Refresher(Protocol):
    def refresh(self, card_ids: Sequence[UUID]) -> RefreshSummary: ...


class InFlight:
    """The ids being refreshed right now (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ids: set[UUID] = set()

    def claim(self, card_ids: Sequence[UUID]) -> list[UUID]:
        """The ids nobody is refreshing yet; they now count as in flight."""
        with self._lock:
            fresh = [i for i in dict.fromkeys(card_ids) if i not in self._ids]
            self._ids.update(fresh)
            return fresh

    def release(self, card_ids: Sequence[UUID]) -> None:
        with self._lock:
            self._ids.difference_update(card_ids)

    def __len__(self) -> int:
        with self._lock:
            return len(self._ids)


class LazyPriceRefresher:
    def __init__(self, refresher: Refresher, guard: InFlight | None = None) -> None:
        self._refresher = refresher
        self._guard = guard or InFlight()

    def refresh_now(self, card_ids: Sequence[UUID]) -> RefreshSummary | None:
        """Refresh the ids nobody else is refreshing. Never raises; None when nothing was done."""
        claimed = self._guard.claim(card_ids[:MAX_PER_REQUEST])
        if not claimed:
            return None
        try:
            return self._refresher.refresh(claimed)
        except Exception:
            _log.exception("lazy price refresh crashed")
            return None
        finally:
            self._guard.release(claimed)
