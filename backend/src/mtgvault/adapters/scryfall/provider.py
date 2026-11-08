"""CardDataProvider backed by Scryfall (ADR-007). Query building stays in the application."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.mapper import card_from_json, page_from_json
from mtgvault.domain.card import Card, LookupResult, ResultPage
from mtgvault.domain.errors import NotFound, UpstreamUnavailable

BATCH_SIZE = 75  # the most identifiers Scryfall accepts per collection request
_UNREADABLE = "The data source sent an unexpected answer."


class ScryfallCardProvider:
    def __init__(self, client: ScryfallClient) -> None:
        self._client = client

    def search(self, query: str, page: int) -> ResultPage[Card]:
        params: dict[str, str | int] = {
            "q": query,
            "unique": "cards",
            "order": "name",
            "page": page,
        }
        try:
            document = self._client.get_json("/cards/search", params)
        except NotFound:  # Scryfall answers 404 when nothing matches
            return ResultPage(items=(), page=page, has_more=False, total=0)
        return self._page(document, page)

    def get(self, card_id: UUID) -> Card:
        document = self._client.get_json(f"/cards/{card_id}")
        try:
            return card_from_json(document)
        except (KeyError, ValueError, TypeError) as error:
            raise UpstreamUnavailable(_UNREADABLE) from error

    def printings(self, oracle_id: UUID, page: int) -> ResultPage[Card]:
        params: dict[str, str | int] = {
            "q": f"oracleid:{oracle_id}",
            "unique": "prints",
            "order": "released",
            "dir": "desc",
            "include_multilingual": "true",
            "page": page,
        }
        try:
            document = self._client.get_json("/cards/search", params)
        except NotFound:
            return ResultPage(items=(), page=page, has_more=False, total=0)
        return self._page(document, page)

    def lookup(self, card_ids: Sequence[UUID]) -> LookupResult:
        """Cards by id through ``POST /cards/collection``, at most 75 per request."""
        cards: list[Card] = []
        missing: list[UUID] = []
        for start in range(0, len(card_ids), BATCH_SIZE):
            batch = card_ids[start : start + BATCH_SIZE]
            body = {"identifiers": [{"id": str(card_id)} for card_id in batch]}
            document = self._client.post_json("/cards/collection", body)
            try:
                cards.extend(card_from_json(item) for item in _list(document, "data"))
                missing.extend(UUID(str(item["id"])) for item in _list(document, "not_found"))
            except (KeyError, ValueError, TypeError) as error:
                raise UpstreamUnavailable(_UNREADABLE) from error
        return LookupResult(tuple(cards), tuple(missing))

    @staticmethod
    def _page(document: dict[str, object], page: int) -> ResultPage[Card]:
        try:
            return page_from_json(document, page)
        except (KeyError, ValueError, TypeError) as error:
            raise UpstreamUnavailable(_UNREADABLE) from error


def _list(document: dict[str, object], key: str) -> list[dict[str, object]]:
    value = document.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(key)
    return value
