"""Worker process (ADR-012): the scheduled jobs, started as ``python -m mtgvault.worker``.

One job today: the price refresh of every owned card, at ``PRICE_REFRESH_CRON`` (UTC, default
daily 04:00). Runs never overlap, a failure is logged and the next run still happens, and a stop
signal ends the run between two batches. ``--once`` runs the refresh a single time and exits (an
operator's manual run); ``--check-alive`` is the container healthcheck.
"""

import argparse
import logging
import signal
import sys
import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import FrameType

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from mtgvault.adapters.db.unit_of_work import SqlAlchemyUnitOfWork
from mtgvault.adapters.resilience import CircuitBreaker
from mtgvault.adapters.scryfall.client import ScryfallClient
from mtgvault.adapters.scryfall.provider import ScryfallCardProvider
from mtgvault.application.price_refresh import PriceRefresher, RefreshSummary
from mtgvault.config import Settings, load_settings
from mtgvault.cron import cron_trigger
from mtgvault.logging_setup import configure_logging

logger = logging.getLogger("mtgvault.worker")
HEARTBEAT_SECONDS = 30
HEARTBEAT_MAX_AGE_SECONDS = 120
MISFIRE_GRACE_SECONDS = 3600
JOB_ID = "price-refresh"


def build_refresher(settings: Settings) -> PriceRefresher:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    sessions = sessionmaker(engine, expire_on_commit=False)
    # ONE client: request spacing and the circuit breaker are per process (FR-DAT-01).
    client = ScryfallClient(
        base_url=settings.scryfall_base_url,
        user_agent=settings.scryfall_user_agent,
        breaker=CircuitBreaker("scryfall", open_seconds=settings.scryfall_breaker_open_seconds),
    )
    return PriceRefresher(
        lambda: SqlAlchemyUnitOfWork(sessions),
        ScryfallCardProvider(client),
        lambda: datetime.now(UTC),
    )


def run_refresh(refresher: PriceRefresher, stop: threading.Event) -> RefreshSummary | None:
    """One run. Never raises: whatever happens is logged and the next run goes ahead."""
    logger.info("price refresh started")
    try:
        summary = refresher.refresh_all(should_stop=stop.is_set)
    except Exception:
        logger.exception("price refresh crashed")
        return None
    logger.info(
        "price refresh finished",
        extra={
            "updated": summary.updated,
            "unchanged": summary.unchanged,
            "not_found": summary.not_found,
            "failed": summary.failed,
            "batches": summary.batches,
            "aborted": summary.aborted,
            "stopped": stop.is_set(),
            "seconds": summary.seconds,
        },
    )
    return summary


def create_scheduler(
    settings: Settings, job: Callable[[], object], heartbeat: Callable[[], object]
) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=UTC)
    scheduler.add_job(
        job,
        cron_trigger(settings.price_refresh_cron),
        id=JOB_ID,
        max_instances=1,  # a run that outlasts its slot is never doubled
        coalesce=True,
        misfire_grace_time=MISFIRE_GRACE_SECONDS,
    )
    scheduler.add_job(heartbeat, IntervalTrigger(seconds=HEARTBEAT_SECONDS), id="heartbeat")
    return scheduler


def touch(path: Path) -> None:
    try:
        path.touch()
    except OSError:  # the healthcheck will notice; the worker keeps its job
        logger.warning("could not write the heartbeat file")


def is_alive(path: Path, now: float | None = None) -> bool:
    try:
        age = (time.time() if now is None else now) - path.stat().st_mtime
    except OSError:
        return False
    return age <= HEARTBEAT_MAX_AGE_SECONDS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mtgvault.worker", description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="refresh every owned card now, then exit"
    )
    parser.add_argument("--check-alive", action="store_true", help="healthcheck: exit 0 if alive")
    args = parser.parse_args([] if argv is None else list(argv))

    settings = load_settings()  # exits with a readable message when invalid
    heartbeat = Path(settings.worker_heartbeat_file)
    if args.check_alive:
        return 0 if is_alive(heartbeat) else 1
    configure_logging(settings.log_level)

    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("stop requested", extra={"signal": signal.Signals(signum).name})
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    refresher = build_refresher(settings)
    if args.once:
        summary = run_refresh(refresher, stop)
        return 0 if summary is not None and not summary.aborted else 1

    scheduler = create_scheduler(
        settings, lambda: run_refresh(refresher, stop), lambda: touch(heartbeat)
    )
    scheduler.start()
    touch(heartbeat)
    logger.info("worker started", extra={"price_refresh_cron": settings.price_refresh_cron})
    if settings.price_refresh_on_start:
        scheduler.add_job(lambda: run_refresh(refresher, stop), id="price-refresh-on-start")
    stop.wait()
    scheduler.shutdown(wait=True)  # a running refresh ends after its current batch
    logger.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
