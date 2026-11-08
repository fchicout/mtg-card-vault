"""The search query is built from checked pieces only (FR-CAT-01, FR-CAT-02)."""

import pytest

from mtgvault.application.catalog_query import CatalogFilters, build_query, parse_colors
from mtgvault.domain.errors import ValidationFailed

NO_FILTERS = CatalogFilters()


def fields(error: ValidationFailed) -> set[str]:
    return {e.field for e in error.errors}


def test_words_become_separate_quoted_name_terms() -> None:
    assert build_query("black lotus", NO_FILTERS) == 'name:"black" name:"lotus"'


def test_filters_each_get_their_own_operator() -> None:
    filters = CatalogFilters("lea", ("R", "G"), "Creature - Dragon", "rare")
    assert (
        build_query("dragon", filters) == 'name:"dragon" set:lea t:"Creature - Dragon" r:rare c:rg'
    )


def test_filters_alone_are_enough() -> None:
    assert build_query(None, CatalogFilters(rarity="mythic")) == "r:mythic"
    assert build_query("", CatalogFilters(colors=("C",))) == "c:c"


@pytest.mark.parametrize(
    "attack",
    [
        'bolt" or o:"draw',
        "bolt or a:1",
        "-bolt",
        "(bolt)",
        "bolt) or (t:land",
        "oracle:destroy",
        'bolt\\" or name:"x',
        "bolt \x00 order:cmc",
    ],
)
def test_user_text_can_never_add_operators(attack: str) -> None:
    query = build_query(attack, NO_FILTERS)
    # every term is a quoted name term: no quote or backslash from the user survives
    assert all(t.startswith('name:"') and t.endswith('"') for t in query.split(" "))
    assert query.count('"') == 2 * len(query.split(" "))
    assert "\\" not in query


@pytest.mark.parametrize(
    ("filters", "field"),
    [
        (CatalogFilters(set_code="lea or t:land"), "set"),
        (CatalogFilters(set_code="x"), "set"),
        (CatalogFilters(type_text='Dragon" or o:"x'), "type"),
        (CatalogFilters(type_text="a" * 41), "type"),
        (CatalogFilters(type_text="-Dragon"), "type"),
        (CatalogFilters(rarity="special"), "rarity"),
        (CatalogFilters(colors=("X",)), "colors"),
    ],
)
def test_filter_values_are_checked_not_escaped(filters: CatalogFilters, field: str) -> None:
    with pytest.raises(ValidationFailed) as rejected:
        build_query("bolt", filters)
    assert field in fields(rejected.value)


def test_text_limits_and_emptiness() -> None:
    with pytest.raises(ValidationFailed) as rejected:
        build_query("x" * 101, NO_FILTERS)
    assert fields(rejected.value) == {"q"}
    nine_words = " ".join(["a"] * 9)
    with pytest.raises(ValidationFailed):
        build_query(nine_words, NO_FILTERS)
    for nothing in (None, "", "   ", '"""'):
        with pytest.raises(ValidationFailed):
            build_query(nothing, NO_FILTERS)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, ()),
        ("", ()),
        ("r", ("R",)),
        ("R,G", ("R", "G")),
        ("rg", ("R", "G")),
        ("wwu", ("W", "U")),
        ("c", ("C",)),
    ],
)
def test_colors_parse(raw: str | None, expected: tuple[str, ...]) -> None:
    assert parse_colors(raw) == expected


@pytest.mark.parametrize("raw", ["x", "rx", "cr", "red"])
def test_bad_colors_are_rejected(raw: str) -> None:
    with pytest.raises(ValidationFailed):
        parse_colors(raw)
