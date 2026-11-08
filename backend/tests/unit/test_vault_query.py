import pytest

from mtgvault.application.vault_query import (
    DEFAULT_PAGE_SIZE,
    build_vault_query,
    normalise,
)
from mtgvault.domain.errors import ValidationFailed


def fields(error: ValidationFailed) -> set[str]:
    return {e.field for e in error.errors}


def test_defaults_are_newest_first_with_fifty_per_page() -> None:
    query = build_vault_query()
    assert (query.page, query.page_size, query.sort, query.descending) == (
        1,
        DEFAULT_PAGE_SIZE,
        "added",
        True,
    )


@pytest.mark.parametrize(
    ("sort", "direction", "descending"),
    [("name", None, False), ("set", None, False), ("price", None, True), ("quantity", None, True),
     ("name", "desc", True), ("added", "asc", False)],
)  # fmt: skip
def test_sort_directions_have_sensible_defaults(
    sort: str, direction: str | None, descending: bool
) -> None:
    assert build_vault_query(sort=sort, direction=direction).descending is descending


def test_text_is_normalised_for_searching() -> None:
    assert normalise("  Jötun   GRUNT ") == "jotun grunt"
    assert build_vault_query(q="  Bolt ").name == "bolt"
    assert build_vault_query(q="   ").name is None


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ({"sort": "price; drop table"}, "sort"),
        ({"sort": "id"}, "sort"),
        ({"direction": "sideways"}, "dir"),
        ({"page": 0}, "page"),
        ({"page_size": 201}, "page_size"),
        ({"page_size": 0}, "page_size"),
        ({"q": "x" * 101}, "q"),
        ({"set_code": "lea or t:land"}, "set"),
        ({"rarity": "special"}, "rarity"),
        ({"type_text": 'x" or'}, "type"),
        ({"colors": "rx"}, "colors"),
    ],
)
def test_bad_parameters_are_rejected_naming_the_field(raw: dict[str, object], field: str) -> None:
    with pytest.raises(ValidationFailed) as refused:
        build_vault_query(**raw)  # type: ignore[arg-type]
    assert field in fields(refused.value)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ValidationFailed) as refused:
        build_vault_query(page=0, sort="nope", rarity="x")
    assert fields(refused.value) == {"page", "sort", "rarity"}


def test_filters_are_normalised() -> None:
    query = build_vault_query(set_code="MH2", colors="rg", type_text=" Creature ", rarity="rare")
    assert (query.set_code, query.colors, query.type_text, query.rarity) == (
        "mh2",
        ("R", "G"),
        "creature",
        "rare",
    )
