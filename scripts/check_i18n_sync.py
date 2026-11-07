#!/usr/bin/env python3
"""Compare the committed i18n messages with freshly extracted ones, ignoring source locations.

``ng extract-i18n`` records the file and line of every message, so an edit that only shifts lines
changes the file without changing a single message. This check compares the messages themselves
(id and text), which is what translators and users depend on.

  check_i18n_sync.py frontend/src/locale/messages.xlf /tmp/fresh/messages.xlf

Exit code 0 = same messages, 1 = they differ, 2 = a file is missing or not XLIFF 2.0.
Standard library only.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET  # noqa: S405  # our own build output, never untrusted input
from pathlib import Path

NS = {"x": "urn:oasis:names:tc:xliff:document:2.0"}


def _text(source: ET.Element) -> str:
    """The message text with inline placeholders kept as markup and whitespace normalised."""
    inner = (source.text or "") + "".join(ET.tostring(child, encoding="unicode") for child in source)
    return " ".join(inner.split())


def messages(path: Path) -> dict[str, str]:
    """``{message id: source text}``."""
    root = ET.parse(path).getroot()  # noqa: S314
    found: dict[str, str] = {}
    for unit in root.iter("{urn:oasis:names:tc:xliff:document:2.0}unit"):
        source = unit.find("x:segment/x:source", NS)
        if source is None:
            raise ValueError(f"unit {unit.get('id')} has no source")
        found[unit.get("id", "?")] = _text(source)
    return found


def differences(committed: dict[str, str], fresh: dict[str, str]) -> list[str]:
    problems = [f"missing from the committed file: {key}" for key in sorted(set(fresh) - set(committed))]
    problems += [f"no longer used (still committed): {key}" for key in sorted(set(committed) - set(fresh))]
    problems += [f"text changed: {key}" for key in sorted(set(committed) & set(fresh)) if committed[key] != fresh[key]]
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: check_i18n_sync.py <committed.xlf> <fresh.xlf>", file=sys.stderr)
        return 2
    try:
        problems = differences(messages(Path(argv[1])), messages(Path(argv[2])))
    except (OSError, ET.ParseError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    for problem in problems:
        print(f"ERROR: {problem}")
    if problems:
        print(f"{len(problems)} i18n message difference(s): run 'npm run i18n:extract' in frontend/ and commit.")
        return 1
    print("i18n messages are current.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
