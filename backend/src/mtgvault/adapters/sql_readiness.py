"""PostgreSQL :class:`ReadinessProbe` (FR-OPS-01)."""

import logging

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class SqlReadinessProbe:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.warning("readiness probe: database unreachable", exc_info=True)
            return False
        return True
