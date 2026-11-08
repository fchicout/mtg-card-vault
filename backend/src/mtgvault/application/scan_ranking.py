"""Ranking scan candidates (FR-SCN-04): pure and table-tested.

An exact set + collector-number match always comes first. Otherwise candidates are ordered by a
confidence in 0..1 that combines how well the card name matches the OCR title with whether the
set code and collector number also agree.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from mtgvault.domain.card import Card
from mtgvault.domain.scan import CollectorInfo

MAX_CANDIDATES = 5
MIN_CONFIDENCE = 0.35
_NAME_WEIGHT, _SET_WEIGHT, _NUMBER_WEIGHT = 0.6, 0.25, 0.15


@dataclass(frozen=True)
class Candidate:
    card: Card
    confidence: float
    exact: bool  # set code and collector number both match the OCR reading


def _plain(text: str) -> str:
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9 ]+", "", stripped.casefold()).strip()


def name_similarity(title: str | None, card_name: str) -> float:
    """0..1 similarity of an OCR title with a card name (the first face of a double-faced card)."""
    if not title:
        return 0.0
    best = 0.0
    for face in card_name.split(" // "):
        best = max(best, fuzz.ratio(_plain(title), _plain(face)) / 100)
    return best


def rank(title: str | None, collector: CollectorInfo, cards: list[Card]) -> list[Candidate]:
    """At most five plausible candidates, best first. Nothing plausible gives an empty list."""
    scored: list[Candidate] = []
    for card in cards:
        set_match = bool(collector.set_code) and card.set_code.lower() == collector.set_code
        number_match = (
            bool(collector.number) and card.collector_number.lstrip("0") == collector.number
        )
        similarity = name_similarity(title, card.name)
        exact = set_match and number_match
        confidence = (
            _NAME_WEIGHT * similarity + _SET_WEIGHT * set_match + _NUMBER_WEIGHT * number_match
        )
        if exact:  # the printing itself was read: trust it unless the title flatly disagrees
            confidence = max(confidence, 0.9 + 0.1 * similarity)
        scored.append(Candidate(card, round(min(confidence, 1.0), 3), exact))
    scored.sort(
        key=lambda c: (c.exact, c.confidence, name_similarity(title, c.card.name)), reverse=True
    )
    unique: list[Candidate] = []
    seen: set[object] = set()
    for candidate in scored:
        key = candidate.card.id
        if key in seen or candidate.confidence < MIN_CONFIDENCE:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique[:MAX_CANDIDATES]
