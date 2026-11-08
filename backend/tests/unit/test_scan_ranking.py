import pytest
from tests.support.fake_cards import make_card

from mtgvault.application.scan_ranking import MAX_CANDIDATES, name_similarity, rank
from mtgvault.domain.scan import CollectorInfo

NONE = CollectorInfo()
BOLT_LEA = make_card("Lightning Bolt", "lea", "161")
BOLT_M10 = make_card("Lightning Bolt", "m10", "146")
HELIX = make_card("Lightning Helix", "rav", "213")
GROWTH = make_card("Giant Growth", "lea", "200")


def names(candidates):  # type: ignore[no-untyped-def]
    return [c.card.name for c in candidates]


def test_a_clean_title_ranks_the_card_first() -> None:
    ranked = rank("Lightning Bolt", NONE, [HELIX, GROWTH, BOLT_LEA])
    assert ranked[0].card is BOLT_LEA
    assert ranked[0].confidence > 0.55
    assert not ranked[0].exact


@pytest.mark.parametrize(
    "typo", ["Lightnlng Bolt", "Lightning Boit", "Lightning Bo1t", "lightning bolt"]
)
def test_ocr_typos_still_find_the_card(typo: str) -> None:
    assert names(rank(typo, NONE, [HELIX, GROWTH, BOLT_LEA]))[0] == "Lightning Bolt"


def test_set_and_number_make_the_exact_printing_first_even_with_a_poor_title() -> None:
    ranked = rank("Lightnng B", CollectorInfo("146", "249", "m10"), [BOLT_LEA, BOLT_M10, HELIX])
    assert ranked[0].card is BOLT_M10
    assert ranked[0].exact
    assert ranked[0].confidence >= 0.9


def test_the_collector_number_alone_adds_confidence_without_being_exact() -> None:
    ranked = rank("Lightning Bolt", CollectorInfo("161", None, None), [BOLT_M10, BOLT_LEA])
    assert ranked[0].card is BOLT_LEA
    assert not ranked[0].exact


def test_an_unreadable_title_with_only_set_and_number_resolves_the_printing() -> None:
    ranked = rank(None, CollectorInfo("161", None, "lea"), [BOLT_LEA, GROWTH])
    assert ranked[0].card is BOLT_LEA
    assert ranked[0].exact


def test_implausible_candidates_are_dropped_and_nothing_is_a_valid_answer() -> None:
    assert rank("Zzzzzz Qqqqq", NONE, [BOLT_LEA, GROWTH, HELIX]) == []
    assert rank(None, NONE, [BOLT_LEA]) == []


def test_at_most_five_best_first_without_duplicates() -> None:
    cards = [make_card(f"Lightning Bolt {n}", "lea", str(n)) for n in range(9)] + [
        BOLT_LEA,
        BOLT_LEA,
    ]
    ranked = rank("Lightning Bolt", NONE, cards)
    assert len(ranked) == MAX_CANDIDATES
    assert ranked[0].card is BOLT_LEA
    assert [c.confidence for c in ranked] == sorted((c.confidence for c in ranked), reverse=True)
    assert len({c.card.id for c in ranked}) == len(ranked)


def test_double_faced_cards_match_on_either_face() -> None:
    delver = make_card("Delver of Secrets // Insectile Aberration", "isd", "51")
    assert name_similarity("Delver of Secrets", delver.name) > 0.95
    assert name_similarity("Insectile Aberration", delver.name) > 0.95
    assert rank("Insectile Aberration", NONE, [delver])[0].card is delver


def test_accents_and_case_do_not_matter() -> None:
    aether = make_card("Æther Vial", "mm2", "1")
    assert name_similarity("aether vial", "Æther Vial") == pytest.approx(1.0, abs=0.12)
    assert rank("Aether Vial", NONE, [aether])[0].card is aether
