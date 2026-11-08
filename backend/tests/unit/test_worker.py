"""ADR-012, US-022: the worker schedules the price refresh, never overlaps runs, survives a failed
run and stops cleanly on a signal."""

import logging
import os
import signal
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mtgvault import worker
from mtgvault.application.price_refresh import RefreshSummary
from mtgvault.config import load_settings


class FakeRefresher:
    def __init__(self, summary: RefreshSummary | None = None, error: Exception | None = None):
        self.summary = summary or RefreshSummary(updated=1, unchanged=2, batches=1)
        self.error = error
        self.runs = 0
        self.saw_stop: list[bool] = []

    def refresh_all(self, should_stop: Callable[[], bool] = lambda: False) -> RefreshSummary:
        self.runs += 1
        if self.error:
            raise self.error
        self.saw_stop.append(should_stop())
        return self.summary


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://id.example.org")
    monkeypatch.setenv("OIDC_AUDIENCE", "mtgvault-api")
    monkeypatch.setenv("SCRYFALL_USER_AGENT", "MTGCardVault/0.3 (+https://example.org)")
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(tmp_path / "alive"))
    monkeypatch.setattr(worker, "configure_logging", lambda level: None)


@pytest.fixture
def handlers() -> Iterator[None]:
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    yield
    for sig, handler in previous.items():
        signal.signal(sig, handler)


def stop_after(seconds: float) -> threading.Timer:
    # Signal handlers can only be installed from the main thread, so main() runs here and
    # SIGTERM is delivered to ourselves from a timer.
    timer = threading.Timer(seconds, lambda: os.kill(os.getpid(), signal.SIGTERM))
    timer.start()
    return timer


def test_it_schedules_the_refresh_daily_at_four_utc_by_default() -> None:
    scheduler = worker.create_scheduler(load_settings(), lambda: None, lambda: None)
    job = scheduler.get_job(worker.JOB_ID)
    assert job is not None and job.max_instances == 1 and job.coalesce
    after = datetime(2026, 11, 8, 4, 0, 1, tzinfo=UTC)
    assert job.trigger.get_next_fire_time(None, after) == datetime(2026, 11, 9, 4, 0, tzinfo=UTC)


def test_the_schedule_is_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRICE_REFRESH_CRON", "30 2 * * 1")
    job = worker.create_scheduler(load_settings(), lambda: None, lambda: None).get_job(
        worker.JOB_ID
    )
    assert job is not None
    after = datetime(2026, 11, 8, 0, 0, tzinfo=UTC)  # a Sunday
    assert job.trigger.get_next_fire_time(None, after) == datetime(2026, 11, 9, 2, 30, tzinfo=UTC)


@pytest.mark.parametrize("bad", ["", "every day", "61 4 * * *", "0 4 * *"])
def test_an_invalid_schedule_stops_the_worker_before_it_starts(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("PRICE_REFRESH_CRON", bad)
    with pytest.raises(SystemExit):
        worker.main()


def test_it_runs_until_it_is_asked_to_stop(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    handlers: None,
) -> None:
    monkeypatch.setattr(worker, "build_refresher", lambda settings: FakeRefresher())
    caplog.set_level(logging.INFO, logger="mtgvault.worker")
    timer = stop_after(0.3)
    assert worker.main() == 0
    timer.join()
    messages = [record.getMessage() for record in caplog.records]
    assert "worker started" in messages and "stop requested" in messages
    assert "worker stopped" in messages
    assert worker.is_alive(tmp_path / "alive")


def test_a_stop_during_a_run_lets_the_run_end_and_tells_it_to_stop(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, handlers: None
) -> None:
    monkeypatch.setenv("PRICE_REFRESH_ON_START", "true")
    refresher = FakeRefresher()
    original = refresher.refresh_all

    def slow(should_stop: Callable[[], bool] = lambda: False) -> RefreshSummary:
        time.sleep(0.5)  # SIGTERM arrives while this "batch" is running
        return original(should_stop)

    refresher.refresh_all = slow  # type: ignore[method-assign]
    monkeypatch.setattr(worker, "build_refresher", lambda settings: refresher)
    caplog.set_level(logging.INFO, logger="mtgvault.worker")
    timer = stop_after(0.25)
    assert worker.main() == 0
    timer.join()
    assert refresher.runs == 1 and refresher.saw_stop == [True]
    assert "price refresh finished" in [r.getMessage() for r in caplog.records]


def test_a_crashed_run_is_logged_and_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    refresher = FakeRefresher(error=RuntimeError("boom"))
    assert worker.run_refresh(refresher, threading.Event()) is None  # type: ignore[arg-type]
    assert "price refresh crashed" in [r.getMessage() for r in caplog.records]
    healthy = FakeRefresher()
    assert worker.run_refresh(healthy, threading.Event()) is not None  # type: ignore[arg-type]


def test_the_summary_line_carries_the_counts(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="mtgvault.worker")
    worker.run_refresh(
        FakeRefresher(RefreshSummary(updated=3, failed=2, batches=2)), threading.Event()
    )  # type: ignore[arg-type]
    record = next(r for r in caplog.records if r.getMessage() == "price refresh finished")
    assert (record.updated, record.failed, record.batches) == (3, 2, 2)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("summary", "code"),
    [(RefreshSummary(updated=1), 0), (RefreshSummary(aborted=True), 1)],
)
def test_once_runs_one_refresh_and_reports_it_in_the_exit_code(
    monkeypatch: pytest.MonkeyPatch, handlers: None, summary: RefreshSummary, code: int
) -> None:
    refresher = FakeRefresher(summary)
    monkeypatch.setattr(worker, "build_refresher", lambda settings: refresher)
    assert worker.main(["--once"]) == code
    assert refresher.runs == 1


def test_the_healthcheck_reads_the_age_of_the_heartbeat(tmp_path: Path) -> None:
    beat = tmp_path / "beat"
    assert not worker.is_alive(beat)
    beat.touch()
    now = beat.stat().st_mtime
    assert worker.is_alive(beat, now + worker.HEARTBEAT_MAX_AGE_SECONDS)
    assert not worker.is_alive(beat, now + worker.HEARTBEAT_MAX_AGE_SECONDS + 1)


def test_check_alive_is_an_exit_code(tmp_path: Path) -> None:
    assert worker.main(["--check-alive"]) == 1
    (tmp_path / "alive").touch()
    assert worker.main(["--check-alive"]) == 0
