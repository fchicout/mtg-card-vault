"""Turns validated user input into a Scryfall search query (FR-CAT-01, FR-CAT-02).

Nothing the user types is passed through as query syntax: free text becomes quoted name terms
(quotes and backslashes removed), and every filter value is checked against a strict pattern or a
closed list before it is placed in its own operator. So a user can never add operators such as
``or``, ``-``, parentheses or ``oracle:`` to the upstream query.
"""

import re
from dataclasses import dataclass

from mtgvault.domain.errors import FieldError, ValidationFailed

MAX_TEXT = 100
MAX_WORDS = 8
MAX_TYPE = 40
RARITIES = ("common", "uncommon", "rare", "mythic")
COLOR_LETTERS = ("W", "U", "B", "R", "G", "C")

_SET = re.compile(r"^[a-z0-9]{2,6}$")
_TYPE = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,39}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


@dataclass(frozen=True)
class CatalogFilters:
    set_code: str | None = None
    colors: tuple[str, ...] = ()
    type_text: str | None = None
    rarity: str | None = None

    def is_empty(self) -> bool:
        return not (self.set_code or self.colors or self.type_text or self.rarity)


def _clean_words(text: str) -> list[str]:
    cleaned = _CONTROL.sub(" ", text).replace('"', " ").replace("\\", " ")
    return cleaned.split()


def parse_colors(raw: str | None) -> tuple[str, ...]:
    """``"R,G"`` or ``"rg"`` to ``("R", "G")``; raises ``ValidationFailed`` for anything else."""
    if not raw:
        return ()
    letters = list(raw.upper().replace(",", "").replace(" ", ""))
    unique = tuple(dict.fromkeys(letters))
    if any(c not in COLOR_LETTERS for c in unique):
        raise ValidationFailed(
            "Invalid filter.", (FieldError("colors", "Use W, U, B, R, G or C."),)
        )
    if "C" in unique and len(unique) > 1:
        raise ValidationFailed(
            "Invalid filter.", (FieldError("colors", "C (colourless) stands alone."),)
        )
    return unique


Checked = tuple[list[str], list[FieldError]]


def _text_terms(text: str | None) -> Checked:
    words = _clean_words(text or "")
    errors: list[FieldError] = []
    if text is not None and len(text) > MAX_TEXT:
        errors.append(FieldError("q", f"At most {MAX_TEXT} characters."))
    if len(words) > MAX_WORDS:
        errors.append(FieldError("q", f"At most {MAX_WORDS} words."))
    return [f'name:"{word}"' for word in words], errors


def _one(value: str | None, valid: bool, term: str, field: str, hint: str) -> Checked:
    if value is None:
        return [], []
    return ([term], []) if valid else ([], [FieldError(field, hint)])


def _filter_terms(filters: CatalogFilters) -> Checked:
    set_code, type_text, rarity = filters.set_code, filters.type_text, filters.rarity
    type_term = f't:"{(type_text or "").strip()}"'
    checks = [
        _one(set_code, bool(set_code and _SET.match(set_code)), f"set:{set_code}", "set",
             "Use the 2-6 letter or digit set code."),
        _one(type_text, bool(type_text and _TYPE.match(type_text)), type_term, "type",
             f"Letters, spaces and hyphens, up to {MAX_TYPE}."),
        _one(rarity, rarity in RARITIES, f"r:{rarity}", "rarity",
             "Use common, uncommon, rare or mythic."),
    ]  # fmt: skip
    if filters.colors:
        known = all(c in COLOR_LETTERS for c in filters.colors)
        checks.append(
            _one(
                "c",
                known,
                "c:" + "".join(filters.colors).lower(),
                "colors",
                "Use W, U, B, R, G or C.",
            )
        )
    terms = [term for found, _ in checks for term in found]
    errors = [error for _, found in checks for error in found]
    return terms, errors


def build_query(text: str | None, filters: CatalogFilters) -> str:
    """The Scryfall query for the input; raises ``ValidationFailed`` with the offending fields."""
    text_terms, text_errors = _text_terms(text)
    filter_terms, filter_errors = _filter_terms(filters)
    terms = text_terms + filter_terms
    errors = text_errors + filter_errors
    if not errors and not terms:
        errors.append(FieldError("q", "Enter a search text or choose a filter."))
    if errors:
        raise ValidationFailed("The search is invalid.", tuple(errors))
    return " ".join(terms)
