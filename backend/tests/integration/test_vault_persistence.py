"""Cards, vault entries and their repositories on real PostgreSQL (#92-#99)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from tests.support.fake_cards import make_card

from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.application.vault_query import VaultQuery, build_vault_query
from mtgvault.domain.card import Prices
from mtgvault.domain.errors import ValidationFailed
from mtgvault.domain.identity import Principal
from mtgvault.domain.vault import Condition, Finish

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def uow(engine: Engine) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(sessionmaker(engine, expire_on_commit=False))


def new_user(engine: Engine, sub: str) -> UUID:
    with uow(engine) as unit:
        user = unit.users.provision(Principal(sub, sub.title()), NOW, timedelta(hours=1))
        unit.commit()
    return user.id


def put_card(engine: Engine, **kwargs: object) -> UUID:
    card = make_card(**kwargs)  # type: ignore[arg-type]
    with uow(engine) as unit:
        unit.cards.upsert_snapshot(card, NOW)
        unit.commit()
    return card.id


def add(engine: Engine, user: UUID, card: UUID, qty: int = 1, cond: Condition = Condition.NM,
        finish: Finish = Finish.NONFOIL, now: datetime = NOW):  # type: ignore[no-untyped-def]  # fmt: skip
    with uow(engine) as unit:
        result = unit.vault.add_or_merge(user, card, qty, cond, finish, now)
        unit.commit()
    return result


def scalar(engine: Engine, sql: str) -> object:
    with engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()


# ---------------------------------------------------------------------------- cards (#92)
def test_snapshot_upsert_keeps_one_row_and_refreshes(migrated: Engine) -> None:
    first = make_card("Lightning Bolt", prices=Prices(usd=Decimal("1.50")))
    with uow(migrated) as unit:
        unit.cards.upsert_snapshot(first, NOW)
        unit.commit()
    later = NOW + timedelta(days=1)
    cheaper = make_card("Lightning Bolt", prices=Prices(usd=Decimal("0.99"), usd_foil=None))
    with uow(migrated) as unit:
        unit.cards.upsert_snapshot(cheaper, later)
        unit.commit()
        snapshot = unit.cards.get(first.id)
    assert scalar(migrated, "SELECT count(*) FROM cards") == 1
    assert snapshot is not None
    assert snapshot.card.prices.usd == Decimal("0.99")
    assert snapshot.card.prices.usd_foil is None  # unknown stays NULL, never zero
    assert snapshot.prices_updated_at == later
    assert snapshot.card.finishes == ("nonfoil", "foil")
    assert snapshot.card.colors == ("R",)


def test_parallel_snapshot_upserts_are_safe(migrated: Engine) -> None:
    card = make_card("Sol Ring")

    def put(_: int) -> None:
        with uow(migrated) as unit:
            unit.cards.upsert_snapshot(card, NOW)
            unit.commit()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(put, range(16)))
    assert scalar(migrated, "SELECT count(*) FROM cards") == 1


# ---------------------------------------------------------------------------- constraints (#93)
@pytest.mark.parametrize(
    ("quantity", "condition", "finish"),
    [(0, "NM", "foil"), (10000, "NM", "foil"), (1, "XX", "foil"), (1, "NM", "holo")],
)
def test_the_database_rejects_invalid_entries(
    migrated: Engine, quantity: int, condition: str, finish: str
) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    statement = text(
        "INSERT INTO vault_entries (id, user_id, card_id, quantity, condition, finish)"
        " VALUES (:id, :u, :c, :q, :co, :f)"
    )
    params = {"id": uuid4(), "u": user, "c": card, "q": quantity, "co": condition, "f": finish}
    with migrated.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(statement, params)


def test_identity_is_unique_and_a_missing_card_is_refused(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    insert = text(
        "INSERT INTO vault_entries (id, user_id, card_id, quantity, condition, finish)"
        " VALUES (:id, :u, :c, 1, 'NM', 'foil')"
    )
    first, second, third = (uuid4() for _ in range(3))
    with migrated.begin() as connection:
        connection.execute(insert, {"id": first, "u": user, "c": card})
    duplicate = {"id": second, "u": user, "c": card}
    with migrated.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert, duplicate)
    missing_card = {"id": third, "u": user, "c": uuid4()}
    with migrated.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert, missing_card)


def test_deleting_a_user_removes_their_entries_but_keeps_the_cards(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    add(migrated, user, card)
    with migrated.begin() as connection:
        connection.execute(text("DELETE FROM users WHERE id = :u"), {"u": user})
    assert scalar(migrated, "SELECT count(*) FROM vault_entries") == 0
    assert scalar(migrated, "SELECT count(*) FROM cards") == 1


# ---------------------------------------------------------------------------- add / merge (#94, #95)
def test_add_creates_then_merges_and_distinguishes_conditions(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    entry, created = add(migrated, user, card, 2)
    assert created
    assert entry.quantity == 2
    merged, created_again = add(migrated, user, card, 1)
    assert not created_again
    assert (merged.id, merged.quantity) == (entry.id, 3)
    other, created_other = add(migrated, user, card, 1, Condition.LP)
    assert created_other
    assert other.id != entry.id


def test_the_cap_is_a_validation_error_and_changes_nothing(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    add(migrated, user, card, 9990)
    with pytest.raises(ValidationFailed) as refused:
        add(migrated, user, card, 10)
    assert refused.value.errors[0].field == "quantity"
    assert scalar(migrated, "SELECT quantity FROM vault_entries") == 9990
    assert add(migrated, user, card, 9)[0].quantity == 9999


def test_parallel_adds_of_the_same_combination_sum_correctly(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: add(migrated, user, card, 1), range(20)))
    assert scalar(migrated, "SELECT count(*) FROM vault_entries") == 1
    assert scalar(migrated, "SELECT quantity FROM vault_entries") == 20


# ---------------------------------------------------------------------------- isolation (#94)
def test_a_user_never_reaches_another_users_entries(migrated: Engine) -> None:
    alice, bob = new_user(migrated, "alice"), new_user(migrated, "bob")
    card = put_card(migrated)
    entry, _ = add(migrated, alice, card, 3)
    with uow(migrated) as unit:
        assert unit.vault.get_item(bob, entry.id) is None
        assert unit.vault.list_items(bob, VaultQuery()) == ([], 0)
        assert unit.vault.count(bob) == 0
        assert unit.vault.update(bob, entry.id, 9, None, None, NOW) is None
        assert unit.vault.delete(bob, entry.id) is False
        unit.commit()
    assert scalar(migrated, "SELECT quantity FROM vault_entries") == 3
    # the same card under another user is a separate entry
    assert add(migrated, bob, card, 1)[1] is True


# ---------------------------------------------------------------------------- list (#96, #97)
def seed_collection(engine: Engine) -> UUID:
    user = new_user(engine, "collector")
    specs = [
        ("Lightning Bolt", "lea", "161", "common", "Instant", ("R",), Decimal("2.00")),
        ("Lightning Helix", "rav", "213", "uncommon", "Instant", ("R", "W"), Decimal("1.00")),
        ("Sol Ring", "mh2", "395", "mythic", "Artifact", (), Decimal("9.00")),
        ("Jötun Grunt", "ice", "1", "common", "Creature — Giant", ("W",), None),
        ("Shivan Dragon", "m10", "225", "rare", "Creature — Dragon", ("R",), Decimal("5.00")),
    ]
    for index, (name, set_code, number, rarity, type_line, colors, price) in enumerate(specs):
        card = put_card(
            engine, name=name, set_code=set_code, number=number, rarity=rarity,
            type_line=type_line, colors=colors, prices=Prices(usd=price),
        )  # fmt: skip
        add(engine, user, card, index + 1, now=NOW + timedelta(minutes=index))
    return user


def names(engine: Engine, user: UUID, **query: object) -> list[str]:
    with uow(engine) as unit:
        items, _ = unit.vault.list_items(user, build_vault_query(**query))  # type: ignore[arg-type]
    return [i.snapshot.card.name for i in items]


def test_listing_is_paged_newest_first_with_a_total(migrated: Engine) -> None:
    user = seed_collection(migrated)
    with uow(migrated) as unit:
        items, total = unit.vault.list_items(user, build_vault_query(page=1, page_size=2))
        second, _ = unit.vault.list_items(user, build_vault_query(page=2, page_size=2))
    assert total == 5
    assert [i.snapshot.card.name for i in items] == ["Shivan Dragon", "Jötun Grunt"]
    assert [i.snapshot.card.name for i in second] == ["Sol Ring", "Lightning Helix"]
    assert items[0].unit_price == Decimal("5.00")  # the price that matches the finish


def test_name_search_ignores_case_and_accents_and_wildcards(migrated: Engine) -> None:
    user = seed_collection(migrated)
    assert names(migrated, user, q="BOLT") == ["Lightning Bolt"]
    assert sorted(names(migrated, user, q="lightning")) == ["Lightning Bolt", "Lightning Helix"]
    assert names(migrated, user, q="jotun") == ["Jötun Grunt"]
    assert names(migrated, user, q="%") == []  # a wildcard is a literal, not "everything"


def test_filters_and_sorting(migrated: Engine) -> None:
    user = seed_collection(migrated)
    assert names(migrated, user, set_code="MH2") == ["Sol Ring"]
    assert sorted(names(migrated, user, colors="R")) == [
        "Lightning Bolt",
        "Lightning Helix",
        "Shivan Dragon",
    ]
    assert names(migrated, user, colors="RW") == ["Lightning Helix"]
    assert sorted(names(migrated, user, rarity="common")) == ["Jötun Grunt", "Lightning Bolt"]
    assert sorted(names(migrated, user, type_text="creature")) == ["Jötun Grunt", "Shivan Dragon"]
    assert names(migrated, user, sort="name", direction="asc")[0] == "Jötun Grunt"
    by_price = names(migrated, user, sort="price")
    assert by_price[:3] == ["Sol Ring", "Shivan Dragon", "Lightning Bolt"]
    assert by_price[-1] == "Jötun Grunt"  # unknown prices come last
    assert names(migrated, user, sort="quantity")[0] == "Shivan Dragon"
    assert names(migrated, user, rarity="mythic", sort="price") == ["Sol Ring"]


# ---------------------------------------------------------------------------- edit / delete (#98, #99)
def test_edit_changes_the_entry_and_its_timestamp(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    entry, _ = add(migrated, user, card, 1)
    later = NOW + timedelta(hours=1)
    with uow(migrated) as unit:
        result = unit.vault.update(user, entry.id, 3, None, Finish.FOIL, later)
        unit.commit()
    assert result is not None
    changed, merged = result
    assert (changed.quantity, changed.finish, merged) == (3, Finish.FOIL, False)
    assert changed.updated_at == later


def test_editing_into_an_existing_combination_merges_both(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    nm, _ = add(migrated, user, card, 2, Condition.NM)
    lp, _ = add(migrated, user, card, 3, Condition.LP)
    with uow(migrated) as unit:
        result = unit.vault.update(user, lp.id, None, Condition.NM, None, NOW)
        unit.commit()
    assert result is not None
    survivor, merged = result
    assert merged
    assert (survivor.id, survivor.quantity) == (nm.id, 5)
    assert scalar(migrated, "SELECT count(*) FROM vault_entries") == 1


def test_a_merge_over_the_cap_leaves_both_entries_alone(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    add(migrated, user, card, 9000, Condition.NM)
    lp, _ = add(migrated, user, card, 1000, Condition.LP)
    with uow(migrated) as unit, pytest.raises(ValidationFailed):
        unit.vault.update(user, lp.id, None, Condition.NM, None, NOW)
    assert scalar(migrated, "SELECT count(*) FROM vault_entries") == 2
    assert scalar(migrated, "SELECT sum(quantity) FROM vault_entries") == 10000


def test_delete_is_true_once_then_false(migrated: Engine) -> None:
    user, card = new_user(migrated, "u"), put_card(migrated)
    entry, _ = add(migrated, user, card)
    with uow(migrated) as unit:
        assert unit.vault.delete(user, entry.id) is True
        unit.commit()
    with uow(migrated) as unit:
        assert unit.vault.delete(user, entry.id) is False


def test_session_type_is_a_plain_sqlalchemy_session(migrated: Engine) -> None:
    with Session(migrated) as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1


# ---------------------------------------------------------------------------- summary (#133)
def test_the_summary_counts_values_and_flags_unpriced_entries(migrated: Engine) -> None:
    alice, bob = new_user(migrated, "alice"), new_user(migrated, "bob")
    both = put_card(migrated, name="Both", number="1", prices=Prices(usd=Decimal("1.10"), eur=Decimal("1.00"), usd_foil=Decimal("2.20")))  # fmt: skip
    usd_only = put_card(migrated, name="Usd only", number="2", prices=Prices(usd=Decimal("0.35")))
    nothing = put_card(migrated, name="Nothing", number="3", prices=Prices())
    add(migrated, alice, both, 3)  # 3.30 USD, 3.00 EUR
    add(migrated, alice, both, 1, finish=Finish.FOIL)  # 2.20 USD, no foil EUR
    add(migrated, alice, usd_only, 2, cond=Condition.LP)  # 0.70 USD, no EUR
    add(migrated, alice, nothing, 4)  # no price at all
    add(migrated, bob, both, 9999)  # another user's cards never count
    with uow(migrated) as unit:
        summary = unit.vault.summary(alice)
    assert (summary.total_cards, summary.entries) == (10, 4)
    assert summary.value_usd == Decimal("6.20")
    assert summary.value_eur == Decimal("3.00")
    assert (summary.unpriced_usd, summary.unpriced_eur) == (1, 3)
    assert summary.oldest_prices_updated_at == summary.newest_prices_updated_at == NOW


def test_an_empty_vault_summarises_to_zeros(migrated: Engine) -> None:
    user = new_user(migrated, "empty")
    with uow(migrated) as unit:
        summary = unit.vault.summary(user)
    assert (summary.total_cards, summary.entries, summary.unpriced_usd) == (0, 0, 0)
    assert summary.value_usd == Decimal("0.00") and summary.value_eur == Decimal("0.00")
    assert summary.oldest_prices_updated_at is None


def test_a_real_price_of_zero_is_priced_not_unpriced(migrated: Engine) -> None:
    user = new_user(migrated, "zero")
    free = put_card(migrated, name="Free", number="1", prices=Prices(usd=Decimal("0.00")))
    add(migrated, user, free, 5)
    with uow(migrated) as unit:
        summary = unit.vault.summary(user)
    assert summary.unpriced_usd == 0 and summary.value_usd == Decimal("0.00")


# ---------------------------------------------------------------------------- bulk refresh (#137)
def test_owned_ids_pages_through_distinct_owned_cards_only(migrated: Engine) -> None:
    alice, bob = new_user(migrated, "alice"), new_user(migrated, "bob")
    ids = sorted(put_card(migrated, name=f"Card {n}", number=str(n)) for n in range(1, 6))
    unowned = put_card(migrated, name="Unowned", number="99")
    for owner in (alice, bob):  # owned twice, still listed once
        for card in ids[:4]:
            add(migrated, owner, card)
    with uow(migrated) as unit:
        first = unit.cards.owned_ids(None, 3)
        second = unit.cards.owned_ids(first[-1], 3)
        third = unit.cards.owned_ids(second[-1], 3) if second else []
    assert first == ids[:3] and second == ids[3:4] and third == []
    assert unowned not in first + second


def test_a_batch_of_75_is_one_statement_and_refreshes_prices(migrated: Engine) -> None:
    from sqlalchemy import event

    cards = [
        make_card(
            name=f"Card {n}", set_code="tst", number=str(n), prices=Prices(usd=Decimal("1.00"))
        )
        for n in range(75)
    ]
    with uow(migrated) as unit:
        unit.cards.upsert_snapshots(cards, NOW)
        unit.commit()
    cheaper = [
        make_card(
            name=f"Card {n}", set_code="tst", number=str(n), prices=Prices(usd=Decimal("0.50"))
        )
        for n in range(75)
    ]
    later = NOW + timedelta(days=1)
    statements: list[str] = []
    event.listen(
        migrated, "before_cursor_execute", lambda c, cur, stmt, *a: statements.append(stmt)
    )
    with uow(migrated) as unit:
        unit.cards.upsert_snapshots([*cheaper, cheaper[0]], later)  # a duplicate collapses
        unit.commit()
    assert sum("INSERT INTO cards" in s for s in statements) == 1
    assert scalar(migrated, "SELECT count(*) FROM cards") == 75
    assert scalar(migrated, "SELECT count(*) FROM cards WHERE usd = 0.50") == 75
    with migrated.connect() as connection:
        stamps = (
            connection.execute(text("SELECT DISTINCT prices_updated_at FROM cards")).scalars().all()
        )
    assert stamps == [later]


def test_an_empty_batch_writes_nothing(migrated: Engine) -> None:
    with uow(migrated) as unit:
        unit.cards.upsert_snapshots([], NOW)
        unit.commit()
    assert scalar(migrated, "SELECT count(*) FROM cards") == 0
