"""Ports: interfaces the application layer needs, implemented by adapters (ADR-006)."""

from types import TracebackType
from typing import Protocol, Self

from mtgvault.domain.identity import Principal


class TokenVerifier(Protocol):
    """Turns a bearer token into the caller's identity (ADR-003, FR-AUTH-05).

    Raises ``Unauthenticated`` for any token that is not acceptable (the reason is only logged)
    and ``UpstreamUnavailable`` when the identity provider's keys cannot be obtained at all.
    """

    def verify(self, token: str) -> Principal: ...


class ReadinessProbe(Protocol):
    """Reports whether the service's dependencies (the database) are reachable."""

    def is_ready(self) -> bool: ...


class UnitOfWork(Protocol):
    """One transaction around a use case. Leaving the block without ``commit`` rolls back."""

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
