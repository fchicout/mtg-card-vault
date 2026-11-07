"""Ports: interfaces the application layer needs, implemented by adapters (ADR-006)."""

from types import TracebackType
from typing import Protocol, Self

from mtgvault.domain.greeting import Greeting


class GreetingProvider(Protocol):
    """Supplies the greeting. Skeleton port (issue #1)."""

    def current(self) -> Greeting: ...


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
