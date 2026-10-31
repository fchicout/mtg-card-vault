import json
from pathlib import Path

from mtgvault.export_openapi import build_document, main


def test_document_is_deterministic_json() -> None:
    first, second = build_document(), build_document()
    assert first == second
    assert first.endswith("\n")
    assert "/hello" in json.loads(first)["paths"]


def test_main_writes_the_file(tmp_path: Path) -> None:
    target = tmp_path / "openapi.json"
    assert main(["export", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["openapi"].startswith("3.")


def test_main_requires_exactly_one_argument() -> None:
    assert main(["export"]) == 2
