"""Accuracy and latency harness for OCR engines (issue #113, BO-02).

    uv run python -m tests.accuracy.harness --engine tesseract [--levels good normal hard]

Reads tests/accuracy/ground_truth.json and the downloaded images (see reference_set.py), renders
each card as a webcam-like frame at three difficulty levels, runs the pipeline and reports:

* title top-1 / top-3: the true card name among the best 1 / 3 distinct matches of the OCR title
  against the name list of ALL Scryfall cards (so the lookup is as hard as in production);
* collector number exact match;
* OCR latency per card (title + collector regions).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
import unicodedata
from collections.abc import Callable
from typing import Any

from PIL import Image
from rapidfuzz import fuzz, process
from tests.accuracy.degrade import LEVELS, make_frame
from tests.accuracy.reference_set import GROUND_TRUTH, IMAGE_DIR

from mtgvault.adapters.ocr.preprocess import Regions, decode, regions_from_frame

NAMES_FILE = IMAGE_DIR.parent / "card_names.json"
Recognizer = Callable[[Regions], tuple[str, str]]


def normalise(text: str) -> str:
    plain = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", "", plain.casefold()).strip()


def load_names() -> list[str]:
    if not NAMES_FILE.exists():
        from tests.accuracy.reference_set import _client

        document = _client().get_json("/catalog/card-names")
        NAMES_FILE.write_text(json.dumps(document["data"]), encoding="utf-8")
    return json.loads(NAMES_FILE.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------- engines
def tesseract_engine() -> Recognizer:
    import pytesseract

    def read(regions: Regions) -> tuple[str, str]:
        title = pytesseract.image_to_string(regions.title, config="--psm 7 --oem 1")
        collector = pytesseract.image_to_string(
            regions.collector,
            config="--psm 6 --oem 1 -c tessedit_char_whitelist=0123456789/ABCDEFGHIJKLMNOPQRSTUVWXYZ•·-",
        )
        return title, collector

    return read


def rapidocr_engine() -> Recognizer:
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()

    def text(image: Image.Image) -> str:
        result, _ = engine(np.asarray(image.convert("RGB")))
        return " ".join(item[1] for item in (result or []))

    return lambda regions: (text(regions.title), text(regions.collector))


def easyocr_engine() -> Recognizer:
    import easyocr
    import numpy as np

    reader = easyocr.Reader(["en"], gpu=False, verbose=False)

    def text(image: Image.Image) -> str:
        return " ".join(reader.readtext(np.asarray(image.convert("RGB")), detail=0))

    return lambda regions: (text(regions.title), text(regions.collector))


ENGINES: dict[str, Callable[[], Recognizer]] = {
    "tesseract": tesseract_engine,
    "rapidocr": rapidocr_engine,
    "easyocr": easyocr_engine,
}


# ---------------------------------------------------------------------------- scoring
def top_names(title: str, names: list[str], normalised: list[str], limit: int = 3) -> list[str]:
    query = normalise(title)
    if not query:
        return []
    found = process.extract(query, normalised, scorer=fuzz.ratio, limit=limit * 3)
    picked: list[str] = []
    for _, _, index in found:
        base = names[index].split(" // ")[0]
        if base not in picked:
            picked.append(base)
        if len(picked) == limit:
            break
    return picked


NUMBER = re.compile(r"(\d{1,4})\s*/\s*\d{2,4}|\b(\d{3,4})\b")


def collector_number(text: str) -> str | None:
    match = NUMBER.search(text.replace("O", "0").replace("o", "0"))
    if not match:
        return None
    return (match.group(1) or match.group(2)).lstrip("0") or "0"


def run(engine_name: str, levels: list[str], limit: int | None, binarize: bool) -> dict[str, Any]:
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))[:limit]
    names = load_names()
    normalised = [normalise(n.split(" // ")[0]) for n in names]
    recognise = ENGINES[engine_name]()
    recognise(regions_from_frame(Image.new("RGB", (400, 300), "white")))  # warm up (model load)
    report: dict[str, Any] = {"engine": engine_name, "binarize": binarize, "cards": len(truth)}
    for level in levels:
        top1 = top3 = number_hits = 0
        timings: list[float] = []
        for index, card in enumerate(truth):
            image = Image.open(IMAGE_DIR / f"{card['id']}.jpg")
            frame = decode(make_frame(image, seed=index, level=level))
            started = time.perf_counter()
            title, collector = recognise(regions_from_frame(frame, binarize=binarize))
            timings.append(time.perf_counter() - started)
            best = top_names(title, names, normalised)
            top1 += bool(best) and best[0] == card["name"].split(" // ")[0]
            top3 += card["name"].split(" // ")[0] in best
            number_hits += collector_number(collector) == card["number"].lstrip("0")
        timings.sort()
        report[level] = {
            "top1": round(top1 / len(truth), 3),
            "top3": round(top3 / len(truth), 3),
            "number": round(number_hits / len(truth), 3),
            "p50_ms": round(statistics.median(timings) * 1000),
            "p90_ms": round(timings[int(len(timings) * 0.9) - 1] * 1000),
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=sorted(ENGINES), required=True)
    parser.add_argument("--levels", nargs="+", default=list(LEVELS), choices=list(LEVELS))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--binarize", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.engine, args.levels, args.limit, args.binarize)))


if __name__ == "__main__":
    main()
