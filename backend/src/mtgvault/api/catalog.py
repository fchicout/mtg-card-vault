"""Catalogue endpoints: search, card detail and printings (US-012..US-014, UC-10)."""

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel

from mtgvault.api.dependencies import get_catalog_service, get_vault_service
from mtgvault.application.catalog_query import CatalogFilters, parse_colors
from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.vault_service import VaultService
from mtgvault.domain.card import Card, CardFace, Prices, ResultPage

router = APIRouter(prefix="/catalog", tags=["catalog"])


class PricesDto(BaseModel):
    """Prices as Scryfall reports them (decimal strings); null means no price, not zero."""

    usd: Decimal | None = None
    usd_foil: Decimal | None = None
    usd_etched: Decimal | None = None
    eur: Decimal | None = None
    eur_foil: Decimal | None = None
    eur_etched: Decimal | None = None


class CardSummary(BaseModel):
    id: UUID
    name: str
    type_line: str | None = None
    set_code: str
    set_name: str
    collector_number: str
    rarity: str
    image_small: str | None = None


class CardFaceDto(BaseModel):
    name: str
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    image_normal: str | None = None


class CardDetail(CardSummary):
    oracle_id: UUID | None = None
    lang: str
    layout: str
    mana_cost: str | None = None
    oracle_text: str | None = None
    colors: list[str]
    finishes: list[str]
    image_normal: str | None = None
    faces: list[CardFaceDto]
    prices: PricesDto


class Printing(BaseModel):
    id: UUID
    set_code: str
    set_name: str
    collector_number: str
    lang: str
    rarity: str
    finishes: list[str]
    image_small: str | None = None
    prices: PricesDto


class PageMeta(BaseModel):
    page: int
    has_more: bool
    total: int | None = None


class CardPage(PageMeta):
    items: list[CardSummary]


class PrintingPage(PageMeta):
    items: list[Printing]


def _prices(prices: Prices) -> PricesDto:
    return PricesDto(**vars(prices))


def card_summary(card: Card) -> CardSummary:
    return CardSummary(
        id=card.id,
        name=card.name,
        type_line=card.type_line,
        set_code=card.set_code,
        set_name=card.set_name,
        collector_number=card.collector_number,
        rarity=card.rarity,
        image_small=card.image_small,
    )


def _face(face: CardFace) -> CardFaceDto:
    return CardFaceDto(
        name=face.name,
        mana_cost=face.mana_cost,
        type_line=face.type_line,
        oracle_text=face.oracle_text,
        image_normal=face.image_normal,
    )


def _detail(card: Card) -> CardDetail:
    return CardDetail(
        **card_summary(card).model_dump(),
        oracle_id=card.oracle_id,
        lang=card.lang,
        layout=card.layout,
        mana_cost=card.mana_cost,
        oracle_text=card.oracle_text,
        colors=list(card.colors),
        finishes=list(card.finishes),
        image_normal=card.image_normal,
        faces=[_face(f) for f in card.faces],
        prices=_prices(card.prices),
    )


def _printing(card: Card) -> Printing:
    return Printing(
        id=card.id,
        set_code=card.set_code,
        set_name=card.set_name,
        collector_number=card.collector_number,
        lang=card.lang,
        rarity=card.rarity,
        finishes=list(card.finishes),
        image_small=card.image_small,
        prices=_prices(card.prices),
    )


def _meta(page: ResultPage[Card]) -> dict[str, object]:
    return {"page": page.page, "has_more": page.has_more, "total": page.total}


PageNumber = Annotated[int, Query(ge=1, le=100, description="1-based page of the source list")]
Service = Annotated[CatalogService, Depends(get_catalog_service)]


@router.get("/cards", operation_id="searchCards", summary="Search cards by name and filters")
def search_cards(  # one parameter per documented query field
    service: Service,
    q: Annotated[str | None, Query(max_length=100, description="Words of the card name")] = None,
    set: Annotated[str | None, Query(max_length=6, description="Set code, e.g. lea")] = None,
    colors: Annotated[
        str | None, Query(max_length=11, description="Letters W U B R G or C")
    ] = None,
    type: Annotated[str | None, Query(max_length=40, description="Part of the type line")] = None,
    rarity: Literal["common", "uncommon", "rare", "mythic"] | None = None,
    page: PageNumber = 1,
) -> CardPage:
    """Unique cards matching the text and filters; an empty list when nothing matches."""
    filters = CatalogFilters(
        set_code=set.lower() if set else None,
        colors=parse_colors(colors),
        type_text=type.strip() if type else None,
        rarity=rarity,
    )
    result = service.search(q, filters, page)
    return CardPage(items=[card_summary(c) for c in result.items], **_meta(result))  # type: ignore[arg-type]


@router.get("/cards/{card_id}", operation_id="getCard", summary="One printing in detail")
def get_card(
    card_id: UUID,
    service: Service,
    vault: Annotated[VaultService, Depends(get_vault_service)],
    background: BackgroundTasks,
) -> CardDetail:
    detail = _detail(service.get(card_id))
    background.add_task(vault.refresh_card_if_stale, card_id)  # after the response (FR-PRC-05)
    return detail


@router.get(
    "/cards/{card_id}/printings",
    operation_id="getCardPrintings",
    summary="All printings of a card, newest first",
)
def get_printings(card_id: UUID, service: Service, page: PageNumber = 1) -> PrintingPage:
    result = service.printings(card_id, page)
    return PrintingPage(items=[_printing(c) for c in result.items], **_meta(result))  # type: ignore[arg-type]
