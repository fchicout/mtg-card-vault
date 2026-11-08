"""Preprocessing and regions of interest (FR-SCN-03), on synthetic cards (no card art involved)."""

import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

from mtgvault.adapters.ocr.preprocess import (
    CARD_ASPECT,
    COLLECTOR,
    TITLE,
    card_from_frame,
    crop,
    decode,
    enhance,
    regions_from_frame,
)


def synthetic_frame(width: int = 1280, height: int = 720) -> Image.Image:
    """A dark frame with a light 'card' in the guide, black text bands where the real ones are."""
    frame = Image.new("RGB", (width, height), (30, 30, 30))
    guide_h = height * 0.92
    guide_w = guide_h * CARD_ASPECT
    left, top = (width - guide_w) / 2, (height - guide_h) / 2
    draw = ImageDraw.Draw(frame)
    draw.rectangle((left, top, left + guide_w, top + guide_h), fill=(235, 230, 215))
    for band, shade in ((TITLE, 0), (COLLECTOR, 0)):
        x0 = left + band.left * guide_w
        y0 = top + (band.top + 0.012) * guide_h
        x1 = left + (band.left + 0.4) * guide_w
        y1 = top + (band.bottom - 0.012) * guide_h
        draw.rectangle((x0, y0, x1, y1), fill=(shade, shade, shade))
    return frame


def test_the_guide_rectangle_is_the_card() -> None:
    card = card_from_frame(synthetic_frame())
    assert card.size[1] == pytest.approx(720 * 0.92, abs=2)
    assert card.size[0] / card.size[1] == pytest.approx(CARD_ASPECT, abs=0.01)
    assert np.asarray(card).mean() > 200  # the light card, not the dark background


def test_a_narrow_frame_still_gets_a_card_shaped_guide() -> None:
    card = card_from_frame(Image.new("RGB", (300, 720), "white"))
    assert card.size[0] <= 300
    assert card.size[0] / card.size[1] == pytest.approx(CARD_ASPECT, abs=0.02)


def test_regions_are_cut_where_the_text_is() -> None:
    card = card_from_frame(synthetic_frame())
    for region in (TITLE, COLLECTOR):
        part = np.asarray(crop(card, region).convert("L"), dtype=float)
        assert part.mean() < 175  # a substantial dark text band lies inside the crop
        assert part.min() < 20  # ... and the crop contains actual dark ink


def test_enhanced_regions_are_upscaled_grayscale_with_full_contrast() -> None:
    regions = regions_from_frame(synthetic_frame())
    assert regions.title.mode == "L"
    assert regions.title.height >= 96
    assert regions.collector.height >= 140
    values = np.asarray(regions.title)
    assert values.min() <= 5
    assert values.max() >= 250


def test_binarising_keeps_dark_text_on_a_light_page_whatever_the_card_polarity() -> None:
    dark_page = Image.new("L", (200, 40), 20)
    ImageDraw.Draw(dark_page).text((10, 10), "ABC", fill=230)
    for source in (dark_page, Image.eval(dark_page, lambda v: 255 - v)):
        result = np.asarray(enhance(source.convert("RGB"), target_height=80, binarize=True))
        assert set(np.unique(result)) <= {0, 255}
        assert result.mean() > 127  # mostly light page, dark ink


def test_processing_is_deterministic_and_leaves_the_input_untouched() -> None:
    frame = synthetic_frame()
    before = np.asarray(frame).copy()
    first = regions_from_frame(frame, binarize=True)
    second = regions_from_frame(frame, binarize=True)
    assert np.array_equal(np.asarray(first.title), np.asarray(second.title))
    assert np.array_equal(np.asarray(frame), before)


def test_decode_fixes_orientation_and_returns_rgb() -> None:
    image = Image.new("RGB", (40, 20), "red")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotated 90 degrees
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    decoded = decode(buffer.getvalue())
    assert decoded.mode == "RGB"
    assert decoded.size == (20, 40)


def test_nothing_is_written_to_disk(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.chdir(tmp_path)
    regions_from_frame(synthetic_frame(), binarize=True)
    assert list(tmp_path.iterdir()) == []
