"""PostgreSQL user repository: one atomic upsert keyed by the token subject (ADR-005)."""

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from mtgvault.adapters.db.models import UserRow
from mtgvault.domain.identity import Principal
from mtgvault.domain.user import User


def _to_user(row: UserRow) -> User:
    return User(
        id=row.id,
        subject=row.sub,
        display_name=row.display_name,
        email=row.email,
        created_at=row.created_at,
        last_login_at=row.last_login_at,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def provision(self, principal: Principal, now: datetime, refresh_after: timedelta) -> User:
        base = insert(UserRow).values(
            id=uuid4(),
            sub=principal.subject,
            display_name=principal.display_name,
            email=principal.email,
            last_login_at=now,
        )
        new_name = func.coalesce(base.excluded.display_name, UserRow.display_name)
        new_email = func.coalesce(base.excluded.email, UserRow.email)
        statement = base.on_conflict_do_update(
            index_elements=[UserRow.sub],
            set_={
                "display_name": new_name,
                "email": new_email,
                "last_login_at": base.excluded.last_login_at,
            },
            # Nothing is written (and no row lock is taken for long) when nothing changed.
            where=or_(
                UserRow.last_login_at < now - refresh_after,
                UserRow.display_name.is_distinct_from(new_name),
                UserRow.email.is_distinct_from(new_email),
            ),
        ).returning(UserRow)
        row = self._session.execute(statement).scalar_one_or_none()
        if row is None:  # the conflict branch decided there was nothing to update
            row = self._session.execute(
                select(UserRow).where(UserRow.sub == principal.subject)
            ).scalar_one()
        return _to_user(row)
