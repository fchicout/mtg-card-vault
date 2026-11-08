"""POST /api/v1/scans (US-016, US-018): validation order, limits, errors and the response."""

import io
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from tests.support.fake_cards import FakeCardProvider, make_card

from mtgvault.adapters.cache import TtlCache
from mtgvault.adapters.rate_limit import SlidingWindowRateLimiter
from mtgvault.application.ports import RecognizedText
from mtgvault.domain.errors import Unauthenticated, ValidationFailed
from mtgvault.domain.identity import Principal
from mtgvault.main import create_app

GOOD = "good-token"  # a stand-in, not a credential
AUTH = {"Authorization": f"Bearer {GOOD}"}
BOLT = make_card("Lightning Bolt", "m10", "146")


class Verifier:
    def verify(self, token: str) -> Principal:
        if token != GOOD:
            raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)
        return Principal("alice")


class Recognizer:
    def __init__(self) -> None:
        self.reads = 0

    def read(self, image: bytes) -> RecognizedText:
        self.reads += 1
        if image.startswith(b"\xff\xd8") and b"TRUNCATED" in image:
            raise ValidationFailed("The image cannot be read.")
        return RecognizedText("Lightning Bolt", "146/249 C\nM10 • EN")


class Probe:
    def is_ready(self) -> bool:
        return True


def jpeg(size: tuple[int, int] = (640, 480), quality: int = 80) -> bytes:
    buffer = io.BytesIO()
    Image.effect_noise(size, 60).convert("RGB").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


@pytest.fixture
def parts() -> tuple[TestClient, Recognizer, FakeCardProvider]:
    provider, recognizer = FakeCardProvider([BOLT, make_card("Giant Growth")]), Recognizer()
    app = create_app(
        readiness_probe=Probe(),
        token_verifier=Verifier(),
        card_provider=provider,
        cache=TtlCache(300, 50),
        text_recognizer=recognizer,
        scan_rate_limiter=SlidingWindowRateLimiter(30, 60),
    )
    return TestClient(app), recognizer, provider


def post(client: TestClient, data: bytes, **kwargs: object):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/scans", files={"image": ("frame.jpg", data, "image/jpeg")}, headers=AUTH, **kwargs
    )


def test_a_scan_needs_a_token(parts) -> None:  # type: ignore[no-untyped-def]
    client, recognizer, _ = parts
    response = client.post("/api/v1/scans", files={"image": ("f.jpg", jpeg(), "image/jpeg")})
    assert response.status_code == 401
    assert recognizer.reads == 0


def test_a_clear_capture_returns_text_and_ranked_candidates(parts) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = parts
    body = post(client, jpeg()).json()
    assert body["text"] == {"title": "Lightning Bolt", "collector": "146/249 C\nM10 • EN"}
    assert body["reason"] is None
    first = body["candidates"][0]
    assert first["card"]["name"] == "Lightning Bolt"
    assert first["exact"] is True
    assert 0.9 <= first["confidence"] <= 1.0
    assert len(body["candidates"]) <= 5


@pytest.mark.parametrize(
    ("data", "status"),
    [(b"", 415), (b"GIF89a" + b"x" * 50, 415), (b"<html></html>", 415), (b"%PDF-1.4 ...", 415)],
)
def test_other_types_never_reach_the_recogniser(parts, data: bytes, status: int) -> None:  # type: ignore[no-untyped-def]
    client, recognizer, _ = parts
    response = post(client, data)
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert recognizer.reads == 0


def test_a_file_over_two_megabytes_is_413_before_any_ocr(parts) -> None:  # type: ignore[no-untyped-def]
    client, recognizer, _ = parts
    big = jpeg((2200, 1800), 98)
    assert len(big) > 2 * 1024 * 1024, len(big)
    response = post(client, big)
    assert response.status_code == 413
    assert recognizer.reads == 0


def test_an_oversized_body_without_content_length_is_refused_while_streaming(parts) -> None:  # type: ignore[no-untyped-def]
    client, recognizer, _ = parts

    def chunks() -> Iterator[bytes]:
        for _ in range(60):
            yield b"x" * 64 * 1024  # 3.8 MB, no Content-Length (chunked)

    response = client.post(
        "/api/v1/scans",
        content=chunks(),
        headers={**AUTH, "Content-Type": "multipart/form-data; boundary=zzz"},
    )
    assert response.status_code == 413
    assert recognizer.reads == 0


def test_too_many_pixels_are_422(parts) -> None:  # type: ignore[no-untyped-def]
    client, recognizer, _ = parts
    buffer = io.BytesIO()
    Image.new("L", (4100, 100), 128).save(buffer, format="PNG")
    response = client.post(
        "/api/v1/scans", files={"image": ("f.png", buffer.getvalue(), "image/png")}, headers=AUTH
    )
    assert response.status_code == 422
    assert "4096" in response.json()["errors"][0]["message"]
    assert recognizer.reads == 0


def test_the_wrong_form_field_is_422(parts) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = parts
    response = client.post(
        "/api/v1/scans", files={"photo": ("f.jpg", jpeg(), "image/jpeg")}, headers=AUTH
    )
    assert response.status_code == 422


def test_a_damaged_frame_the_recogniser_cannot_decode_is_422(parts) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = parts
    data = jpeg() + b"TRUNCATED"
    assert post(client, data).status_code == 422


def test_the_thirty_first_scan_in_a_minute_is_429_with_a_wait(parts) -> None:  # type: ignore[no-untyped-def]
    client, recognizer, _ = parts
    data = jpeg((64, 64))
    for _ in range(30):
        assert post(client, data).status_code == 200
    refused = post(client, data)
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) >= 1
    assert recognizer.reads == 30  # the refused one was never read or recognised


def test_a_source_outage_is_a_typed_503(parts) -> None:  # type: ignore[no-untyped-def]
    client, _, provider = parts
    provider.fail = True
    response = post(client, jpeg())
    assert response.status_code == 503
    assert response.json()["type"] == "urn:mtgvault:problem:upstream-unavailable"


def test_the_response_carries_nothing_about_the_image(parts) -> None:  # type: ignore[no-untyped-def]
    client, _, _ = parts
    text = post(client, jpeg()).text
    assert "frame.jpg" not in text
