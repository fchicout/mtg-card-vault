"""ADR-012: the worker slot starts, idles and stops cleanly on a signal."""

import logging
import os
import signal
import threading

import pytest

from mtgvault import worker


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/db")
    monkeypatch.setattr(worker, "configure_logging", lambda level: None)


def test_it_idles_until_it_is_asked_to_stop(caplog: pytest.LogCaptureFixture) -> None:
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    caplog.set_level(logging.INFO, logger="mtgvault.worker")
    try:
        # Signal handlers can only be installed from the main thread, so run main() here and
        # deliver SIGTERM to ourselves from a timer.
        timer = threading.Timer(0.2, lambda: os.kill(os.getpid(), signal.SIGTERM))
        timer.start()
        assert worker.main() == 0
        timer.join()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)

    messages = [record.getMessage() for record in caplog.records]
    assert any("no jobs are registered yet" in m for m in messages)
    assert "stop requested" in messages
    assert "worker stopped" in messages


def test_invalid_configuration_stops_it_before_it_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL")
    with pytest.raises(SystemExit):
        worker.main()
