"""US-004 at API level with an in-memory repository (the PostgreSQL race is in integration)."""

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from mtgvault.application.user_service import LOGIN_REFRESH, UserService
from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal
from mtgvault.domain.user import User
from mtgvault.main import create_app

T0 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
GOOD = "good"  # a stand-in value, not a credential


class MemoryUsers:
    def __init__(self) -> None:
        self.by_subject: dict[str, User] = {}
        self.provisioned = 0

    def provision(self, principal: Principal, now: datetime, refresh_after: timedelta) -> User:
        self.provisioned += 1
        known = self.by_subject.get(principal.subject)
        if known is None:
            known = User(
                uuid4(), principal.subject, principal.display_name, principal.email, now, now
            )
        elif now - known.last_login_at >= refresh_after:
            known = User(
                known.id, known.subject, known.display_name, known.email, known.created_at, now
            )
        self.by_subject[principal.subject] = known
        return known


class MemoryUnitOfWork:
    def __init__(self, users: MemoryUsers) -> None:
        self.users = users
        self.committed = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        return None


class Verifier:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    def verify(self, token: str) -> Principal:
        if token != GOOD:
            raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)
        return self.principal


class Probe:
    def is_ready(self) -> bool:
        return True


def build(principal: Principal, users: MemoryUsers) -> TestClient:
    app = create_app(
        readiness_probe=Probe(),
        token_verifier=Verifier(principal),
        unit_of_work_factory=lambda: MemoryUnitOfWork(users),
    )
    return TestClient(app)


AUTH = {"Authorization": f"Bearer {GOOD}"}


def test_me_requires_a_token() -> None:
    assert build(Principal("s"), MemoryUsers()).get("/api/v1/me").status_code == 401


def test_first_call_provisions_and_returns_only_the_profile() -> None:
    users = MemoryUsers()
    response = build(Principal("s1", "Ada", "ada@example.org"), users).get(
        "/api/v1/me", headers=AUTH
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id", "display_name", "email"}
    assert (body["display_name"], body["email"]) == ("Ada", "ada@example.org")
    UUID(body["id"])
    assert len(users.by_subject) == 1


def test_repeated_calls_return_the_same_user() -> None:
    users = MemoryUsers()
    client = build(Principal("s1", "Ada", None), users)
    first = client.get("/api/v1/me", headers=AUTH).json()
    second = client.get("/api/v1/me", headers=AUTH).json()
    assert first == second
    assert len(users.by_subject) == 1


def test_a_token_without_name_or_email_still_works() -> None:
    body = build(Principal("s2"), MemoryUsers()).get("/api/v1/me", headers=AUTH).json()
    assert body["display_name"] is None
    assert body["email"] is None


def test_the_service_commits_and_uses_the_refresh_window() -> None:
    users = MemoryUsers()
    uows: list[MemoryUnitOfWork] = []

    def factory() -> MemoryUnitOfWork:
        uows.append(MemoryUnitOfWork(users))
        return uows[-1]

    now = [T0]
    service = UserService(factory, clock=lambda: now[0])
    first = service.ensure_user(Principal("s3", "Ada"))
    now[0] = T0 + LOGIN_REFRESH + timedelta(seconds=1)
    later = service.ensure_user(Principal("s3", "Ada"))
    assert later.id == first.id
    assert later.last_login_at > first.last_login_at
    assert [u.committed for u in uows] == [1, 1]
