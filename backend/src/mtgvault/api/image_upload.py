"""Checks of an uploaded image before anything is decoded or recognised (FR-SCN-08, NFR-SEC-07).

The type is decided by the file's magic bytes, never by the client's content type or file name; the
size comes from the header (no full decode), so a decompression bomb is refused before it can
use memory.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from mtgvault.domain.errors import (
    FieldError,
    PayloadTooLarge,
    UnsupportedMediaType,
    ValidationFailed,
)

MAX_BYTES = 2 * 1024 * 1024
MAX_SIDE = 4096
MAX_PIXELS = 16_000_000
# Guard of the decoder itself in case a header lies: Pillow refuses far beyond this.
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass(frozen=True)
class ImageInfo:
    format: str  # "JPEG", "PNG" or "WEBP"
    width: int
    height: int


def sniff(data: bytes) -> str | None:
    """The image type by magic bytes, or None when it is none of the accepted ones."""
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "WEBP"
    return None


def inspect_upload(data: bytes) -> ImageInfo:
    """Raise ``PayloadTooLarge`` (413), ``UnsupportedMediaType`` (415) or ``ValidationFailed``
    (422) unless ``data`` is an acceptable image."""
    if len(data) > MAX_BYTES:
        raise PayloadTooLarge("The image is larger than 2 MB.")
    kind = sniff(data)
    if kind is None:
        raise UnsupportedMediaType("Send a JPEG, PNG or WebP image.")
    try:
        with Image.open(io.BytesIO(data)) as image:  # reads the header only
            width, height = image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValidationFailed(
            "The image cannot be read.",
            (FieldError("image", "The file is damaged or not an image."),),
        ) from error
    if max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
        raise ValidationFailed(
            "The image is too large in pixels.",
            (FieldError("image", f"At most {MAX_SIDE} px per side and 16 megapixels."),),
        )
    return ImageInfo(kind, width, height)
