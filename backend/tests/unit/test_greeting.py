import pytest

from mtgvault.adapters.in_memory_greeting import InMemoryGreetingProvider
from mtgvault.application.greeting_service import GreetingService
from mtgvault.domain.greeting import Greeting


class FakeProvider:
    def current(self) -> Greeting:
        return Greeting("from the fake")


def test_service_returns_what_the_port_supplies() -> None:
    assert GreetingService(FakeProvider()).greet() == Greeting("from the fake")


def test_in_memory_adapter_default_message() -> None:
    assert InMemoryGreetingProvider().current().message == "Hello, MTG Vault!"


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_greeting_is_rejected(blank: str) -> None:
    with pytest.raises(ValueError, match="blank"):
        Greeting(blank)
