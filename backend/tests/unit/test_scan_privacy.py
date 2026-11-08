"""CON-12 proven mechanically (FR-SCN-06, ADR-008): a scanned image is never written, stored or
logged. A sentinel travels inside the image; the tests look everywhere it could have gone."""

import base64
import io
import logging
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.adapters.cache import TtlCache
from mtgvault.adapters.rate_limit import SlidingWindowRateLimiter
from mtgvault.application.ports import RecognizedText, UnitOfWork
from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal
from mtgvault.main import create_app

SENTINEL = b"SENTINEL-8f3a91-DO-NOT-PERSIST"
GOOD = "good-token"  # a stand-in, not a credential


class Verifier:
    def verify(self, token: str) -> Principal:
        if token != GOOD:
            raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)
        return Principal("alice")


class Recognizer:
    def __init__(self) -> None:
        self.seen: list[bytes] = []

    def read(self, image: bytes) -> RecognizedText:
        self.seen.append(image)
        return RecognizedText("Lightning Bolt", "146/249 C")


class Probe:
    def is_ready(self) -> bool:
        return True


def _no_database() -> UnitOfWork:
    raise AssertionError("a scan must not use the database")


def image_with_sentinel(size: tuple[int, int], quality: int) -> bytes:
    buffer = io.BytesIO()
    Image.effect_noise(size, 80).convert("RGB").save(
        buffer, format="JPEG", quality=quality, comment=SENTINEL
    )
    return buffer.getvalue()


@pytest.fixture
def client() -> Iterator[tuple[TestClient, Recognizer]]:
    recognizer = Recognizer()
    app = create_app(
        readiness_probe=Probe(),
        token_verifier=Verifier(),
        card_provider=FakeCardProvider([make_card("Lightning Bolt", "m10", "146")]),
        cache=TtlCache(300, 10),
        text_recognizer=recognizer,
        scan_rate_limiter=SlidingWindowRateLimiter(30, 60),
        unit_of_work_factory=_no_database,
    )
    yield TestClient(app), recognizer


def scan(client: TestClient, data: bytes) -> int:
    return client.post(
        "/api/v1/scans",
        files={"image": ("secret-name.jpg", data, "image/jpeg")},
        headers={"Authorization": f"Bearer {GOOD}"},
    ).status_code


def tree(root: Path) -> set[str]:
    return {str(p) for p in root.rglob("*")}


@pytest.mark.parametrize(
    ("size", "quality"), [((320, 240), 80), ((1500, 1150), 95)], ids=["small", "above-1MB"]
)
def test_no_file_is_written_for_a_scan(
    client,
    tmp_path,
    monkeypatch,
    size,
    quality,  # type: ignore[no-untyped-def]
) -> None:
    web, recognizer = client
    data = image_with_sentinel(size, quality)
    if size[0] > 1000:
        assert 1024 * 1024 < len(data) < 2 * 1024 * 1024  # would spool to disk by default
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    rollovers: list[int] = []
    original = tempfile.SpooledTemporaryFile.rollover

    def watched(self) -> None:  # type: ignore[no-untyped-def]
        rollovers.append(1)  # a spooled upload moving from memory to a real file
        original(self)

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", watched)
    before = tree(tmp_path)
    assert scan(web, data) == 200
    assert recognizer.seen == [data]
    assert rollovers == []  # the upload never left memory (it is deleted afterwards, so look now)
    assert tree(tmp_path) == before == set()
    assert not any(SENTINEL in p.read_bytes() for p in tmp_path.rglob("*") if p.is_file())


def test_no_log_line_contains_the_image_its_name_or_its_base64(client, caplog) -> None:  # type: ignore[no-untyped-def]
    web, _ = client
    data = image_with_sentinel((320, 240), 80)
    with caplog.at_level(logging.DEBUG):
        assert scan(web, data) == 200
        assert scan(web, b"not an image") == 415
    logged = caplog.text.encode()
    for needle in (
        SENTINEL,
        base64.b64encode(SENTINEL),
        b"secret-name",
        base64.b64encode(data[:60]),
    ):
        assert needle not in logged


def test_the_database_is_never_touched_and_nothing_is_cached(client) -> None:  # type: ignore[no-untyped-def]
    web, _ = client
    assert scan(web, image_with_sentinel((320, 240), 80)) == 200  # _no_database would raise
    cache_values = repr(vars(web.app.state.catalog_cache)).encode()  # type: ignore[attr-defined]
    assert SENTINEL not in cache_values


def test_a_rejected_upload_leaves_no_trace_either(client, tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    web, recognizer = client
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    assert scan(web, SENTINEL * 100) == 415
    assert recognizer.seen == []
    assert os.listdir(tmp_path) == []
