import pytest
from fastapi.testclient import TestClient

from mtgvault.main import create_app


class StubProbe:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    def is_ready(self) -> bool:
        return self._ready


def client(ready: bool = True) -> TestClient:
    return TestClient(create_app(readiness_probe=StubProbe(ready)))


def test_hello_returns_the_greeting() -> None:
    response = client().get("/hello")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, MTG Vault!"}


def test_liveness_is_ok() -> None:
    response = client(ready=False).get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_ok_when_dependencies_are_up() -> None:
    response = client(ready=True).get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_503_when_dependencies_are_down() -> None:
    response = client(ready=False).get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}


def test_openapi_is_served_under_the_versioned_prefix() -> None:
    response = client().get("/api/v1/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "MTG Card Vault API"


def test_unknown_route_is_404() -> None:
    assert client().get("/nope").status_code == 404


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="database_url"):
        create_app()


def test_database_url_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:1/db")
    assert create_app().title == "MTG Card Vault API"
