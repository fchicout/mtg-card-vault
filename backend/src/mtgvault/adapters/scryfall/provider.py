"""CardDataProvider backed by Scryfall (ADR-007). Query building stays in the application."""

from __future__ import annotations

from uuid import UUID

from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.mapper import card_from_json, page_from_json
from mtgvault.domain.card import Card, ResultPage
from mtgvault.domain.errors import NotFound, UpstreamUnavailable

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

    @staticmethod
    def _page(document: dict[str, object], page: int) -> ResultPage[Card]:
        try:
            return page_from_json(document, page)
        except (KeyError, ValueError, TypeError) as error:
            raise UpstreamUnavailable(_UNREADABLE) from error
