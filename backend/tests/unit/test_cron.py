"""The worker's schedule follows standard cron, not APScheduler's weekday numbering."""

from datetime import UTC, datetime

import pytest

from mtgvault.cron import cron_trigger

SUNDAY = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)  # 2026-11-08 is a Sunday


def next_fire(expression: str, after: datetime = SUNDAY) -> datetime:
    fire = cron_trigger(expression).get_next_fire_time(None, after)
    assert fire is not None
    return fire


@pytest.mark.parametrize(
    ("expression", "expected_day"),
    [
        ("0 4 * * 1", 9),  # Monday
        ("0 4 * * 0", 15),  # the next Sunday
        ("0 4 * * 7", 15),
        ("0 4 * * 5", 13),  # Friday
        ("0 4 * * sat", 14),
        ("0 4 * * 1-5", 9),
        ("0 4 * * 6,0", 14),
        ("0 4 * * */2", 10),  # Sunday, Tuesday, Thursday, Saturday
        ("0 4 * * 1-5/2", 9),  # Monday, Wednesday, Friday
    ],
)
def test_weekdays_follow_standard_cron(expression: str, expected_day: int) -> None:
    after = datetime(2026, 11, 8, 4, 0, 1, tzinfo=UTC)
    assert next_fire(expression, after).day == expected_day


def test_the_default_runs_every_day_at_four() -> None:
    assert next_fire("0 4 * * *") == datetime(2026, 11, 8, 4, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad",
    ["", "0 4 * *", "0 4 * * * *", "61 4 * * *", "0 25 * * *", "x", "0 4 * * */0", "0 4 * * 5-1"],
)
def test_invalid_expressions_are_value_errors(bad: str) -> None:
    with pytest.raises(ValueError):
        cron_trigger(bad)
