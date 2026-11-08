"""Builds the OCR reference set (issue #113): real card images with exact ground truth.

The ground truth (name, set, collector number) comes from Scryfall's API through the project's own
compliant client; the images come from Scryfall's image CDN. The images are NOT committed (card art
is not ours to redistribute): ``build`` downloads them into a git-ignored directory, and only the
small ``ground_truth.json`` is kept in the repository.

    uv run python -m tests.accuracy.reference_set build [--per-set 8]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

from mtgvault.adapters.scryfall.client import ScryfallClient

HERE = Path(__file__).resolve().parent
GROUND_TRUTH = HERE / "ground_truth.json"
IMAGE_DIR = HERE / "data" / "images"
USER_AGENT = "MTGCardVault-accuracy/0.5 (+https://github.com/fchicout/mtg-card-vault)"
# Modern frames, normal layout, English: the cards a collector shows to a webcam most often.
SETS = (
    "m21",
    "znr",
    "khm",
    "stx",
    "afr",
    "mid",
    "vow",
    "neo",
    "snc",
    "dmu",
    "bro",
    "one",
    "mom",
    "woe",
    "lci",
)


def _client() -> ScryfallClient:
    return ScryfallClient(base_url="https://api.scryfall.com", user_agent=USER_AGENT)


def collect(per_set: int) -> list[dict[str, str]]:
    client = _client()
    chosen: list[dict[str, str]] = []
    for code in SETS:
        query = f"set:{code} lang:en layout:normal -is:digital border:black frame:2015"
        try:
            page = client.get_json(
                "/cards/search", {"q": query, "unique": "cards", "order": "name"}
            )
        except Exception as error:  # a set without such cards is skipped
            print(f"{code}: skipped ({type(error).__name__})", file=sys.stderr)
            continue
        cards = [c for c in page["data"] if c.get("image_uris") and c.get("collector_number")]
        step = max(1, len(cards) // per_set)
        for card in cards[::step][:per_set]:
            chosen.append(
                {
                    "id": card["id"],
                    "name": card["name"],
                    "set": card["set"],
                    "number": card["collector_number"],
                    "rarity": card["rarity"],
                    "type_line": card.get("type_line", ""),
                    "image": card["image_uris"]["normal"],
                }
            )
    return chosen


def download(entries: list[dict[str, str]]) -> None:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = IMAGE_DIR / f"{entry['id']}.jpg"
        if target.exists():
            continue
        request = urllib.request.Request(entry["image"], headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:  # fixed CDN host
            target.write_bytes(response.read())
        time.sleep(0.12)  # polite spacing on the CDN as well


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build"])
    parser.add_argument("--per-set", type=int, default=8)
    args = parser.parse_args()
    entries = collect(args.per_set)
    GROUND_TRUTH.write_text(
        json.dumps([{k: v for k, v in e.items() if k != "image"} for e in entries], indent=1),
        encoding="utf-8",
    )
    download(entries)
    print(f"{len(entries)} cards, images in {IMAGE_DIR}")


if __name__ == "__main__":
    main()
