"""PostgreSQL vault repository. Every method takes the user id first and every statement filters
by it: a caller cannot reach another user's rows through this class (FR-VLT-07, ADR-005)."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, case, delete, func, literal_column, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from mtgvault.adapters.db.card_repository import snapshot_from_row
from mtgvault.adapters.db.models import CardRow, VaultEntryRow
from mtgvault.application.vault_query import VaultQuery
from mtgvault.domain.vault import (
    MAX_QUANTITY,
    Condition,
    Finish,
    VaultEntry,
    VaultItem,
    VaultSummary,
    merged_quantity,
)


def _entry(row: VaultEntryRow) -> VaultEntry:
    return VaultEntry(
        id=row.id,
        user_id=row.user_id,
        card_id=row.card_id,
        quantity=row.quantity,
        condition=Condition(row.condition),
        finish=Finish(row.finish),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _like(text: str) -> str:
    """A LIKE pattern for 'contains', with the wildcard characters of the input escaped."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class SqlAlchemyVaultRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------ create / merge
    def add_or_merge(
        self,
        user_id: UUID,
        card_id: UUID,
        quantity: int,
        condition: Condition,
        finish: Finish,
        now: datetime,
    ) -> tuple[VaultEntry, bool]:
        base = insert(VaultEntryRow).values(
            id=uuid4(),
            user_id=user_id,
            card_id=card_id,
            quantity=quantity,
            condition=condition.value,
            finish=finish.value,
            created_at=now,
            updated_at=now,
        )
        statement: Any = base.on_conflict_do_update(
            constraint="uq_vault_entries_identity",
            set_={
                "quantity": VaultEntryRow.quantity + base.excluded.quantity,
                "updated_at": now,
            },
            # A total above the cap updates nothing: no row comes back and we report it.
            where=VaultEntryRow.quantity + base.excluded.quantity <= MAX_QUANTITY,
        ).returning(VaultEntryRow, literal_column("(xmax = 0)").label("created"))  # 0: fresh insert
        row = self._session.execute(statement).first()
        if row is None:
            existing = self._by_identity(user_id, card_id, condition, finish)
            merged_quantity(existing.quantity, quantity)  # raises the validation error
            raise RuntimeError("the merge was refused without a reason")  # pragma: no cover
        return _entry(row[0]), bool(row[1])

    def _by_identity(
        self, user_id: UUID, card_id: UUID, condition: Condition, finish: Finish
    ) -> VaultEntryRow:
        return self._session.execute(
            select(VaultEntryRow).where(
                VaultEntryRow.user_id == user_id,
                VaultEntryRow.card_id == card_id,
                VaultEntryRow.condition == condition.value,
                VaultEntryRow.finish == finish.value,
            )
        ).scalar_one()

    # ------------------------------------------------------------------ read
    def get_item(self, user_id: UUID, entry_id: UUID) -> VaultItem | None:
        statement = self._joined(user_id).where(VaultEntryRow.id == entry_id)
        row = self._session.execute(statement).first()
        return None if row is None else VaultItem(_entry(row[0]), snapshot_from_row(row[1]))

    def list_items(self, user_id: UUID, query: VaultQuery) -> tuple[list[VaultItem], int]:
        conditions = self._conditions(query)
        total = self._session.execute(
            select(func.count())
            .select_from(VaultEntryRow)
            .join(CardRow, CardRow.scryfall_id == VaultEntryRow.card_id)
            .where(VaultEntryRow.user_id == user_id, *conditions)
        ).scalar_one()
        statement = (
            self._joined(user_id)
            .where(*conditions)
            .order_by(*self._order(query))
            .limit(query.page_size)
            .offset((query.page - 1) * query.page_size)
        )
        rows = self._session.execute(statement).all()
        return [VaultItem(_entry(r[0]), snapshot_from_row(r[1])) for r in rows], total

    def count(self, user_id: UUID) -> int:
        return self._session.execute(
            select(func.count()).select_from(VaultEntryRow).where(VaultEntryRow.user_id == user_id)
        ).scalar_one()

    def _joined(self, user_id: UUID) -> Select[VaultEntryRow, CardRow]:
        return (
            select(VaultEntryRow, CardRow)
            .join(CardRow, CardRow.scryfall_id == VaultEntryRow.card_id)
            .where(VaultEntryRow.user_id == user_id)
        )

    @staticmethod
    def _conditions(query: VaultQuery) -> list[ColumnElement[bool]]:
        found: list[ColumnElement[bool]] = []
        if query.name:
            found.append(CardRow.name_search.like(_like(query.name), escape="\\"))
        if query.set_code:
            found.append(CardRow.set_code == query.set_code)
        if query.rarity:
            found.append(CardRow.rarity == query.rarity)
        if query.type_text:
            found.append(func.lower(CardRow.type_line).like(_like(query.type_text), escape="\\"))
        if query.colors:
            found.append(CardRow.colors.contains(list(query.colors)))
        return found

    @staticmethod
    def _order(query: VaultQuery) -> list[Any]:
        price = case(
            (VaultEntryRow.finish == "nonfoil", CardRow.usd),
            (VaultEntryRow.finish == "foil", CardRow.usd_foil),
            else_=CardRow.usd_etched,
        )
        column: Any = {
            "name": CardRow.name_search,
            "set": CardRow.set_code,
            "price": price,
            "added": VaultEntryRow.created_at,
            "quantity": VaultEntryRow.quantity,
        }[query.sort]
        ordered = column.desc() if query.descending else column.asc()
        if query.sort == "price":
            ordered = ordered.nulls_last()  # unknown prices never head the list
        return [ordered, VaultEntryRow.id.asc()]  # the id keeps pages stable

    # ------------------------------------------------------------------ change
    def update(
        self,
        user_id: UUID,
        entry_id: UUID,
        quantity: int | None,
        condition: Condition | None,
        finish: Finish | None,
        now: datetime,
    ) -> tuple[VaultEntry, bool] | None:
        try:
            return self._update_once(user_id, entry_id, quantity, condition, finish, now)
        except IntegrityError:
            # A concurrent add created the target combination between our check and our write.
            self._session.rollback()
            return self._update_once(user_id, entry_id, quantity, condition, finish, now)

    def _update_once(
        self,
        user_id: UUID,
        entry_id: UUID,
        quantity: int | None,
        condition: Condition | None,
        finish: Finish | None,
        now: datetime,
    ) -> tuple[VaultEntry, bool] | None:
        row = self._session.execute(
            select(VaultEntryRow)
            .where(VaultEntryRow.id == entry_id, VaultEntryRow.user_id == user_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            return None
        new_quantity = row.quantity if quantity is None else quantity
        new_condition = row.condition if condition is None else condition.value
        new_finish = row.finish if finish is None else finish.value
        other = self._session.execute(
            select(VaultEntryRow)
            .where(
                and_(
                    VaultEntryRow.user_id == user_id,
                    VaultEntryRow.card_id == row.card_id,
                    VaultEntryRow.condition == new_condition,
                    VaultEntryRow.finish == new_finish,
                    VaultEntryRow.id != row.id,
                )
            )
            .with_for_update()
        ).scalar_one_or_none()
        if other is None:
            self._session.execute(
                update(VaultEntryRow)
                .where(VaultEntryRow.id == row.id, VaultEntryRow.user_id == user_id)
                .values(
                    quantity=new_quantity,
                    condition=new_condition,
                    finish=new_finish,
                    updated_at=now,
                )
            )
            self._session.expire(row)
            return _entry(self._session.get_one(VaultEntryRow, row.id)), False
        total = merged_quantity(other.quantity, new_quantity)  # over the cap: validation error
        self._session.execute(
            update(VaultEntryRow)
            .where(VaultEntryRow.id == other.id, VaultEntryRow.user_id == user_id)
            .values(quantity=total, updated_at=now)
        )
        self._session.execute(
            delete(VaultEntryRow).where(
                VaultEntryRow.id == row.id, VaultEntryRow.user_id == user_id
            )
        )
        self._session.expire(other)
        return _entry(self._session.get_one(VaultEntryRow, other.id)), True

    def delete(self, user_id: UUID, entry_id: UUID) -> bool:
        result = self._session.execute(
            delete(VaultEntryRow).where(
                VaultEntryRow.id == entry_id, VaultEntryRow.user_id == user_id
            )
        )
        return result.rowcount > 0  # type: ignore[attr-defined,no-any-return]

    def stale_card_ids(self, user_id: UUID, before: datetime, limit: int) -> list[UUID]:
        stamp = CardRow.prices_updated_at
        statement = (
            select(CardRow.scryfall_id)
            .join(VaultEntryRow, VaultEntryRow.card_id == CardRow.scryfall_id)
            .where(VaultEntryRow.user_id == user_id)
            .where((stamp.is_(None)) | (stamp < before))
            .group_by(CardRow.scryfall_id, stamp)
            .order_by(stamp.asc().nulls_first(), CardRow.scryfall_id)
            .limit(limit)
        )
        return list(self._session.scalars(statement))

    # ------------------------------------------------------------------ summary
    def summary(self, user_id: UUID) -> VaultSummary:
        usd, eur = _unit_price_column("usd"), _unit_price_column("eur")
        statement = (
            select(
                func.coalesce(func.sum(VaultEntryRow.quantity), 0),
                func.count(),
                func.coalesce(func.sum(VaultEntryRow.quantity * usd), 0),
                func.coalesce(func.sum(VaultEntryRow.quantity * eur), 0),
                func.count().filter(usd.is_(None)),
                func.count().filter(eur.is_(None)),
                func.min(CardRow.prices_updated_at),
                func.max(CardRow.prices_updated_at),
            )
            .select_from(VaultEntryRow)
            .join(CardRow, CardRow.scryfall_id == VaultEntryRow.card_id)
            .where(VaultEntryRow.user_id == user_id)
        )
        cards, entries, value_usd, value_eur, no_usd, no_eur, oldest, newest = (
            self._session.execute(statement).one()
        )
        return VaultSummary(
            total_cards=int(cards),
            entries=int(entries),
            value_usd=Decimal(value_usd).quantize(_CENT, rounding=ROUND_HALF_UP),
            value_eur=Decimal(value_eur).quantize(_CENT, rounding=ROUND_HALF_UP),
            unpriced_usd=int(no_usd),
            unpriced_eur=int(no_eur),
            oldest_prices_updated_at=oldest,
            newest_prices_updated_at=newest,
        )


_CENT = Decimal("0.01")


def _unit_price_column(currency: str) -> ColumnElement[Any]:
    """The price column of the card that matches the entry's finish (NULL when unknown)."""
    suffix = {"nonfoil": "", "foil": "_foil", "etched": "_etched"}
    return case(
        *[
            (VaultEntryRow.finish == finish, getattr(CardRow, f"{currency}{tail}"))
            for finish, tail in suffix.items()
        ],
        else_=None,
    )
