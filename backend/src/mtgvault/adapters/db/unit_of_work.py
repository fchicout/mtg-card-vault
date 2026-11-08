"""SQLAlchemy :class:`UnitOfWork`: one session and one transaction per use (ADR-005, ADR-006).

Leaving the ``with`` block without :meth:`commit` rolls everything back, so a failed use case can
never leave half-written data behind. Repositories (added with the features) take ``session``.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from mtgvault.adapters.db.user_repository import SqlAlchemyUserRepository
from mtgvault.application.ports import UserRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self.session
        try:
            session.rollback()  # no-op after commit(); undoes everything otherwise
        finally:
            session.close()
            self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("The unit of work is not active: use it in a 'with' block")
        return self._session

    @property
    def users(self) -> UserRepository:
        return SqlAlchemyUserRepository(self.session)

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
