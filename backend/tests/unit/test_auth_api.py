"""The HTTP surface of authentication: 401/403/503 problems, public health, CORS, docs switch."""

from typing import Annotated

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from mtgvault.api import v1
from mtgvault.api.security import current_principal
from mtgvault.config import Settings
from mtgvault.domain.errors import Forbidden, Unauthenticated, UpstreamUnavailable
from mtgvault.domain.identity import Principal
from mtgvault.main import create_app


class StubProbe:
    def is_ready(self) -> bool:
        return True


GOOD, OUTAGE = "good", "down"  # stand-ins, not credentials


class StubVerifier:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def verify(self, token: str) -> Principal:
        self.seen.append(token)
        if token == GOOD:
            return Principal(subject="user-1")
        if token == OUTAGE:
            raise UpstreamUnavailable("The identity provider is currently unreachable.")
        raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)


def settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@h/db",
        "oidc_issuer_url": "https://idp.example.test",
        "oidc_audience": "mtgvault-api",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def make_client(cfg: Settings | None = None, verifier: StubVerifier | None = None) -> TestClient:
    app = create_app(cfg, readiness_probe=StubProbe(), token_verifier=verifier or StubVerifier())
    probe = APIRouter(prefix=v1.API_PREFIX, dependencies=[Depends(current_principal)])

    @probe.get("/whoami")
    def whoami(principal: Annotated[Principal, Depends(current_principal)]) -> dict[str, str]:
        return {"sub": principal.subject}

    @probe.get("/admin")
    def admin() -> None:
        raise Forbidden("You may not do this.")

    app.include_router(probe)
    return TestClient(app)


def test_missing_token_is_401_with_a_challenge_and_a_problem_document() -> None:
    response = make_client().get("/api/v1/whoami")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:mtgvault:problem:unauthenticated"
    assert body["correlation_id"]


def test_invalid_token_is_401_invalid_token_without_details() -> None:
    response = make_client().get("/api/v1/whoami", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Bearer error="invalid_token"'
    assert response.json()["detail"] == "The access token is invalid or expired."


def test_other_schemes_count_as_missing_credentials() -> None:
    verifier = StubVerifier()
    response = make_client(verifier=verifier).get(
        "/api/v1/whoami", headers={"Authorization": "Basic dXNlcjpwYXNz"}
    )
    assert response.status_code == 401
    assert verifier.seen == []


def test_valid_token_reaches_the_route_with_the_principal() -> None:
    response = make_client().get("/api/v1/whoami", headers={"Authorization": "Bearer good"})
    assert response.status_code == 200
    assert response.json() == {"sub": "user-1"}


def test_authenticated_but_forbidden_is_403() -> None:
    response = make_client().get("/api/v1/admin", headers={"Authorization": "Bearer good"})
    assert response.status_code == 403
    assert response.json()["type"] == "urn:mtgvault:problem:forbidden"


def test_identity_provider_outage_is_503_not_401() -> None:
    response = make_client().get("/api/v1/whoami", headers={"Authorization": "Bearer down"})
    assert response.status_code == 503


def test_health_endpoints_need_no_token() -> None:
    client = make_client()
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200


def test_without_settings_and_verifier_nothing_is_accepted() -> None:
    app = create_app(readiness_probe=StubProbe())
    app.include_router(APIRouter(prefix="/api/v1", dependencies=[Depends(current_principal)]))
    client = TestClient(app)
    assert client.get("/api/v1/anything", headers={"Authorization": "Bearer good"}).status_code in (
        401,
        404,
    )


def test_preflight_from_the_configured_origin_is_answered() -> None:
    client = make_client(settings(cors_origins="https://app.example"))
    response = client.options(
        "/api/v1/whoami",
        headers={
            "Origin": "https://app.example",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example"
    assert "access-control-allow-credentials" not in response.headers


def test_preflight_from_a_foreign_origin_is_refused() -> None:
    client = make_client(settings(cors_origins="https://app.example"))
    response = client.options(
        "/api/v1/whoami",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_no_cors_headers_without_configured_origins() -> None:
    response = make_client(settings()).get("/healthz", headers={"Origin": "https://app.example"})
    assert "access-control-allow-origin" not in response.headers


def test_documentation_is_off_unless_enabled() -> None:
    assert make_client(settings()).get("/api/v1/openapi.json").status_code == 404
    assert make_client(settings()).get("/api/v1/docs").status_code == 404
    assert (
        make_client(settings(api_docs_enabled=True)).get("/api/v1/openapi.json").status_code == 200
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("oidc_issuer_url", "http://idp.example"),
        ("oidc_allowed_algs", "HS256"),
        ("oidc_allowed_algs", "none"),
        ("cors_origins", "*"),
        ("cors_origins", "https://app.example/path"),
        ("cors_origins", "app.example"),
    ],
)
def test_unsafe_settings_are_refused(field: str, value: str) -> None:
    with pytest.raises(ValueError, match=r"."):
        settings(**{field: value})


def test_settings_normalise_issuer_and_origins() -> None:
    cfg = settings(
        oidc_issuer_url="https://idp.example/", cors_origins="https://a.example/, https://b.example"
    )
    assert cfg.oidc_issuer_url == "https://idp.example"
    assert cfg.cors_origin_list == ["https://a.example", "https://b.example"]
    assert cfg.oidc_algorithms == ["RS256"]
