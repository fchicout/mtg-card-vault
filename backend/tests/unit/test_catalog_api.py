"""The catalogue endpoints (US-012..US-014, US-025) with a fake provider and a stub verifier."""

from uuid import uuid4

from fastapi.testclient import TestClient
from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.adapters.cache import TtlCache
from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal
from mtgvault.main import create_app

GOOD = "good"  # a stand-in value, not a credential
AUTH = {"Authorization": f"Bearer {GOOD}"}


class Verifier:
    def verify(self, token: str) -> Principal:
        if token != GOOD:
            raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)
        return Principal("u1")


class Probe:
    def is_ready(self) -> bool:
        return True


BOLT = make_card("Lightning Bolt", "lea", "161")
BOLT_2 = make_card("Lightning Bolt", "m10", "146")
LOTUS = make_card("Black Lotus", "lea", "232", rarity="rare", type_line="Artifact")
DRAGON = make_card("Shivan Dragon", "lea", "175", rarity="rare", type_line="Creature - Dragon")
SPLIT = make_card(
    "Fire // Ice", "mh2", "290", layout="split", type_line="Instant // Instant", faces=()
)


def build(cards=None, **kwargs):  # type: ignore[no-untyped-def]
    provider = FakeCardProvider(
        cards if cards is not None else [BOLT, BOLT_2, LOTUS, DRAGON, SPLIT]
    )
    app = create_app(
        readiness_probe=Probe(),
        token_verifier=Verifier(),
        card_provider=provider,
        cache=TtlCache(300, 100),
        **kwargs,
    )
    return TestClient(app), provider


def test_everything_requires_a_token() -> None:
    client, _ = build()
    for path in (
        "/api/v1/catalog/cards?q=bolt",
        f"/api/v1/catalog/cards/{BOLT.id}",
        f"/api/v1/catalog/cards/{BOLT.id}/printings",
    ):
        assert client.get(path).status_code == 401


def test_search_by_partial_name_lists_unique_cards() -> None:
    client, _ = build()
    body = client.get("/api/v1/catalog/cards", params={"q": "lightning"}, headers=AUTH).json()
    assert [c["name"] for c in body["items"]] == ["Lightning Bolt"]
    first = body["items"][0]
    assert set(first) == {
        "id", "name", "type_line", "set_code", "set_name", "collector_number", "rarity",
        "image_small",
    }  # fmt: skip
    assert body["page"] == 1
    assert body["has_more"] is False


def test_no_results_is_an_empty_list_not_an_error() -> None:
    client, _ = build()
    response = client.get("/api/v1/catalog/cards", params={"q": "zzzz"}, headers=AUTH)
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_the_provider_only_ever_sees_a_translated_query() -> None:
    client, provider = build()
    client.get(
        "/api/v1/catalog/cards",
        params={"q": "dragon", "colors": "r", "rarity": "rare", "set": "LEA", "type": "Creature"},
        headers=AUTH,
    )
    assert provider.search_calls == [('name:"dragon" set:lea t:"Creature" r:rare c:r', 1)]


def test_injection_attempts_are_neutralised_or_rejected() -> None:
    client, provider = build()
    ok = client.get("/api/v1/catalog/cards", params={"q": 'bolt" or o:"x'}, headers=AUTH)
    assert ok.status_code == 200
    assert provider.search_calls[-1][0] == 'name:"bolt" name:"or" name:"o:" name:"x"'
    for params in (
        {"q": "bolt", "set": "lea or t:land"},
        {"q": "bolt", "type": 'x" or o:"y'},
        {"q": "bolt", "colors": "rx"},
    ):
        bad = client.get("/api/v1/catalog/cards", params=params, headers=AUTH)
        assert bad.status_code == 422
        assert bad.headers["content-type"].startswith("application/problem+json")
    assert len(provider.search_calls) == 1


def test_validation_problems_name_the_field() -> None:
    client, provider = build()
    for params, field in (
        ({"q": "x" * 101}, "q"),
        ({}, "q"),
        ({"q": "a", "rarity": "special"}, "rarity"),
        ({"q": "a", "page": 0}, "page"),
    ):
        response = client.get("/api/v1/catalog/cards", params=params, headers=AUTH)
        assert response.status_code == 422
        assert field in {e["field"] for e in response.json()["errors"]}
    assert provider.search_calls == []


def test_a_repeated_search_is_served_from_the_cache() -> None:
    client, provider = build()
    for _ in range(3):
        client.get("/api/v1/catalog/cards", params={"q": "bolt"}, headers=AUTH)
    assert len(provider.search_calls) == 1
    client.get("/api/v1/catalog/cards", params={"q": "bolt", "page": 2}, headers=AUTH)
    assert len(provider.search_calls) == 2


def test_card_detail() -> None:
    client, _ = build()
    body = client.get(f"/api/v1/catalog/cards/{LOTUS.id}", headers=AUTH).json()
    assert body["name"] == "Black Lotus"
    assert body["prices"]["usd"] == "1.50"
    assert body["prices"]["eur"] is None
    assert body["finishes"] == ["nonfoil", "foil"]
    assert body["faces"] == []


def test_unknown_card_is_a_404_problem_and_bad_ids_are_422() -> None:
    client, _ = build()
    missing = client.get(f"/api/v1/catalog/cards/{uuid4()}", headers=AUTH)
    assert missing.status_code == 404
    assert missing.json()["type"] == "urn:mtgvault:problem:not-found"
    assert client.get("/api/v1/catalog/cards/not-a-uuid", headers=AUTH).status_code == 422


def test_printings_of_a_card_with_many_printings_are_paged() -> None:
    cards = [make_card("Lightning Bolt", f"s{n:02d}", str(n)) for n in range(1, 8)]
    client, _ = build(cards)
    first = client.get(f"/api/v1/catalog/cards/{cards[0].id}/printings", headers=AUTH).json()
    assert len(first["items"]) == 3
    assert first["has_more"] is True
    assert first["total"] == 7
    last = client.get(
        f"/api/v1/catalog/cards/{cards[0].id}/printings", params={"page": 3}, headers=AUTH
    ).json()
    assert len(last["items"]) == 1
    assert last["has_more"] is False
    item = first["items"][0]
    assert set(item) == {
        "id",
        "set_code",
        "set_name",
        "collector_number",
        "lang",
        "rarity",
        "finishes",
        "image_small",
        "prices",
    }


def test_an_outage_is_a_typed_503_with_no_internals() -> None:
    client, provider = build()
    provider.fail = True
    response = client.get("/api/v1/catalog/cards", params={"q": "bolt"}, headers=AUTH)
    assert response.status_code == 503
    body = response.json()
    assert body["type"] == "urn:mtgvault:problem:upstream-unavailable"
    assert "Traceback" not in response.text
    assert body["correlation_id"]


def test_without_a_card_source_the_catalogue_answers_503() -> None:
    app = create_app(readiness_probe=Probe(), token_verifier=Verifier())
    response = TestClient(app).get("/api/v1/catalog/cards", params={"q": "bolt"}, headers=AUTH)
    assert response.status_code == 503
