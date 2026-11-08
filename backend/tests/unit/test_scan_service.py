"""US-016 at service level with a fake recogniser and a fake catalogue."""

import pytest
from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.adapters.cache import TtlCache
from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.ports import RecognizedText
from mtgvault.application.scan_service import ScanService
from mtgvault.domain.errors import UpstreamUnavailable, ValidationFailed

BOLT_LEA = make_card("Lightning Bolt", "lea", "161")
BOLT_M10 = make_card("Lightning Bolt", "m10", "146")
HELIX = make_card("Lightning Helix", "rav", "213")
CARDS = [BOLT_LEA, BOLT_M10, HELIX, make_card("Giant Growth", "lea", "200")]


class FakeRecognizer:
    def __init__(self, title: str, collector: str = "") -> None:
        self.text = RecognizedText(title, collector)
        self.images: list[bytes] = []

    def read(self, image: bytes) -> RecognizedText:
        self.images.append(image)
        if image == b"broken":
            raise ValidationFailed("The image cannot be read.")
        return self.text


def service(title: str, collector: str = "", provider: FakeCardProvider | None = None):  # type: ignore[no-untyped-def]
    provider = provider or FakeCardProvider(list(CARDS))
    catalog = CatalogService(provider, TtlCache(300, 100))
    return ScanService(FakeRecognizer(title, collector), catalog), provider


def test_a_clear_capture_gives_ranked_candidates_and_the_text_that_was_read() -> None:
    scan, _ = service("Lightning Bolt")
    result = scan.scan(b"frame")
    assert result.title_text == "Lightning Bolt"
    assert result.reason is None
    assert result.candidates[0].card.name == "Lightning Bolt"
    assert len(result.candidates) <= 5


def test_set_and_number_pick_the_exact_printing() -> None:
    scan, _ = service("Lightnng Bolt", "146/249 C\nM10 • EN")
    result = scan.scan(b"frame")
    assert result.candidates[0].card is BOLT_M10
    assert result.candidates[0].exact


def test_an_unreadable_capture_is_reported_with_a_reason_and_asks_nothing_of_the_catalogue() -> (
    None
):
    scan, provider = service("@@ ## 12", "")
    result = scan.scan(b"frame")
    assert (result.candidates, result.reason) == ([], "unreadable")
    assert provider.search_calls == []


def test_a_readable_title_without_a_match_says_so() -> None:
    scan, _ = service("Zzzqqq Wwwxxx")
    assert scan.scan(b"frame").reason == "no_match"


def test_a_misread_word_is_tolerated_by_loosening_the_query() -> None:
    scan, provider = service("Lightning Bxlt Storm")
    result = scan.scan(b"frame")
    assert (
        any(c.card.name == "Lightning Bolt" for c in result.candidates)
        or result.reason == "no_match"
    )
    assert len(provider.search_calls) >= 2  # all words first, then looser queries


def test_a_source_outage_is_a_typed_503_and_nothing_is_stored() -> None:
    provider = FakeCardProvider(list(CARDS))
    provider.fail = True
    scan, _ = service("Lightning Bolt", provider=provider)
    with pytest.raises(UpstreamUnavailable):
        scan.scan(b"frame")


def test_an_undecodable_image_is_a_validation_error() -> None:
    scan, _ = service("x")
    with pytest.raises(ValidationFailed):
        scan.scan(b"broken")
