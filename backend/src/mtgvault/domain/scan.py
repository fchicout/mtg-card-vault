"""Reading card text from OCR output (FR-SCN-03, FR-SCN-04): pure functions, no I/O.

OCR text is noisy. These functions only return what they can trust: an unreadable title is
``None`` (never a guess) and a collector number or set code is returned only when its shape fits.
"""

import re
import unicodedata
from dataclasses import dataclass

MIN_TITLE_LETTERS = 3
MAX_TITLE_LENGTH = 60
_LANGUAGES = ("EN", "DE", "FR", "IT", "ES", "PT", "JA", "KO", "RU", "ZH", "PH")
_ALLOWED_IN_TITLE = re.compile(r"[^\w\s',\-:!.]", re.UNICODE)
_LIGATURES = {"æ": "ae", "Æ": "Ae", "œ": "oe", "Œ": "Oe", "ß": "ss"}
_DIGIT_LOOKALIKES = str.maketrans({"O": "0", "o": "0", "D": "0", "I": "1", "l": "1", "|": "1",
                                   "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2"})  # fmt: skip


@dataclass(frozen=True)
class CollectorInfo:
    """What the bottom-left band of a card says."""

    number: str | None = None  # collector number without leading zeros, e.g. "97"
    total: str | None = None  # the "/274" part when present
    set_code: str | None = None  # lower-case, e.g. "m21"


def clean_title(raw: str) -> str | None:
    """A plausible card title from OCR text of the title bar, or None when it is unreadable."""
    text = unicodedata.normalize("NFKC", raw)
    for ligature, plain in _LIGATURES.items():
        text = text.replace(ligature, plain)
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = _ALLOWED_IN_TITLE.sub(" ", text)
    words = [w for w in text.split() if len(w) > 1 or w.isalpha() or w in ("'",)]
    # A trailing run of digits and single characters is the mana cost misread as text.
    while words and (words[-1].isdigit() or len(words[-1]) == 1):
        words.pop()
    title = " ".join(words).strip(" -:,.'")
    letters = sum(c.isalpha() for c in title)
    visible = sum(not c.isspace() for c in title)
    if letters < MIN_TITLE_LETTERS or not title or len(title) > MAX_TITLE_LENGTH:
        return None
    if letters / max(visible, 1) < 0.7:
        return None
    return title


def _digits(token: str) -> str | None:
    """Digits of a token that is mostly digits, with look-alike letters corrected."""
    cleaned = token.strip(".,;:·•*")
    if not cleaned:
        return None
    mapped = cleaned.translate(_DIGIT_LOOKALIKES)
    if not mapped.isdigit():
        return None
    real = sum(c.isdigit() for c in cleaned)
    return mapped if real >= len(cleaned) / 2 else None


def parse_collector(raw: str) -> CollectorInfo:
    """Collector number, total and set code from the text of the bottom-left band."""
    text = unicodedata.normalize("NFKC", raw).replace("\n", " ")
    number = total = None
    slash = re.search(r"([0-9OoIl|SBZD]{1,5})\s*/\s*([0-9OoIl|SBZD]{2,5})", text)
    if slash:
        number, total = _digits(slash.group(1)), _digits(slash.group(2))
    if number is None:
        for token in text.split():
            found = _digits(token)
            if found and 3 <= len(found) <= 4:
                number = found
                break
    set_code = _set_code(text)
    return CollectorInfo(
        number=number.lstrip("0") or "0" if number else None,
        total=total.lstrip("0") if total else None,
        set_code=set_code,
    )


def _set_code(text: str) -> str | None:
    tokens = re.split(r"[\s•·*]+", text)
    for index, token in enumerate(tokens):
        if not re.fullmatch(r"[A-Z][A-Z0-9]{2,4}", token) or token.isdigit():
            continue
        following = tokens[index + 1 : index + 3]
        if any(t in _LANGUAGES for t in following) or (index + 1 < len(tokens) and "•" in text):
            return token.lower()
    return None
