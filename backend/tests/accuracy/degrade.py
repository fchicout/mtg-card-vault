"""Turns a card image into a webcam-like frame (issue #113): tilt, blur, noise, glare, JPEG.

Deterministic for a given seed, so results are comparable between runs and engines. This is a
stand-in for real photographs, which add effects no simulation covers; the owner's real photos can
be added to the set (see tests/accuracy/README.md).
"""

from __future__ import annotations

import io
import random

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

FRAME = (1280, 720)
GUIDE_HEIGHT = 0.92

LEVELS = {
    # tilt degrees, shift share, scale jitter, blur radius, noise sigma, glare alpha, jpeg quality
    "good": (1.5, 0.01, 0.01, 0.6, 3, 0.0, 85),
    "normal": (3.5, 0.02, 0.025, 0.9, 6, 0.15, 75),
    "hard": (6.0, 0.035, 0.05, 1.4, 10, 0.35, 60),
}


def make_frame(card: Image.Image, seed: int, level: str) -> bytes:
    tilt, shift, scale_jitter, blur, noise, glare, quality = LEVELS[level]
    rng = random.Random(seed)
    frame_w, frame_h = FRAME
    guide_h = frame_h * GUIDE_HEIGHT
    scale = 1 + rng.uniform(-scale_jitter, scale_jitter)
    height = round(guide_h * scale)
    width = round(height * 63 / 88)
    resized = card.convert("RGB").resize((width, height), Image.Resampling.LANCZOS)
    resized = resized.rotate(
        rng.uniform(-tilt, tilt),
        resample=Image.Resampling.BICUBIC,
        expand=True,
        fillcolor=(30, 32, 36),
    )
    canvas = Image.new("RGB", FRAME, (30, 32, 36))
    dx = rng.uniform(-shift, shift) * frame_w
    dy = rng.uniform(-shift, shift) * frame_h
    canvas.paste(
        resized,
        (round((frame_w - resized.width) / 2 + dx), round((frame_h - resized.height) / 2 + dy)),
    )
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    canvas = ImageEnhance.Brightness(canvas).enhance(rng.uniform(0.8, 1.15))
    canvas = ImageEnhance.Contrast(canvas).enhance(rng.uniform(0.8, 1.1))
    array = np.asarray(canvas, dtype=np.float32)
    np_rng = np.random.default_rng(seed)
    array = array + np_rng.normal(0, noise, array.shape)
    if glare:
        yy, xx = np.mgrid[0:frame_h, 0:frame_w]
        cx, cy = rng.uniform(0.3, 0.7) * frame_w, rng.uniform(0.25, 0.75) * frame_h
        blob = np.exp(-(((xx - cx) / 160) ** 2 + ((yy - cy) / 110) ** 2))
        array = array + (255 - array) * (blob[..., None] * glare)
    out = Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))
    buffer = io.BytesIO()
    out.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()
