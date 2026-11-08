"""Validated vault list queries: paging, filters and whitelisted sorting (FR-VLT-02, FR-VLT-05)."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from mtgvault.application.catalog_query import RARITIES, parse_colors
from mtgvault.domain.errors import FieldError, ValidationFailed

SortField = Literal["name", "set", "price", "added", "quantity"]
SORT_FIELDS: tuple[SortField, ...] = ("name", "set", "price", "added", "quantity")
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
MAX_NAME = 100

_SET = re.compile(r"^[a-z0-9]{2,6}$")
_TYPE = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,39}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def normalise(text: str) -> str:
    """Lower-case, accent-free, single-spaced: how names are stored and searched."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(_CONTROL.sub(" ", stripped).casefold().split())


@dataclass(frozen=True)
class VaultQuery:
    page: int = 1
    page_size: int = DEFAULT_PAGE_SIZE
    name: str | None = None  # already normalised
    set_code: str | None = None
    colors: tuple[str, ...] = ()
    rarity: str | None = None
    type_text: str | None = None  # already lower-cased
    sort: SortField = "added"
    descending: bool = True


def _paging_errors(page: int, page_size: int) -> list[FieldError]:
    errors: list[FieldError] = []
    if not 1 <= page <= 100_000:
        errors.append(FieldError("page", "Use a page number of 1 or more."))
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        errors.append(FieldError("page_size", f"Use a page size from 1 to {MAX_PAGE_SIZE}."))
    return errors


def _filter_errors(
    q: str | None, set_code: str | None, rarity: str | None, type_text: str | None
) -> list[FieldError]:
    checks = [
        (bool(q) and len(q or "") > MAX_NAME, FieldError("q", f"At most {MAX_NAME} characters.")),
        (
            bool(set_code) and not _SET.match((set_code or "").lower()),
            FieldError("set", "Use the 2-6 letter or digit set code."),
        ),
        (
            bool(rarity) and rarity not in RARITIES,
            FieldError("rarity", "Use common, uncommon, rare or mythic."),
        ),
        (
            bool(type_text) and not _TYPE.match((type_text or "").strip()),
            FieldError("type", "Letters, spaces and hyphens, up to 40."),
        ),
    ]
    return [error for failed, error in checks if failed]


def _sort_errors(sort: str, direction: str | None) -> list[FieldError]:
    errors: list[FieldError] = []
    if sort not in SORT_FIELDS:
        errors.append(FieldError("sort", f"Use one of: {', '.join(SORT_FIELDS)}."))
    if direction not in (None, "asc", "desc"):
        errors.append(FieldError("dir", "Use asc or desc."))
    return errors


def build_vault_query(  # one argument per documented query field
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    q: str | None = None,
    set_code: str | None = None,
    colors: str | None = None,
    rarity: str | None = None,
    type_text: str | None = None,
    sort: str = "added",
    direction: str | None = None,
) -> VaultQuery:
    """Check the raw parameters; raises ``ValidationFailed`` naming every offending field."""
    errors = _paging_errors(page, page_size)
    errors += _filter_errors(q, set_code, rarity, type_text)
    errors += _sort_errors(sort, direction)
    try:
        parsed_colors = parse_colors(colors)
    except ValidationFailed as error:
        errors.extend(error.errors)
        parsed_colors = ()
    if errors:
        raise ValidationFailed("The vault query is invalid.", tuple(errors))
    # Newest first, and highest value or largest first, unless the caller says otherwise.
    descending = (direction == "desc") if direction else sort in ("added", "price", "quantity")
    return VaultQuery(
        page=page,
        page_size=page_size,
        name=normalise(q) if q and normalise(q) else None,
        set_code=set_code.lower() if set_code else None,
        colors=parsed_colors,
        rarity=rarity or None,
        type_text=type_text.strip().casefold() if type_text else None,
        sort=sort,  # type: ignore[arg-type]  # validated above
        descending=descending,
    )
