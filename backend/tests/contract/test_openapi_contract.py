"""The OpenAPI document is valid and the committed copy is current (FR-API-01)."""

import json
from pathlib import Path

from openapi_spec_validator import validate

from mtgvault.export_openapi import build_document

COMMITTED = Path(__file__).resolve().parents[2] / "openapi.json"


def test_generated_document_is_a_valid_openapi_spec() -> None:
    validate(json.loads(build_document()))


def test_expected_operations_are_present() -> None:
    paths = json.loads(build_document())["paths"]
    assert set(paths) == {
        "/healthz",
        "/readyz",
        "/api/v1/me",
        "/api/v1/catalog/cards",
        "/api/v1/catalog/cards/{card_id}",
        "/api/v1/catalog/cards/{card_id}/printings",
    }
    me = paths["/api/v1/me"]["get"]
    assert me["operationId"] == "getMe"
    assert {"401", "403", "503"} <= set(me["responses"])
    assert me["security"], "the operation must declare the bearer scheme"


def test_committed_openapi_json_is_up_to_date() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == build_document(), (
        "backend/openapi.json is stale: run "
        "`uv run python -m mtgvault.export_openapi openapi.json` and commit it"
    )
