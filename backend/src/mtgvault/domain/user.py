"""A person known to the application (FR-AUTH-04). Only minimal personal data is stored."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class User:
    id: UUID
    subject: str
    display_name: str | None
    email: str | None = field(repr=False)  # personal data: never in repr/logs
    created_at: datetime
    last_login_at: datetime
