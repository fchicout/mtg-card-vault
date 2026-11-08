from decimal import Decimal

import pytest

from mtgvault.domain.card import Prices
from mtgvault.domain.errors import ValidationFailed
from mtgvault.domain.vault import (
    MAX_QUANTITY,
    Finish,
    merged_quantity,
    unit_price,
    validate_finish,
    validate_quantity,
)


@pytest.mark.parametrize("quantity", [1, 2, 9999])
def test_valid_quantities_pass(quantity: int) -> None:
    assert validate_quantity(quantity) == quantity


@pytest.mark.parametrize("quantity", [0, -1, 10000])
def test_invalid_quantities_name_the_field(quantity: int) -> None:
    with pytest.raises(ValidationFailed) as refused:
        validate_quantity(quantity)
    assert refused.value.errors[0].field == "quantity"


def test_a_finish_must_exist_on_the_printing_and_the_error_lists_the_allowed_ones() -> None:
    assert validate_finish(Finish.FOIL, ("nonfoil", "foil")) is Finish.FOIL
    with pytest.raises(ValidationFailed) as refused:
        validate_finish(Finish.ETCHED, ("nonfoil", "foil"))
    assert refused.value.errors[0].field == "finish"
    assert "nonfoil, foil" in refused.value.errors[0].message


def test_merging_adds_up_to_the_cap_and_never_clamps() -> None:
    assert merged_quantity(2, 1) == 3
    assert merged_quantity(MAX_QUANTITY - 1, 1) == MAX_QUANTITY
    with pytest.raises(ValidationFailed):
        merged_quantity(MAX_QUANTITY, 1)


def test_the_unit_price_follows_the_finish_and_unknown_is_none() -> None:
    prices = Prices(usd=Decimal("1"), usd_foil=Decimal("2"), usd_etched=None)
    assert unit_price(prices, Finish.NONFOIL) == Decimal("1")
    assert unit_price(prices, Finish.FOIL) == Decimal("2")
    assert unit_price(prices, Finish.ETCHED) is None
