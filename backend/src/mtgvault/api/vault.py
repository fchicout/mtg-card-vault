"""Vault endpoints (US-005..US-011). Every one acts for the user of the token, never for a user
named in the request (FR-VLT-07)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict

from mtgvault.api.catalog import CardSummary, card_summary
from mtgvault.api.dependencies import get_vault_service
from mtgvault.api.security import current_user
from mtgvault.application.vault_query import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, build_vault_query
from mtgvault.application.vault_service import VaultService
from mtgvault.domain.user import User
from mtgvault.domain.vault import Condition, Finish, VaultItem

router = APIRouter(prefix="/vault", tags=["vault"])
Service = Annotated[VaultService, Depends(get_vault_service)]
Owner = Annotated[User, Depends(current_user)]


class VaultItemDto(BaseModel):
    id: UUID
    quantity: int
    condition: Condition
    finish: Finish
    created_at: datetime
    updated_at: datetime
    card: CardSummary
    available_finishes: list[str]
    unit_price: Decimal | None = None
    unit_price_eur: Decimal | None = None
    line_value_usd: Decimal | None = None
    line_value_eur: Decimal | None = None
    prices_updated_at: datetime | None = None
    prices_stale: bool


class VaultPage(BaseModel):
    items: list[VaultItemDto]
    page: int
    page_size: int
    total: int


class AddEntry(BaseModel):
    """Only these fields are accepted: a user id in the body is rejected, not ignored."""

    model_config = ConfigDict(extra="forbid")

    card_id: UUID
    quantity: int
    condition: Condition = Condition.NM
    finish: Finish


class EditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int | None = None
    condition: Condition | None = None
    finish: Finish | None = None


def _dto(item: VaultItem, service: VaultService) -> VaultItemDto:
    card = item.snapshot.card
    return VaultItemDto(
        id=item.entry.id,
        quantity=item.entry.quantity,
        condition=item.entry.condition,
        finish=item.entry.finish,
        created_at=item.entry.created_at,
        updated_at=item.entry.updated_at,
        card=card_summary(card),
        available_finishes=list(card.finishes),
        unit_price=item.unit_price,
        unit_price_eur=item.unit_price_eur,
        line_value_usd=item.line_value_usd,
        line_value_eur=item.line_value_eur,
        prices_updated_at=item.snapshot.prices_updated_at,
        prices_stale=service.prices_stale(item.snapshot),
    )


@router.post(
    "/entries",
    operation_id="addVaultEntry",
    summary="Add a printing, or add to the entry that already exists",
    status_code=status.HTTP_201_CREATED,
    responses={status.HTTP_200_OK: {"model": VaultItemDto, "description": "Merged into an entry"}},
)
def add_entry(body: AddEntry, owner: Owner, service: Service, response: Response) -> VaultItemDto:
    item, created = service.add(owner.id, body.card_id, body.quantity, body.condition, body.finish)
    if not created:
        response.status_code = status.HTTP_200_OK
    return _dto(item, service)


@router.get("/entries", operation_id="listVaultEntries", summary="The caller's entries")
def list_entries(  # one parameter per documented query field
    owner: Owner,
    service: Service,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    q: Annotated[str | None, Query(max_length=100, description="Part of the card name")] = None,
    set: Annotated[str | None, Query(max_length=6)] = None,
    colors: Annotated[str | None, Query(max_length=11)] = None,
    rarity: Annotated[str | None, Query(max_length=10)] = None,
    type: Annotated[str | None, Query(max_length=40)] = None,
    sort: Annotated[str, Query(description="name, set, price, added or quantity")] = "added",
    dir: Annotated[str | None, Query(description="asc or desc")] = None,
) -> VaultPage:
    query = build_vault_query(
        page=page, page_size=page_size, q=q, set_code=set, colors=colors, rarity=rarity,
        type_text=type, sort=sort, direction=dir,
    )  # fmt: skip
    items, total = service.list(owner.id, query)
    return VaultPage(
        items=[_dto(i, service) for i in items], page=page, page_size=page_size, total=total
    )


@router.patch("/entries/{entry_id}", operation_id="editVaultEntry", summary="Change an entry")
def edit_entry(entry_id: UUID, body: EditEntry, owner: Owner, service: Service) -> VaultItemDto:
    """A new combination that equals another entry merges the two; the merged entry comes back."""
    item, _ = service.edit(owner.id, entry_id, body.quantity, body.condition, body.finish)
    return _dto(item, service)


@router.delete(
    "/entries/{entry_id}",
    operation_id="removeVaultEntry",
    summary="Remove an entry",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_entry(entry_id: UUID, owner: Owner, service: Service) -> None:
    service.remove(owner.id, entry_id)
