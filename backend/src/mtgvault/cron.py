"""Standard 5-field cron expressions (UTC) for the worker's schedule.

APScheduler 3 numbers the weekdays from Monday (0), standard cron from Sunday (0 or 7). Operators
write standard cron, so the weekday field is converted to names before APScheduler sees it.
"""

import re
from datetime import UTC

from apscheduler.triggers.cron import CronTrigger

_NAMES = ("sun", "mon", "tue", "wed", "thu", "fri", "sat", "sun")  # 0..7, both 0 and 7 are Sunday
_FIELDS = 5


def _weekday_field(field: str) -> str:
    """Standard weekday numbers to names; steps are expanded because they count from Sunday."""
    return ",".join(_weekday_token(token) for token in field.split(","))


def _weekday_token(token: str) -> str:
    base, slash, step = token.partition("/")
    if slash:
        if not step.isdigit() or int(step) < 1:
            raise ValueError(f"invalid weekday step: {token!r}")
        first, last = _range(base)
        return ",".join(_NAMES[day] for day in range(first, last + 1, int(step)))
    return re.sub(r"\d+", lambda m: _NAMES[int(m.group()) % 8], base)


def _range(base: str) -> tuple[int, int]:
    if base == "*":
        return 0, 6
    low, dash, high = base.partition("-")
    if not low.isdigit() or (dash and not high.isdigit()):
        raise ValueError(f"invalid weekday range: {base!r}")
    first = int(low)
    last = int(high) if dash else 6
    if not (0 <= first <= 7 and 0 <= last <= 7 and first <= last):
        raise ValueError(f"invalid weekday range: {base!r}")
    return first, last


def cron_trigger(expression: str) -> CronTrigger:
    """A trigger for ``minute hour day month weekday``; ``ValueError`` when it is not valid."""
    fields = expression.split()
    if len(fields) != _FIELDS:
        raise ValueError("expected 5 fields: minute hour day month weekday")
    fields[4] = _weekday_field(fields[4])
    minute, hour, day, month, weekday = fields
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=weekday, timezone=UTC
    )
