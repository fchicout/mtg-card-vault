"""FR-API-02: every error path returns a valid RFC 9457 document with a correlation id."""

from typing import Annotated

import pytest
from fastapi import HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from mtgvault.api.pagination import MAX_PAGE_SIZE, PageQuery, ResultPage
from mtgvault.domain.errors import (
    Conflict,
    DomainError,
    FieldError,
    NotFound,
    RateLimited,
    UpstreamUnavailable,
    ValidationFailed,
)
from mtgvault.main import create_app


class _Ready:
    def is_ready(self) -> bool:
        return True


class _Body(BaseModel):
    quantity: int


def _app_with_error_routes() -> TestClient:
    app = create_app(readiness_probe=_Ready())

    def raiser(error: Exception):  # type: ignore[no-untyped-def]  # test helper
        def endpoint() -> None:
            raise error

        return endpoint

    routes: dict[str, Exception] = {
        "not-found": NotFound("Card not found."),
        "invalid": ValidationFailed("Bad.", (FieldError("quantity", "must be positive"),)),
        "conflict": Conflict("Already exists."),
        "limited": RateLimited("Slow down.", retry_after_seconds=7),
        "limited-no-hint": RateLimited("Slow down."),
        "upstream": UpstreamUnavailable("Scryfall is down."),
        "plain-domain": DomainError("Something else."),
        "boom": RuntimeError("secret internal detail postgresql://user:hunter2@db/x"),
        "http": HTTPException(status_code=403, detail="Forbidden here.", headers={"X-Extra": "1"}),
    }
    for name, error in routes.items():
        app.add_api_route(f"/t/{name}", raiser(error))

    @app.post("/t/body")
    def body(payload: _Body) -> _Body:
        return payload

    @app.get("/t/query")
    def query(limit: Annotated[int, Query(ge=1)]) -> int:
        return limit

    @app.get("/t/page")
    def page(params: PageQuery) -> ResultPage[int]:
        return ResultPage[int](items=[], page=params.page, page_size=params.page_size, total=0)

    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return _app_with_error_routes()


CASES = [
    ("/t/not-found", 404, "not-found"),
    ("/t/invalid", 422, "validation-failed"),
    ("/t/conflict", 409, "conflict"),
    ("/t/limited", 429, "rate-limited"),
    ("/t/limited-no-hint", 429, "rate-limited"),
    ("/t/upstream", 503, "upstream-unavailable"),
    ("/t/plain-domain", 500, "internal-error"),
    ("/t/boom", 500, "internal-error"),
    ("/t/http", 403, "forbidden"),
    ("/t/missing", 404, "not-found"),
    ("/healthz?x=1", None, None),
]


@pytest.mark.parametrize(("path", "status", "slug"), [c for c in CASES if c[1]])
def test_every_error_is_a_problem_document_with_a_correlation_id(
    client: TestClient, path: str, status: int, slug: str
) -> None:
    response = client.get(path)
    body = response.json()
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert body["type"] == f"urn:mtgvault:problem:{slug}"
    assert body["status"] == status
    assert body["title"]
    assert body["detail"]
    assert body["correlation_id"]
    assert body["correlation_id"] == response.headers["X-Request-ID"]


def test_wrong_method_is_a_problem_document(client: TestClient) -> None:
    response = client.post("/healthz")
    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["allow"] == "GET"


def test_unexpected_errors_never_leak_internals(client: TestClient) -> None:
    response = client.get("/t/boom")
    assert "hunter2" not in response.text
    assert "internal detail" not in response.text
    assert response.json()["detail"] == "An unexpected error occurred."


def test_validation_errors_list_the_offending_fields(client: TestClient) -> None:
    response = client.post("/t/body", json={"quantity": "many"})
    assert response.status_code == 422
    fields = {entry["field"] for entry in response.json()["errors"]}
    assert fields == {"quantity"}

    response = client.get("/t/query", params={"limit": 0})
    assert [e["field"] for e in response.json()["errors"]] == ["limit"]


def test_domain_validation_errors_carry_their_fields(client: TestClient) -> None:
    errors = client.get("/t/invalid").json()["errors"]
    assert errors == [{"field": "quantity", "message": "must be positive"}]


def test_rate_limit_sets_retry_after_only_when_known(client: TestClient) -> None:
    assert client.get("/t/limited").headers["Retry-After"] == "7"
    assert "Retry-After" not in client.get("/t/limited-no-hint").headers


def test_http_error_headers_are_kept(client: TestClient) -> None:
    assert client.get("/t/http").headers["X-Extra"] == "1"


def test_a_safe_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/t/not-found", headers={"X-Request-ID": "abc-123.DEF_9"})
    assert response.headers["X-Request-ID"] == "abc-123.DEF_9"
    assert response.json()["correlation_id"] == "abc-123.DEF_9"


@pytest.mark.parametrize("unsafe", ["has space", "x" * 129, "<script>", "a;b"])
def test_an_unsafe_request_id_is_replaced(client: TestClient, unsafe: str) -> None:
    response = client.get("/t/not-found", headers={"X-Request-ID": unsafe})
    assert response.headers["X-Request-ID"] != unsafe
    assert len(response.headers["X-Request-ID"]) == 32


def test_successful_responses_carry_the_correlation_header_too(client: TestClient) -> None:
    assert len(client.get("/healthz").headers["X-Request-ID"]) == 32


def test_pagination_defaults_and_limits(client: TestClient) -> None:
    assert client.get("/t/page").json() == {"items": [], "page": 1, "page_size": 50, "total": 0}
    assert client.get("/t/page", params={"page_size": MAX_PAGE_SIZE}).status_code == 200
    assert client.get("/t/page", params={"page_size": MAX_PAGE_SIZE + 1}).status_code == 422
    assert client.get("/t/page", params={"page": 0}).status_code == 422


def test_the_problem_schema_is_part_of_the_openapi_contract(client: TestClient) -> None:
    schema = client.get("/api/v1/openapi.json").json()
    assert "Problem" in schema["components"]["schemas"]
    responses = schema["paths"]["/healthz"]["get"]["responses"]
    assert "422" in responses
    assert "500" in responses
