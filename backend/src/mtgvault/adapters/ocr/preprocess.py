"""Image preprocessing and region-of-interest extraction for card scans (FR-SCN-03).

Everything here works on in-memory images and returns new in-memory images: nothing is written
anywhere (FR-SCN-06). The card is assumed to be aligned in the on-screen guide, so the guide
rectangle of the frame is the card.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter, ImageOps

CARD_ASPECT = 63 / 88  # width / height of a Magic card
GUIDE_HEIGHT = 0.92  # the guide's height as a share of the frame's height


@dataclass(frozen=True)
class Region:
    """A rectangle as shares of the card's width and height."""

    left: float
    top: float
    right: float
    bottom: float


# Fixed regions of a modern card (title bar; collector number, rarity, set code and language).
TITLE = Region(0.06, 0.040, 0.78, 0.110)
COLLECTOR = Region(0.02, 0.925, 0.50, 0.985)


def decode(data: bytes) -> Image.Image:
    """Decode bytes (already validated by the upload checks) to an upright RGB image."""
    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        return ImageOps.exif_transpose(opened).convert("RGB")


def card_from_frame(frame: Image.Image) -> Image.Image:
    """Cut the guide rectangle (the card) out of a camera frame."""
    width, height = frame.size
    guide_h = height * GUIDE_HEIGHT
    guide_w = guide_h * CARD_ASPECT
    if guide_w > width:  # a very narrow frame: the guide is as wide as the frame
        guide_w = float(width)
        guide_h = guide_w / CARD_ASPECT
    left = (width - guide_w) / 2
    top = (height - guide_h) / 2
    return frame.crop((round(left), round(top), round(left + guide_w), round(top + guide_h)))


def crop(card: Image.Image, region: Region) -> Image.Image:
    width, height = card.size
    box = (
        round(region.left * width),
        round(region.top * height),
        round(region.right * width),
        round(region.bottom * height),
    )
    return card.crop(box)


def _otsu_threshold(gray: np.ndarray) -> int:
    histogram = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
    total = gray.size
    sum_all = float(np.dot(np.arange(256), histogram))
    best, weight_bg, sum_bg, threshold = 0.0, 0.0, 0.0, 127
    for level in range(256):
        weight_bg += histogram[level]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += level * histogram[level]
        mean_bg, mean_fg = sum_bg / weight_bg, (sum_all - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best:
            best, threshold = between, level
    return threshold


def enhance(region: Image.Image, *, target_height: int, binarize: bool) -> Image.Image:
    """Grayscale, upscale small text, normalise contrast and (optionally) threshold."""
    gray = ImageOps.grayscale(region)
    if gray.height < target_height:
        scale = target_height / gray.height
        gray = gray.resize((round(gray.width * scale), target_height), Image.Resampling.LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=2)
    gray = gray.filter(ImageFilter.MedianFilter(3))
    if not binarize:
        return gray
    array = np.asarray(gray, dtype=np.uint8)
    threshold = _otsu_threshold(array)
    binary = np.where(array > threshold, 255, 0).astype(np.uint8)
    # Text is dark on light on most cards, light on dark on some: keep dark text on a light page.
    if binary.mean() < 127:
        binary = 255 - binary
    return Image.fromarray(binary)


@dataclass(frozen=True)
class Regions:
    title: Image.Image
    collector: Image.Image


def regions_from_frame(frame: Image.Image, *, binarize: bool = False) -> Regions:
    """The two cleaned-up regions the OCR engine reads."""
    card = card_from_frame(frame)
    return Regions(
        title=enhance(crop(card, TITLE), target_height=96, binarize=binarize),
        collector=enhance(crop(card, COLLECTOR), target_height=140, binarize=binarize),
    )
