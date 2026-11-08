"""Who is calling: the identity established by a verified access token (FR-AUTH-05)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Principal:
    """The authenticated caller. ``subject`` (the token's ``sub``) is the only identity key."""

    subject: str
    # Verified claims, kept out of repr/logs on purpose (they may contain personal data).
    claims: Mapping[str, Any] = field(default_factory=dict, repr=False, compare=False)
