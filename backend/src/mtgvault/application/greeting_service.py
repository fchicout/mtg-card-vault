"""Skeleton use case (issue #1). Removed together with the /hello route (issue #15)."""

from mtgvault.application.ports import GreetingProvider
from mtgvault.domain.greeting import Greeting


class GreetingService:
    """Returns the greeting supplied by a :class:`GreetingProvider`."""

    def __init__(self, provider: GreetingProvider) -> None:
        self._provider = provider

    def greet(self) -> Greeting:
        return self._provider.current()
