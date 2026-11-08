"""Worker process (ADR-012): the slot for scheduled jobs, started as ``python -m mtgvault.worker``.

Until the price refresh job exists (issue BL-44) there is nothing to schedule, so the worker only
starts cleanly, logs that it is idle and waits for a stop signal. Having the process, its
configuration and its container in place now means adding a job later changes no deployment.
"""

import logging
import signal
import sys
import threading
from types import FrameType

from mtgvault.config import load_settings
from mtgvault.logging_setup import configure_logging

logger = logging.getLogger("mtgvault.worker")


def main() -> int:
    settings = load_settings()
    configure_logging(settings.log_level)

    stop = threading.Event()

    def request_stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("stop requested", extra={"signal": signal.Signals(signum).name})
        stop.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logger.info("worker started: no jobs are registered yet (price refresh arrives with BL-44)")
    stop.wait()
    logger.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
