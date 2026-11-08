"""Ports: interfaces the application layer needs, implemented by adapters (ADR-006)."""

from datetime import datetime, timedelta
from types import TracebackType
from typing import Protocol, Self

from mtgvault.domain.identity import Principal
from mtgvault.domain.user import User


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

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
