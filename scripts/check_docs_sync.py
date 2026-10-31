#!/usr/bin/env python3
"""Verify that the documentation set in ``docs/`` is synchronized.

Rules are described in ``docs/README.md`` (section 2 and 5). Exit code 0 means
the set is in sync, 1 means at least one violation (all are printed).

Usage:  python3 scripts/check_docs_sync.py [docs_dir]
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

DOC_FILES = {
    "00": "README.md",
    "01": "01-project-charter.md",
    "02": "02-user-stories.md",
    "03": "03-requirements-specification.md",
    "04": "04-use-cases.md",
    "05": "05-architecture.md",
    "06": "06-traceability-matrix.md",
}

# Which document owns (defines) each ID prefix.
OWNER = {
    "BO": "01", "STK": "01", "CON": "01", "ASM": "01", "RSK": "01", "OQ": "01",
    "EP": "02", "US": "02",
    "FR": "03", "NFR": "03",
    "UC": "04",
    "ADR": "05",
}

ID_PATTERN = (
    r"(?:(?:BO|STK|CON|ASM|RSK|OQ|EP|UC)-\d{2}"
    r"|(?:US|ADR)-\d{3}"
    r"|N?FR-[A-Z]{3,4}-\d{2})"
)
ID_RE = re.compile(rf"\b{ID_PATTERN}\b")
REQ_RE = re.compile(r"\bN?FR-[A-Z]{3,4}-\d{2}\b")
US_RE = re.compile(r"\bUS-\d{3}\b")
UC_RE = re.compile(r"\bUC-\d{2}\b")
BO_RE = re.compile(r"\bBO-\d{2}\b")
ADR_RE = re.compile(r"\bADR-\d{3}\b")
VERSION_RE = re.compile(r"\*\*Docs set version:\*\*\s*(\d+\.\d+\.\d+)")
FIELD_RE = re.compile(r"^- \*\*(Epic|Priority|Release|Requirements|Use cases|Stories):\*\*\s*(.*)$")


def prefix(identifier: str) -> str:
    return identifier.split("-")[0]


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def ids_in(text: str, pattern: re.Pattern[str]) -> set[str]:
    return set(pattern.findall(text))


def invert(mapping: dict[str, set[str]]) -> dict[str, set[str]]:
    inverted: dict[str, set[str]] = defaultdict(set)
    for key, values in mapping.items():
        for value in values:
            inverted[value].add(key)
    return dict(inverted)


class Checker:
    def __init__(self, docs_dir: Path) -> None:
        self.errors: list[str] = []
        self.texts: dict[str, str] = {}
        for key, name in DOC_FILES.items():
            path = docs_dir / name
            if not path.is_file():
                self.errors.append(f"missing document: {path}")
                continue
            self.texts[key] = path.read_text(encoding="utf-8")

    def fail(self, message: str) -> None:
        self.errors.append(message)

    def compare(self, label: str, left_name: str, left: dict[str, set[str]],
                right_name: str, right: dict[str, set[str]]) -> None:
        """Report every key whose sets differ between two relations."""
        for key in sorted(set(left) | set(right)):
            a, b = left.get(key, set()), right.get(key, set())
            if a != b:
                self.fail(
                    f"{label} {key}: {left_name} has {sorted(a) or '-'} "
                    f"but {right_name} has {sorted(b) or '-'}"
                )

    # ---- parsing helpers -------------------------------------------------

    def rows(self, doc: str, id_re: re.Pattern[str]) -> dict[str, list[str]]:
        """Table rows of ``doc`` whose first cell is a single ID matching id_re."""
        found: dict[str, list[str]] = {}
        for line in self.texts.get(doc, "").splitlines():
            if not line.startswith("|"):
                continue
            cells = table_cells(line)
            if cells and id_re.fullmatch(cells[0]):
                found[cells[0]] = cells
        return found

    def blocks(self, doc: str, heading_re: re.Pattern[str]) -> dict[str, dict[str, str]]:
        """Fields (``- **Name:** value``) of each ``### ID`` block in ``doc``."""
        result: dict[str, dict[str, str]] = {}
        current: dict[str, str] | None = None
        for line in self.texts.get(doc, "").splitlines():
            heading = re.match(r"^#{2,4}\s+(\S+)", line)
            if heading:
                current = None
                if heading_re.fullmatch(heading.group(1)):
                    current = result.setdefault(heading.group(1), {})
                continue
            field = FIELD_RE.match(line)
            if field and current is not None:
                current[field.group(1)] = field.group(2)
        return result

    # ---- checks ----------------------------------------------------------

    def check_versions(self) -> None:
        versions = {}
        for key, text in self.texts.items():
            match = VERSION_RE.search(text)
            if match:
                versions[key] = match.group(1)
            else:
                self.fail(f"{DOC_FILES[key]}: missing '**Docs set version:**' line")
        if len(set(versions.values())) > 1:
            self.fail(f"docs set version differs between documents: {versions}")
        changelog = [
            tuple(int(p) for p in m.split("."))
            for m in re.findall(r"^\|\s*(\d+\.\d+\.\d+)\s*\|", self.texts.get("00", ""), re.M)
        ]
        if not changelog:
            self.fail("README.md: changelog has no version row")
        elif versions and ".".join(map(str, max(changelog))) != next(iter(versions.values())):
            self.fail("README.md: newest changelog version differs from the docs set version")

    def check_definitions(self) -> set[str]:
        """An ID is defined by a heading and/or a table row in its owner document.

        At most one heading and one table row per ID are allowed (an index table
        next to the detailed heading is fine; two headings or two rows are not).
        """
        defined: dict[tuple[str, str], int] = defaultdict(int)
        for key in sorted(set(OWNER.values())):
            for line in self.texts.get(key, "").splitlines():
                match = re.match(rf"^\|\s*({ID_PATTERN})\s*\||^#{{2,4}}\s+({ID_PATTERN})\b", line)
                if not match:
                    continue
                identifier = match.group(1) or match.group(2)
                if OWNER[prefix(identifier)] == key:
                    defined[(identifier, "row" if match.group(1) else "heading")] += 1
        for (identifier, kind), count in sorted(defined.items()):
            if count > 1:
                self.fail(f"{identifier} is defined {count} times as a {kind}")
        known = {identifier for identifier, _ in defined}
        for key, text in self.texts.items():
            for identifier in sorted(ids_in(text, ID_RE) - known):
                self.fail(f"{DOC_FILES[key]}: reference to undefined ID {identifier}")
        return known

    def check_traceability(self, known: set[str]) -> None:
        reqs = {i for i in known if REQ_RE.fullmatch(i)}
        stories = {i for i in known if US_RE.fullmatch(i)}
        use_cases = {i for i in known if UC_RE.fullmatch(i)}

        srs = self.rows("03", REQ_RE)
        matrix = self.rows("06", REQ_RE)
        srs_stories = {i: ids_in(c[3], US_RE) for i, c in srs.items() if len(c) >= 5}
        matrix_stories = {i: ids_in(c[1], US_RE) for i, c in matrix.items() if len(c) >= 5}
        matrix_ucs = {i: ids_in(c[2], UC_RE) for i, c in matrix.items() if len(c) >= 5}

        for req in sorted(reqs - set(srs)):
            self.fail(f"{req}: not found in a requirements table of 03")
        for req in sorted(reqs - set(matrix)):
            self.fail(f"{req}: missing from the traceability matrix (06 section B)")
        for req in sorted(reqs):
            if not srs_stories.get(req):
                self.fail(f"{req}: traces to no user story in 03")
            if matrix.get(req) and not (matrix[req][3] and matrix[req][4]):
                self.fail(f"{req}: matrix row needs components and tests")
        self.compare("requirement", "03", srs_stories, "06", matrix_stories)

        story_docs = self.blocks("02", US_RE)
        matrix_c = self.rows("06", US_RE)
        for story in sorted(stories - set(story_docs)):
            self.fail(f"{story}: no story block in 02")
        for story in sorted(stories - set(matrix_c)):
            self.fail(f"{story}: missing from the traceability matrix (06 section C)")

        story_reqs = {s: ids_in(f.get("Requirements", ""), REQ_RE) for s, f in story_docs.items()}
        story_ucs = {s: ids_in(f.get("Use cases", ""), UC_RE) for s, f in story_docs.items()}
        for story, linked in story_reqs.items():
            if not linked:
                self.fail(f"{story}: lists no requirements in 02")
        self.compare("story", "02", story_reqs, "03", invert(srs_stories))
        self.compare("story", "02", story_reqs, "06", invert(matrix_stories))

        matrix_c_ucs = {s: ids_in(c[4], UC_RE) for s, c in matrix_c.items() if len(c) >= 5}
        self.compare("story use cases", "02", story_ucs, "06", matrix_c_ucs)
        self.check_story_metadata(story_docs, matrix_c)

        uc_docs = self.blocks("04", UC_RE)
        for uc in sorted(use_cases - set(uc_docs)):
            self.fail(f"{uc}: no use case block in 04")
        uc_reqs = {u: ids_in(f.get("Requirements", ""), REQ_RE) for u, f in uc_docs.items()}
        uc_stories = {u: ids_in(f.get("Stories", ""), US_RE) for u, f in uc_docs.items()}
        for uc in sorted(uc_docs):
            if not uc_reqs[uc]:
                self.fail(f"{uc}: lists no requirements in 04")
        self.compare("use case requirements", "04", uc_reqs, "06", invert(matrix_ucs))
        self.compare("use case stories", "04", uc_stories, "02", invert(story_ucs))

    def check_story_metadata(self, story_docs: dict[str, dict[str, str]],
                             matrix_c: dict[str, list[str]]) -> None:
        releases = set(re.findall(r"^\|\s*M\d[^|]*\|\s*(\d+\.\d+\.\d+)\s*\|",
                                  self.texts.get("01", ""), re.M))
        for story, fields in story_docs.items():
            row = matrix_c.get(story)
            if not row or len(row) < 5:
                continue
            for field, column in (("Epic", 1), ("Release", 2), ("Priority", 3)):
                if fields.get(field, "").strip() != row[column]:
                    self.fail(f"{story}: {field} is '{fields.get(field)}' in 02 "
                              f"but '{row[column]}' in 06")
            if fields.get("Release", "").strip() not in releases:
                self.fail(f"{story}: release {fields.get('Release')} is not a milestone in 01 section 10")

    def check_objectives_and_adrs(self, known: set[str]) -> None:
        reqs = {i for i in known if REQ_RE.fullmatch(i)}
        rows_a = self.rows("06", BO_RE)
        covered: set[str] = set()
        for objective in sorted(i for i in known if BO_RE.fullmatch(i)):
            linked = ids_in(rows_a[objective][1], REQ_RE) if objective in rows_a else set()
            if not linked:
                self.fail(f"{objective}: no requirements in the matrix (06 section A)")
            covered |= linked
        for req in sorted(reqs - covered):
            self.fail(f"{req}: serves no business objective (06 section A)")
        rows_d = self.rows("06", ADR_RE)
        for adr in sorted(i for i in known if ADR_RE.fullmatch(i)):
            if adr not in rows_d or not ids_in(rows_d[adr][1], REQ_RE):
                self.fail(f"{adr}: not mapped to requirements (06 section D)")

    def run(self) -> int:
        if not self.errors:
            self.check_versions()
            known = self.check_definitions()
            self.check_traceability(known)
            self.check_objectives_and_adrs(known)
        for error in self.errors:
            print(f"ERROR: {error}")
        if self.errors:
            print(f"\n{len(self.errors)} documentation sync violation(s).")
            return 1
        print("Documentation set is in sync.")
        return 0


def main(argv: list[str]) -> int:
    default = Path(__file__).resolve().parent.parent / "docs"
    docs_dir = Path(argv[1]) if len(argv) > 1 else default
    return Checker(docs_dir).run()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
