"""Scryfall card and list objects to the application's card model (FR-CAT-03, FR-DAT-02).

Layouts differ: a normal card has everything at the top level, a transform or modal card keeps
mana cost, text and images per face, a split card has both. The mapper hides that. Images stay
Scryfall CDN URLs, untouched (NFR-LEG-01).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from mtgvault.domain.card import Card, CardFace, Prices, ResultPage

FACE_SEPARATOR = " // "


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def _price(value: object) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except ValueError:
        return None


def _images(data: Mapping[str, Any]) -> tuple[str | None, str | None]:
    uris = data.get("image_uris")
    if isinstance(uris, Mapping):
        return _text(uris.get("small")), _text(uris.get("normal"))
    return None, None


def _face(data: Mapping[str, Any]) -> CardFace:
    small, normal = _images(data)
    return CardFace(
        name=str(data.get("name", "")),
        mana_cost=_text(data.get("mana_cost")),
        type_line=_text(data.get("type_line")),
        oracle_text=_text(data.get("oracle_text")),
        image_small=small,
        image_normal=normal,
    )


def _joined(values: list[str | None], separator: str) -> str | None:
    present = [v for v in values if v]
    return separator.join(present) if present else None


def prices_from_json(data: Mapping[str, Any] | None) -> Prices:
    data = data or {}
    return Prices(
        usd=_price(data.get("usd")),
        usd_foil=_price(data.get("usd_foil")),
        usd_etched=_price(data.get("usd_etched")),
        eur=_price(data.get("eur")),
        eur_foil=_price(data.get("eur_foil")),
        eur_etched=_price(data.get("eur_etched")),
    )


def card_from_json(data: Mapping[str, Any]) -> Card:
    raw_faces = [f for f in data.get("card_faces") or [] if isinstance(f, Mapping)]
    faces = tuple(_face(f) for f in raw_faces)
    small, normal = _images(data)
    if small is None and normal is None and faces:
        small, normal = faces[0].image_small, faces[0].image_normal
    colors = data.get("colors")
    if colors is None:  # multi-faced cards keep colours per face
        colors = [c for f in raw_faces for c in f.get("colors") or []]
    oracle_id = _uuid(data.get("oracle_id")) or next(
        (u for f in raw_faces if (u := _uuid(f.get("oracle_id")))), None
    )
    return Card(
        id=UUID(str(data["id"])),
        oracle_id=oracle_id,
        name=str(data["name"]),
        set_code=str(data["set"]),
        set_name=str(data.get("set_name", data["set"])),
        collector_number=str(data["collector_number"]),
        lang=str(data.get("lang", "en")),
        rarity=str(data.get("rarity", "common")),
        layout=str(data.get("layout", "normal")),
        type_line=_text(data.get("type_line"))
        or _joined([f.type_line for f in faces], FACE_SEPARATOR),
        mana_cost=_text(data.get("mana_cost"))
        or _joined([f.mana_cost for f in faces], FACE_SEPARATOR),
        oracle_text=_text(data.get("oracle_text"))
        or _joined([f.oracle_text for f in faces], "\n\n"),
        colors=tuple(dict.fromkeys(str(c) for c in colors)),
        finishes=tuple(str(f) for f in data.get("finishes") or []),
        image_small=small,
        image_normal=normal,
        prices=prices_from_json(data.get("prices")),
        faces=faces if len(faces) > 1 else (),
    )


def page_from_json(data: Mapping[str, Any], page: int) -> ResultPage[Card]:
    items = tuple(card_from_json(c) for c in data.get("data") or [])
    total = data.get("total_cards")
    return ResultPage(
        items=items,
        page=page,
        has_more=bool(data.get("has_more", False)),
        total=int(total) if isinstance(total, int) else None,
    )
