"""In-memory :class:`GreetingProvider` (skeleton, issue #1)."""

from mtgvault.domain.greeting import Greeting


class InMemoryGreetingProvider:
    def __init__(self, message: str = "Hello, MTG Vault!") -> None:
        self._greeting = Greeting(message)

    def current(self) -> Greeting:
        return self._greeting
