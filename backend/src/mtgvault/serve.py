"""Container entry point: migrate the database, then serve (FR-OPS-03).

The API never accepts traffic against an outdated schema: if a migration fails the process exits
non-zero before the HTTP server starts, and the container is restarted by its supervisor.
"""

import logging
import sys

import uvicorn

from mtgvault.adapters.db.migrate import upgrade_to_head
from mtgvault.config import load_settings
from mtgvault.logging_setup import configure_logging

logger = logging.getLogger("mtgvault.serve")


def main() -> int:
    settings = load_settings()
    configure_logging(settings.log_level)
    logger.info("applying database migrations")
    try:
        upgrade_to_head(settings.database_url)
    except Exception:
        logger.exception("migrations failed: refusing to serve")
        return 1
    logger.info("migrations applied: starting the API")
    uvicorn.run(
        "mtgvault.main:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104  # inside the container; the proxy is the only way in
        port=8000,
        log_config=None,  # keep our JSON handler
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
