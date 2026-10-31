"""Ports: interfaces the application layer needs, implemented by adapters (ADR-006)."""

from typing import Protocol

from mtgvault.domain.greeting import Greeting


class GreetingProvider(Protocol):
    """Supplies the greeting. Skeleton port (issue #1)."""

    def current(self) -> Greeting: ...


class ReadinessProbe(Protocol):
    """Reports whether the service's dependencies (the database) are reachable."""

    def is_ready(self) -> bool: ...
