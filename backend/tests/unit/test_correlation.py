import pytest

from mtgvault.correlation import (
    accept_or_generate,
    current_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)


@pytest.mark.parametrize("value", ["abc", "A-b_c.9", "x" * 128])
def test_safe_ids_are_kept(value: str) -> None:
    assert accept_or_generate(value) == value


@pytest.mark.parametrize("value", [None, "", "a b", "new\nline", "x" * 129, "<b>"])
def test_unsafe_or_missing_ids_are_replaced(value: str | None) -> None:
    generated = accept_or_generate(value)
    assert generated != value
    assert len(generated) == 32


def test_the_current_id_is_scoped() -> None:
    assert current_correlation_id() is None
    token = set_correlation_id("req-1")
    assert current_correlation_id() == "req-1"
    reset_correlation_id(token)
    assert current_correlation_id() is None
