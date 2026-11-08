"""Ports: interfaces the application layer needs, implemented by adapters (ADR-006)."""

from collections.abc import Callable
from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from mtgvault.application.vault_query import VaultQuery
from mtgvault.domain.card import Card, ResultPage
from mtgvault.domain.identity import Principal
from mtgvault.domain.user import User
from mtgvault.domain.vault import CardSnapshot, Condition, Finish, VaultEntry, VaultItem


class TokenVerifier(Protocol):
    """Turns a bearer token into the caller's identity (ADR-003, FR-AUTH-05).

    Raises ``Unauthenticated`` for any token that is not acceptable (the reason is only logged)
    and ``UpstreamUnavailable`` when the identity provider's keys cannot be obtained at all.
    """

    def verify(self, token: str) -> Principal: ...


class ReadinessProbe(Protocol):
    """Reports whether the service's dependencies (the database) are reachable."""

    def is_ready(self) -> bool: ...


class UserRepository(Protocol):
    """Persistence of users, keyed by the token subject."""

    def provision(self, principal: Principal, now: datetime, refresh_after: timedelta) -> User:
        """Create the user if unknown, otherwise bring the profile up to date; race-safe.

        ``last_login_at`` is only rewritten when it is older than ``refresh_after``, so a busy
        client does not cause a write on every request.
        """
        ...


class UnitOfWork(Protocol):
    """One transaction around a use case. Leaving the block without ``commit`` rolls back."""

    @property
    def users(self) -> UserRepository: ...

    @property
    def cards(self) -> "CardRepository": ...

    @property
    def vault(self) -> "VaultRepository": ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class CardDataProvider(Protocol):
    """Where card data comes from (Scryfall today; ADR-006, ADR-007).

    Raises ``NotFound`` for an unknown card, ``RateLimited`` or ``UpstreamUnavailable`` when the
    source cannot answer. A search without matches is an empty page, not an error.
    """

    def search(self, query: str, page: int) -> ResultPage[Card]:
        """Unique cards matching a Scryfall-syntax ``query`` (built by the application)."""
        ...

    def get(self, card_id: UUID) -> Card: ...

    def printings(self, oracle_id: UUID, page: int) -> ResultPage[Card]:
        """Every printing of a card, newest first."""
        ...


class Cache(Protocol):
    """A small, short-lived cache. Implementations are thread-safe and bounded."""

    def get_or_load[T](self, key: str, loader: Callable[[], T]) -> T:
        """The cached value, or ``loader()``'s result stored under ``key``.

        Concurrent callers with the same key share one ``loader`` call; a loader that raises
        stores nothing.
        """
        ...


class CardRepository(Protocol):
    """The shared snapshots of printings that someone owns (FR-DAT-02)."""

    def upsert_snapshot(self, card: Card, now: datetime) -> None:
        """Insert or refresh the printing; prices and data timestamps become ``now``."""
        ...

    def get(self, card_id: UUID) -> CardSnapshot | None: ...


class VaultRepository(Protocol):
    """A user's entries. EVERY method takes the user id first: there is no unscoped access."""

    def add_or_merge(
        self,
        user_id: UUID,
        card_id: UUID,
        quantity: int,
        condition: Condition,
        finish: Finish,
        now: datetime,
    ) -> tuple[VaultEntry, bool]:
        """Create the entry or add to the existing one; the flag says whether it was created.

        Raises ``ValidationFailed`` when the merged quantity would exceed the cap.
        """
        ...

    def get_item(self, user_id: UUID, entry_id: UUID) -> VaultItem | None: ...

    def list_items(self, user_id: UUID, query: VaultQuery) -> tuple[list[VaultItem], int]:
        """One page of the user's entries with their cards, and the total count."""
        ...

    def update(
        self,
        user_id: UUID,
        entry_id: UUID,
        quantity: int | None,
        condition: Condition | None,
        finish: Finish | None,
        now: datetime,
    ) -> tuple[VaultEntry, bool] | None:
        """Change an entry; on a collision merge into the other entry (flag True).

        Returns None when the entry does not exist for this user.
        """
        ...

    def delete(self, user_id: UUID, entry_id: UUID) -> bool: ...

    def count(self, user_id: UUID) -> int: ...
