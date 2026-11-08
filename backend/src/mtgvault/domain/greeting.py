"""Skeleton domain value (issue #1). Removed together with the /hello route (issue #15)."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Greeting:
    """A greeting message."""

    message: str

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ValueError("a greeting must not be blank")
