from decimal import Decimal
from pathlib import Path

import pytest

from mtgvault.domain import vault as vault_module
from mtgvault.domain.card import Prices
from mtgvault.domain.errors import ValidationFailed
from mtgvault.domain.vault import (
    MAX_QUANTITY,
    Currency,
    Finish,
    line_value,
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


@pytest.mark.parametrize(
    ("finish", "usd", "eur"),
    [
        (Finish.NONFOIL, Decimal("1.10"), Decimal("1.00")),
        (Finish.FOIL, Decimal("2.20"), Decimal("2.00")),
        (Finish.ETCHED, None, Decimal("3.00")),
    ],
)
def test_the_unit_price_exists_per_finish_and_currency(
    finish: Finish, usd: Decimal | None, eur: Decimal | None
) -> None:
    prices = Prices(
        usd=Decimal("1.10"),
        usd_foil=Decimal("2.20"),
        eur=Decimal("1.00"),
        eur_foil=Decimal("2.00"),
        eur_etched=Decimal("3.00"),
    )
    assert unit_price(prices, finish) == usd
    assert unit_price(prices, finish, Currency.EUR) == eur


@pytest.mark.parametrize(
    ("price", "quantity", "expected"),
    [
        (Decimal("0.35"), 3, Decimal("1.05")),
        (Decimal("1234.56"), 9999, Decimal("12344365.44")),
        (Decimal("0.005"), 1, Decimal("0.01")),  # half up, once, at the end
        (Decimal("0.00"), 5, Decimal("0.00")),  # a real price of zero is still a price
        (None, 5, None),  # no price is not zero
    ],
)
def test_line_value_is_exact_and_unpriced_stays_unpriced(
    price: Decimal | None, quantity: int, expected: Decimal | None
) -> None:
    assert line_value(price, quantity) == expected


def test_the_pricing_rules_never_use_floats() -> None:
    source = Path(vault_module.__file__).read_text(encoding="utf-8")
    assert "float(" not in source
