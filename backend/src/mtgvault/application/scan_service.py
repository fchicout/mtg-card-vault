"""The scan use case (UC-02 steps 6-8): recognise, interpret, resolve and rank. A scan never
changes the vault (FR-SCN-05) and never keeps the image (FR-SCN-06)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from mtgvault.application.catalog_query import CatalogFilters
from mtgvault.application.catalog_service import CatalogService
from mtgvault.application.ports import TextRecognizer
from mtgvault.application.scan_ranking import Candidate, rank
from mtgvault.domain.card import Card
from mtgvault.domain.scan import CollectorInfo, clean_title, parse_collector

Reason = Literal["unreadable", "no_match"]
_MAX_POOL = 25  # candidates gathered before ranking


@dataclass(frozen=True)
class ScanResult:
    title_text: str  # what the OCR read in the title band (shown to the user)
    collector_text: str  # what the OCR read in the collector band
    candidates: list[Candidate]
    reason: Reason | None  # set when there are no candidates


def _title_queries(title: str) -> list[str]:
    """From specific to loose: all words, then the two longest, then the longest."""
    words = re.findall(r"[^\W_]+(?:'[^\W_]+)?", title)
    longest = sorted(words, key=len, reverse=True)
    attempts = [" ".join(words)]
    if len(words) > 2:
        attempts.append(" ".join(longest[:2]))
    if longest and len(longest[0]) >= 4:
        attempts.append(longest[0])
    return list(dict.fromkeys(a for a in attempts if a))


class ScanService:
    def __init__(self, recognizer: TextRecognizer, catalog: CatalogService) -> None:
        self._recognizer = recognizer
        self._catalog = catalog

    def scan(self, image: bytes) -> ScanResult:
        text = self._recognizer.read(image)  # raises ValidationFailed for an undecodable image
        title = clean_title(text.title)
        collector = parse_collector(text.collector)
        if title is None and collector.number is None:
            return ScanResult(text.title, text.collector, [], "unreadable")
        pool = self._pool(title, collector)
        ranked = rank(title, collector, pool)
        return ScanResult(text.title, text.collector, ranked, None if ranked else "no_match")

    def _pool(self, title: str | None, collector: CollectorInfo) -> list[Card]:
        found: dict[object, Card] = {}
        if collector.set_code and collector.number:
            for card in self._catalog.find_printing(collector.set_code, collector.number):
                found[card.id] = card
        if title:
            for query in _title_queries(title):
                for card in self._catalog.search(query, CatalogFilters(), 1).items:
                    found.setdefault(card.id, card)
                if len(found) >= _MAX_POOL or any(
                    c.name.lower() == title.lower() for c in found.values()
                ):
                    break
        return list(found.values())[:_MAX_POOL]
