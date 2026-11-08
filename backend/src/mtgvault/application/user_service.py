"""User provisioning (US-004, FR-AUTH-04)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from mtgvault.application.ports import UnitOfWork
from mtgvault.domain.identity import Principal
from mtgvault.domain.user import User

# last_login_at is rewritten at most this often: a busy client must not cause a write per request.
LOGIN_REFRESH = timedelta(hours=1)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class UserService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWork],
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock

    def ensure_user(self, principal: Principal) -> User:
        """The user for this principal: created on first sight, otherwise refreshed. Idempotent."""
        with self._unit_of_work_factory() as unit_of_work:
            user = unit_of_work.users.provision(principal, self._clock(), LOGIN_REFRESH)
            unit_of_work.commit()
        return user
