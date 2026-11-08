"""Who is calling: the identity established by a verified access token (FR-AUTH-04/05).

Only what the application needs is kept (NFR-PRV-01): the token subject, an optional display name
and an optional email address. Every other claim is dropped at the boundary.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_DISPLAY_NAME = 100
MAX_EMAIL = 254
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
# The first present, usable claim wins.
_NAME_CLAIMS = ("name", "preferred_username")


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. ``subject`` (the token's ``sub``) is the only identity key."""

    subject: str
    display_name: str | None = None
    email: str | None = field(default=None, repr=False)  # personal data: never in repr/logs


def _looks_like_email(value: str) -> bool:
    """One ``@``, no whitespace, a non-empty local part and a dotted domain (no regex: linear)."""
    local, separator, domain = value.partition("@")
    if not separator or not local or "@" in domain or any(c.isspace() for c in value):
        return False
    labels = domain.split(".")
    return len(labels) >= 2 and all(labels)


def _clean_text(value: object, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(_CONTROL.sub(" ", value).split())
    return cleaned[:limit] or None


def principal_from_claims(claims: Mapping[str, Any]) -> Principal:
    """Build the principal from verified claims. Missing or odd optional claims never fail."""
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("a verified token must carry a subject")
    display_name = next(
        (n for c in _NAME_CLAIMS if (n := _clean_text(claims.get(c), MAX_DISPLAY_NAME))), None
    )
    email = _clean_text(claims.get("email"), MAX_EMAIL)
    if email is not None and not _looks_like_email(email):
        email = None
    return Principal(
        subject=subject, display_name=display_name, email=email.lower() if email else None
    )
