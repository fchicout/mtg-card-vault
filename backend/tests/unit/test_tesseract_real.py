"""The real Tesseract on a rendered card (needs the ``tesseract`` binary; skipped without it)."""

import io

import pytest
from PIL import Image

from mtgvault.adapters.ocr.tesseract import TesseractRecognizer, find_tesseract
from mtgvault.domain.scan import clean_title, parse_collector

pytestmark = pytest.mark.skipif(find_tesseract() is None, reason="tesseract is not installed")

# 5 x 7 dots per letter: the letters of the title below.
GLYPHS = {
    "L": ["10000"] * 6 + ["11111"],
    "I": ["11111"] + ["00100"] * 5 + ["11111"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001"] * 3 + ["11111"] + ["10001"] * 3,
    "T": ["11111"] + ["00100"] * 6,
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "O": ["01110"] + ["10001"] * 5 + ["01110"],
    " ": ["00000"] * 7,
}
TITLE = "LIGHTNING BOLT"
DOT = 4


def card_frame() -> bytes:
    """A 1280 x 960 frame: a bright card filling the guide, the title in the title band."""
    width, height = 1280, 960
    image = Image.new("L", (width, height), 40)
    card_h = int(height * 0.92)
    card_w = int(card_h * 63 / 88)
    left, top = (width - card_w) // 2, (height - card_h) // 2
    image.paste(235, (left, top, left + card_w, top + card_h))
    pixels = image.load()
    x0, y0 = left + int(card_w * 0.07), top + int(card_h * 0.055)
    for index, letter in enumerate(TITLE):
        for row, dots in enumerate(GLYPHS[letter]):
            for col, dot in enumerate(dots):
                if dot == "1":
                    for dy in range(DOT):
                        for dx in range(DOT):
                            pixels[x0 + (index * 6 + col) * DOT + dx, y0 + row * DOT + dy] = 30
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=85)
    return buffer.getvalue()


def test_the_title_of_a_rendered_card_is_read() -> None:
    command = find_tesseract()
    assert command is not None
    text = TesseractRecognizer(command).read(card_frame())
    assert clean_title(text.title) == "LIGHTNING BOLT"
    assert parse_collector(text.collector).number is None
