"""Upload checks (FR-SCN-08): size, magic bytes, dimensions, decompression bombs."""

import io
import struct
import tracemalloc
import zlib

import pytest
from PIL import Image

from mtgvault.api.image_upload import MAX_BYTES, inspect_upload, sniff
from mtgvault.domain.errors import PayloadTooLarge, UnsupportedMediaType, ValidationFailed


def encoded(fmt: str, size: tuple[int, int] = (320, 240), **options: object) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format=fmt, **options)
    return buffer.getvalue()


def png_claiming(width: int, height: int) -> bytes:
    """A syntactically valid PNG whose header claims a huge size (and has almost no data)."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


@pytest.mark.parametrize(("fmt", "expected"), [("JPEG", "JPEG"), ("PNG", "PNG"), ("WEBP", "WEBP")])
def test_the_three_accepted_types_pass(fmt: str, expected: str) -> None:
    info = inspect_upload(encoded(fmt))
    assert (info.format, info.width, info.height) == (expected, 320, 240)


def test_the_limit_sits_exactly_at_two_megabytes() -> None:
    ok = encoded("JPEG")
    assert len(ok) < MAX_BYTES
    padded = ok + b"\0" * (MAX_BYTES - len(ok))
    assert inspect_upload(padded).format == "JPEG"  # trailing bytes are tolerated up to the cap
    with pytest.raises(PayloadTooLarge):
        inspect_upload(padded + b"\0")


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"GIF89a....",
        b"<html>not an image</html>",
        b"%PDF-1.7",
        b"MZ\x90\x00",
        b"RIFF\x00\x00\x00\x00WAVE",
    ],
    ids=["empty", "gif", "html", "pdf", "exe", "wav"],
)
def test_other_types_are_415_whatever_they_claim(data: bytes) -> None:
    with pytest.raises(UnsupportedMediaType):
        inspect_upload(data)


def test_a_renamed_file_is_judged_by_its_bytes() -> None:
    assert sniff(b"MZ\x90\x00" + b"x" * 100) is None
    assert sniff(encoded("PNG")) == "PNG"


@pytest.mark.parametrize("cut", [12, 30])
def test_damaged_images_are_422(cut: int) -> None:
    with pytest.raises(ValidationFailed) as refused:
        inspect_upload(encoded("PNG")[:cut])
    assert refused.value.errors[0].field == "image"


@pytest.mark.parametrize(("w", "h"), [(4097, 100), (100, 4097), (5000, 5000)])
def test_too_many_pixels_are_422(w: int, h: int) -> None:
    with pytest.raises(ValidationFailed) as refused:
        inspect_upload(png_claiming(w, h))
    assert "4096" in refused.value.errors[0].message


def test_the_limits_themselves_pass() -> None:
    assert inspect_upload(png_claiming(4096, 3906)).width == 4096  # 15.99 MP
    with pytest.raises(ValidationFailed):
        inspect_upload(png_claiming(4096, 4096))  # 16.8 MP


def test_a_decompression_bomb_is_refused_from_the_header_without_a_memory_spike() -> None:
    bomb = png_claiming(60_000, 60_000)  # 3.6 gigapixels claimed
    tracemalloc.start()
    with pytest.raises(ValidationFailed):
        inspect_upload(bomb)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 5 * 1024 * 1024
