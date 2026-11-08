"""The vault over HTTP on real PostgreSQL: US-005..US-011 and the vault part of US-025."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.adapters.cache import TtlCache
from mtgvault.config import Settings
from mtgvault.domain.card import Prices
from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal
from mtgvault.main import create_app

pytestmark = pytest.mark.integration
GOOD = {"alice": "alice-token", "bob": "bob-token"}  # stand-ins, not credentials
BOLT = make_card(
    "Lightning Bolt", "lea", "161", prices=Prices(usd=Decimal("1.50"), usd_foil=Decimal("3.00"))
)
FOIL_ONLY = make_card(
    "Foil Dragon", "m10", "9", finishes=("foil",), prices=Prices(usd_foil=Decimal("7.00"))
)
LOTUS = make_card("Black Lotus", "lea", "232", rarity="rare", type_line="Artifact", colors=(),
                  prices=Prices(usd=Decimal("9000.00")))  # fmt: skip
CARDS = [BOLT, FOIL_ONLY, LOTUS]


class Verifier:
    def verify(self, token: str) -> Principal:
        for sub, value in GOOD.items():
            if token == value:
                return Principal(sub, sub.title())
        raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)


def headers(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {GOOD[who]}"}


@pytest.fixture
def provider() -> FakeCardProvider:
    return FakeCardProvider(list(CARDS))


@pytest.fixture
def client(migrated: Engine, database_url: str, provider: FakeCardProvider) -> TestClient:
    settings = Settings(
        database_url=database_url,
        oidc_issuer_url="https://idp.example.test",
        oidc_audience="mtgvault-api",
        scryfall_user_agent="MTGCardVault-tests/0.3 (+https://example.org)",
    )  # type: ignore[call-arg]
    app = create_app(
        settings, token_verifier=Verifier(), card_provider=provider, cache=TtlCache(300, 100)
    )
    return TestClient(app)


def add(client: TestClient, who: str, card: UUID, quantity: int = 1, finish: str = "nonfoil", condition: str = "NM"):  # type: ignore[no-untyped-def]  # fmt: skip
    return client.post(
        "/api/v1/vault/entries",
        json={"card_id": str(card), "quantity": quantity, "condition": condition, "finish": finish},
        headers=headers(who),
    )


def entries(client: TestClient, who: str, **params: object) -> dict[str, object]:
    response = client.get("/api/v1/vault/entries", params=params, headers=headers(who))  # type: ignore[arg-type]
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------- US-005 / US-010
def test_adding_a_printing_creates_an_entry_and_caches_the_card(
    client: TestClient, migrated: Engine
) -> None:
    response = add(client, "alice", BOLT.id, 2, "foil")
    assert response.status_code == 201
    body = response.json()
    assert (body["quantity"], body["condition"], body["finish"]) == (2, "NM", "foil")
    assert body["card"]["name"] == "Lightning Bolt"
    assert body["unit_price"] == "3.00"  # the foil price
    assert body["line_value_usd"] == "6.00"  # x 2
    assert body["unit_price_eur"] is None and body["line_value_eur"] is None  # no price, not zero
    assert body["available_finishes"] == ["nonfoil", "foil"]
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM cards")).scalar_one() == 1


def test_adding_the_same_combination_again_merges_and_a_new_condition_does_not(
    client: TestClient,
) -> None:
    first = add(client, "alice", BOLT.id, 2).json()
    again = add(client, "alice", BOLT.id, 1)
    assert again.status_code == 200
    assert (again.json()["id"], again.json()["quantity"]) == (first["id"], 3)
    other = add(client, "alice", BOLT.id, 1, condition="LP")
    assert other.status_code == 201
    assert other.json()["id"] != first["id"]
    assert entries(client, "alice")["total"] == 2


def test_an_unavailable_finish_is_rejected_naming_the_allowed_ones(client: TestClient) -> None:
    response = add(client, "alice", FOIL_ONLY.id, 1, "nonfoil")
    assert response.status_code == 422
    error = response.json()["errors"][0]
    assert error["field"] == "finish"
    assert "foil" in error["message"]
    assert entries(client, "alice")["total"] == 0  # nothing saved


@pytest.mark.parametrize("quantity", [0, -3, 10000])
def test_invalid_quantities_are_rejected(client: TestClient, quantity: int) -> None:
    response = add(client, "alice", BOLT.id, quantity)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "quantity"


def test_the_cap_is_enforced_when_merging(client: TestClient) -> None:
    add(client, "alice", BOLT.id, 9999)
    response = add(client, "alice", BOLT.id, 1)
    assert response.status_code == 422
    assert entries(client, "alice")["items"][0]["quantity"] == 9999  # type: ignore[index]


def test_unknown_cards_and_bad_bodies(client: TestClient) -> None:
    assert add(client, "alice", uuid4()).status_code == 404
    bad = client.post(
        "/api/v1/vault/entries",
        json={"card_id": "x", "quantity": 1, "finish": "foil"},
        headers=headers("alice"),
    )
    assert bad.status_code == 422
    missing = client.post(
        "/api/v1/vault/entries",
        json={"card_id": str(BOLT.id), "quantity": 1},
        headers=headers("alice"),
    )
    assert missing.status_code == 422


# ---------------------------------------------------------------------------- US-006 / US-009
def seed_many(migrated: Engine, user: UUID, how_many: int) -> None:
    """A big vault without 250 HTTP calls: one card, many conditions/finishes is capped, so use many cards."""
    from datetime import UTC, datetime

    from sqlalchemy.orm import sessionmaker

    from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
    from mtgvault.domain.vault import Condition, Finish

    now = datetime(2026, 11, 8, tzinfo=UTC)
    with SqlAlchemyUnitOfWork(sessionmaker(migrated, expire_on_commit=False)) as unit:
        for index in range(how_many):
            card = make_card(f"Card {index:04d}", "tst", str(index))
            unit.cards.upsert_snapshot(card, now)
            unit.vault.add_or_merge(
                user, card.id, 1, Condition.NM, Finish.NONFOIL, now + timedelta(seconds=index)
            )
        unit.commit()


def user_id(client: TestClient, who: str) -> UUID:
    return UUID(client.get("/api/v1/me", headers=headers(who)).json()["id"])


def test_a_vault_of_250_entries_is_paged(client: TestClient, migrated: Engine) -> None:
    seed_many(migrated, user_id(client, "alice"), 250)
    page = entries(client, "alice", page_size=50)
    assert (page["total"], len(page["items"]), page["page_size"]) == (250, 50, 50)  # type: ignore[arg-type]
    assert page["items"][0]["card"]["name"] == "Card 0249"  # type: ignore[index]  # newest first
    last = entries(client, "alice", page=5, page_size=50)
    assert len(last["items"]) == 50  # type: ignore[arg-type]
    assert entries(client, "alice", page=6, page_size=50)["items"] == []


def test_an_empty_vault_is_an_empty_list(client: TestClient) -> None:
    page = entries(client, "alice")
    assert (page["items"], page["total"]) == ([], 0)


def test_filters_and_sorting_over_http(client: TestClient) -> None:
    add(client, "alice", BOLT.id, 4)
    add(client, "alice", LOTUS.id, 1)
    add(client, "alice", FOIL_ONLY.id, 2, "foil")
    names = lambda **p: [i["card"]["name"] for i in entries(client, "alice", **p)["items"]]  # type: ignore[index]  # noqa: E731
    assert names(q="BOLT") == ["Lightning Bolt"]
    assert names(set="lea", sort="name", dir="asc") == ["Black Lotus", "Lightning Bolt"]
    assert names(rarity="rare") == ["Black Lotus"]
    assert names(sort="price")[0] == "Black Lotus"
    assert names(sort="quantity")[0] == "Lightning Bolt"
    assert names(type="artifact") == ["Black Lotus"]


@pytest.mark.parametrize(
    "params", [{"sort": "nope"}, {"dir": "up"}, {"page_size": 500}, {"set": "a b"}, {"colors": "z"}]
)
def test_bad_list_parameters_are_422_problems(
    client: TestClient, params: dict[str, object]
) -> None:
    response = client.get("/api/v1/vault/entries", params=params, headers=headers("alice"))  # type: ignore[arg-type]
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


# ---------------------------------------------------------------------------- US-007
def test_editing_quantity_changes_the_timestamp(client: TestClient) -> None:
    created = add(client, "alice", BOLT.id, 1).json()
    response = client.patch(
        f"/api/v1/vault/entries/{created['id']}", json={"quantity": 3}, headers=headers("alice")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["quantity"] == 3
    assert body["updated_at"] >= created["updated_at"]


def test_editing_into_an_existing_combination_merges(client: TestClient) -> None:
    nm = add(client, "alice", BOLT.id, 2, condition="NM").json()
    lp = add(client, "alice", BOLT.id, 3, condition="LP").json()
    response = client.patch(
        f"/api/v1/vault/entries/{lp['id']}", json={"condition": "NM"}, headers=headers("alice")
    )
    assert response.status_code == 200
    assert (response.json()["id"], response.json()["quantity"]) == (nm["id"], 5)
    assert entries(client, "alice")["total"] == 1


def test_edit_validation(client: TestClient) -> None:
    created = add(client, "alice", FOIL_ONLY.id, 1, "foil").json()
    url = f"/api/v1/vault/entries/{created['id']}"
    assert (
        client.patch(url, json={"finish": "nonfoil"}, headers=headers("alice")).status_code == 422
    )
    assert client.patch(url, json={"quantity": 0}, headers=headers("alice")).status_code == 422
    assert client.patch(url, json={}, headers=headers("alice")).status_code == 422
    assert (
        client.patch(
            f"/api/v1/vault/entries/{uuid4()}", json={"quantity": 2}, headers=headers("alice")
        ).status_code
        == 404
    )


# ---------------------------------------------------------------------------- US-008
def test_removing_an_entry_then_again(client: TestClient) -> None:
    created = add(client, "alice", BOLT.id).json()
    url = f"/api/v1/vault/entries/{created['id']}"
    assert client.delete(url, headers=headers("alice")).status_code == 204
    assert client.delete(url, headers=headers("alice")).status_code == 404
    assert entries(client, "alice")["total"] == 0


# ---------------------------------------------------------------------------- US-011 isolation suite
ISOLATION_COVERAGE = {
    ("POST", "/api/v1/vault/entries"),
    ("GET", "/api/v1/vault/entries"),
    ("PATCH", "/api/v1/vault/entries/{entry_id}"),
    ("DELETE", "/api/v1/vault/entries/{entry_id}"),
    (
        "GET",
        "/api/v1/vault/summary",
    ),  # test_the_summary_endpoint_totals_the_callers_collection_only
}


def test_every_vault_route_is_covered_by_the_isolation_suite(client: TestClient) -> None:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    routes = {
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/v1/vault")
        for method in operations
    }
    assert routes == ISOLATION_COVERAGE, "a vault route was added without isolation tests"


def test_user_b_cannot_see_change_or_remove_user_as_entries(client: TestClient) -> None:
    entry = add(client, "alice", BOLT.id, 5).json()
    url = f"/api/v1/vault/entries/{entry['id']}"
    assert entries(client, "bob")["items"] == []
    assert client.patch(url, json={"quantity": 1}, headers=headers("bob")).status_code == 404
    assert client.delete(url, headers=headers("bob")).status_code == 404
    still = entries(client, "alice")
    assert still["total"] == 1
    assert still["items"][0]["quantity"] == 5  # type: ignore[index]


def test_the_same_printing_is_a_separate_entry_per_user(client: TestClient) -> None:
    a = add(client, "alice", BOLT.id, 1).json()
    b = add(client, "bob", BOLT.id, 7)
    assert b.status_code == 201
    assert b.json()["id"] != a["id"]
    assert entries(client, "alice")["items"][0]["quantity"] == 1  # type: ignore[index]


@pytest.mark.parametrize("field", ["user_id", "userId", "owner"])
def test_a_user_named_in_the_request_is_rejected_not_obeyed(client: TestClient, field: str) -> None:
    bob = user_id(client, "bob")
    body = {"card_id": str(BOLT.id), "quantity": 1, "finish": "nonfoil", field: str(bob)}
    response = client.post("/api/v1/vault/entries", json=body, headers=headers("alice"))
    assert response.status_code == 422
    assert entries(client, "bob")["total"] == 0
    created = add(client, "alice", BOLT.id).json()
    edit = client.patch(
        f"/api/v1/vault/entries/{created['id']}",
        json={"quantity": 2, field: str(bob)},
        headers=headers("alice"),
    )
    assert edit.status_code == 422


def test_a_query_parameter_cannot_select_another_user(client: TestClient) -> None:
    add(client, "alice", BOLT.id)
    bob = user_id(client, "bob")
    page = entries(client, "bob", user_id=str(bob), owner="alice")
    assert page["items"] == []


def test_every_vault_endpoint_needs_a_token(client: TestClient) -> None:
    some = uuid4()
    for method, url, body in (
        ("get", "/api/v1/vault/entries", None),
        ("post", "/api/v1/vault/entries", {"card_id": str(some), "quantity": 1, "finish": "foil"}),
        ("patch", f"/api/v1/vault/entries/{some}", {"quantity": 1}),
        ("delete", f"/api/v1/vault/entries/{some}", None),
    ):
        response = getattr(client, method)(url, **({"json": body} if body else {}))
        assert response.status_code == 401, (method, url)


# ---------------------------------------------------------------------------- US-025 (vault part)
def test_the_vault_stays_readable_and_editable_while_the_source_is_down(
    client: TestClient, provider: FakeCardProvider
) -> None:
    created = add(client, "alice", BOLT.id, 2).json()
    provider.fail = True
    page = entries(client, "alice")
    assert page["items"][0]["card"]["name"] == "Lightning Bolt"  # type: ignore[index]
    url = f"/api/v1/vault/entries/{created['id']}"
    assert client.patch(url, json={"quantity": 4}, headers=headers("alice")).status_code == 200
    assert client.get("/api/v1/me", headers=headers("alice")).status_code == 200
    assert client.delete(url, headers=headers("alice")).status_code == 204


def test_adding_a_cached_printing_works_during_an_outage_and_an_uncached_one_is_a_503(
    client: TestClient, provider: FakeCardProvider
) -> None:
    add(client, "alice", BOLT.id)
    provider.fail = True
    # the printing is known (catalogue cache or stored snapshot); a new one cannot be fetched
    assert add(client, "alice", BOLT.id, 1).status_code in (200, 201)
    assert add(client, "alice", LOTUS.id).status_code == 503


def test_stale_prices_are_flagged(client: TestClient, migrated: Engine) -> None:
    add(client, "alice", BOLT.id)
    assert entries(client, "alice")["items"][0]["prices_stale"] is False  # type: ignore[index]
    old = datetime.now(UTC) - timedelta(hours=30)
    with migrated.begin() as connection:
        connection.execute(text("UPDATE cards SET prices_updated_at = :t"), {"t": old})
    assert entries(client, "alice")["items"][0]["prices_stale"] is True  # type: ignore[index]
    with migrated.begin() as connection:
        connection.execute(text("UPDATE cards SET prices_updated_at = NULL"))
    assert entries(client, "alice")["items"][0]["prices_stale"] is True  # type: ignore[index]


# ---------------------------------------------------------------------------- summary (#133)
def test_the_summary_endpoint_totals_the_callers_collection_only(client: TestClient) -> None:
    add(client, "alice", BOLT.id, 2, "foil")  # 6.00
    add(client, "alice", LOTUS.id, 1)  # 9000.00
    add(client, "bob", BOLT.id, 100)
    body = client.get("/api/v1/vault/summary", headers=headers("alice")).json()
    assert body["total_cards"] == 3 and body["entries"] == 2
    assert body["value_usd"] == "9006.00"
    assert body["value_eur"] == "0.00" and body["unpriced_eur"] == 2 and body["lower_bound_eur"]
    assert body["unpriced_usd"] == 0 and body["lower_bound_usd"] is False


def test_the_summary_needs_a_token_and_an_empty_vault_is_zeros(client: TestClient) -> None:
    assert client.get("/api/v1/vault/summary").status_code == 401
    body = client.get("/api/v1/vault/summary", headers=headers("bob")).json()
    assert (body["total_cards"], body["entries"], body["value_usd"]) == (0, 0, "0.00")
