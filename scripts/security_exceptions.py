#!/usr/bin/env python3
"""Time-boxed security exceptions for the dependency, container and secret scanners.

``security/exceptions.yaml`` lists findings that are accepted for a limited time. This script
validates the file (every entry complete, not expired, at most 90 days ahead), prints the active
ids per tool for the scanners' ignore options, and runs ``npm audit`` with the exceptions applied.

  security_exceptions.py check
  security_exceptions.py ids --tool trivy
  security_exceptions.py ids --tool pip-audit --flag=--ignore-vuln   (note the '=')
  security_exceptions.py npm-audit --prefix frontend --level high [--omit dev]

Exit code 0 = fine, 1 = violation (expired/invalid exception, blocking vulnerability), 2 = usage
or tool error. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "security" / "exceptions.yaml"
TOOLS = ("trivy", "pip-audit", "npm-audit")
REQUIRED = ("id", "tool", "justification", "owner", "expires")
MAX_DAYS = 90
SEVERITY_ORDER = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
ADVISORY_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ExceptionsError(ValueError):
    """The exceptions file is not in the supported format."""


def parse(text: str) -> list[dict[str, str]]:
    """Parse the supported YAML subset: ``exceptions:`` followed by ``- key: value`` mappings."""
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    seen_root = False
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #", 1)[0].rstrip() if " #" in raw else raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not seen_root:
            if line.strip() in ("exceptions: []", "exceptions:"):
                seen_root = True
                if line.strip() == "exceptions: []":
                    return []
                continue
            raise ExceptionsError(f"line {number}: expected 'exceptions:' at the top")
        stripped = line.strip()
        if stripped.startswith("- "):
            current = {}
            entries.append(current)
            stripped = stripped[2:].strip()
        elif current is None:
            raise ExceptionsError(f"line {number}: a mapping must start with '- '")
        key, separator, value = stripped.partition(":")
        if not separator or not key.strip():
            raise ExceptionsError(f"line {number}: expected 'key: value'")
        assert current is not None  # noqa: S101  # set by the branches above
        current[key.strip()] = value.strip().strip("\"'")
    if not seen_root:
        raise ExceptionsError("the file is empty: write 'exceptions: []' when there are none")
    return entries


def validate(entries: list[dict[str, str]], today: dt.date) -> tuple[list[str], list[dict[str, str]]]:
    """Return ``(errors, active)``; expired entries are errors and never active."""
    errors: list[str] = []
    active: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(entries, 1):
        label = f"exception #{index} ({entry.get('id', '?')})"
        missing = [key for key in REQUIRED if not entry.get(key)]
        unknown = sorted(set(entry) - set(REQUIRED))
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
            continue
        if unknown:
            errors.append(f"{label}: unknown field(s) {', '.join(unknown)}")
            continue
        if entry["tool"] not in TOOLS:
            errors.append(f"{label}: tool must be one of {', '.join(TOOLS)}")
            continue
        if not ADVISORY_ID.fullmatch(entry["id"]):
            errors.append(f"{label}: id has unexpected characters")
            continue
        if len(entry["justification"]) < 20:
            errors.append(f"{label}: justification is too short to be a real reason")
            continue
        try:
            expires = dt.date.fromisoformat(entry["expires"])
        except ValueError:
            errors.append(f"{label}: expires must be YYYY-MM-DD, got '{entry['expires']}'")
            continue
        if (entry["tool"], entry["id"]) in seen:
            errors.append(f"{label}: listed twice for {entry['tool']}")
            continue
        seen.add((entry["tool"], entry["id"]))
        if expires < today:
            errors.append(f"{label}: EXPIRED on {expires} (owner {entry['owner']}): fix the finding or renew with a new date")
        elif (expires - today).days > MAX_DAYS:
            errors.append(f"{label}: expires {expires}, more than {MAX_DAYS} days away")
        else:
            active.append(entry)
    return errors, active


def active_ids(entries: list[dict[str, str]], tool: str) -> list[str]:
    return sorted(entry["id"] for entry in entries if entry["tool"] == tool)


def advisory_id(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def blocking_vulnerabilities(report: dict, level: str, excepted: set[str]) -> list[str]:
    """Names of packages in an ``npm audit --json`` report that still block at ``level``.

    A vulnerability is excused only when every advisory behind it (directly, or through the
    packages it depends on) is an active exception.
    """
    vulnerabilities = report.get("vulnerabilities", {})
    threshold = SEVERITY_ORDER[level]

    def blocked(name: str, visiting: frozenset[str]) -> bool:
        entry = vulnerabilities.get(name)
        if entry is None or name in visiting:
            return False
        via = entry.get("via", [])
        if not via:
            return True
        for item in via:
            if isinstance(item, str):
                if blocked(item, visiting | {name}):
                    return True
            elif advisory_id(item.get("url", "")) not in excepted:
                return True
        return False

    return sorted(
        name for name, entry in vulnerabilities.items()
        if SEVERITY_ORDER.get(entry.get("severity", "info"), 0) >= threshold and blocked(name, frozenset())
    )


def run_npm_audit(prefix: str, omit: str | None) -> dict:
    command = ["npm", "audit", "--json", "--prefix", prefix]
    if omit:
        command += ["--omit", omit]
    result = subprocess.run(command, capture_output=True, text=True, check=False)  # noqa: S603, S607
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"npm audit gave no JSON (exit {result.returncode}): {result.stderr.strip()[:200]}") from error
    # Fail closed: an error document or one without the vulnerability map is not a clean bill of health.
    if not isinstance(report, dict) or "error" in report or "vulnerabilities" not in report:
        detail = report.get("error", {}).get("summary", "unexpected report") if isinstance(report, dict) else "unexpected report"
        raise RuntimeError(f"npm audit did not produce a vulnerability report: {detail}")
    return report


def load(path: Path, today: dt.date) -> tuple[list[str], list[dict[str, str]]]:
    return validate(parse(path.read_text(encoding="utf-8")), today)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("command", choices=("check", "ids", "npm-audit"))
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None, help="override today (tests)")
    parser.add_argument("--tool", choices=TOOLS)
    parser.add_argument("--flag", help="print each id as '<flag> <id>' on one line (for pip-audit)")
    parser.add_argument("--prefix", default="frontend")
    parser.add_argument("--level", choices=("low", "moderate", "high", "critical"), default="high")
    parser.add_argument("--omit", choices=("dev",), default=None)
    args = parser.parse_args(argv[1:])
    today = args.today or dt.date.today()

    try:
        errors, active = load(args.file, today)
    except (ExceptionsError, OSError) as error:
        print(f"ERROR: {args.file}: {error}", file=sys.stderr)
        return 2
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1

    if args.command == "check":
        print(f"{len(active)} active security exception(s); all valid.")
        for entry in active:
            print(f"  {entry['tool']}: {entry['id']} until {entry['expires']} (owner {entry['owner']})")
        return 0

    if args.command == "ids":
        if not args.tool:
            parser.error("--tool is required")
        ids = active_ids(active, args.tool)
        print(" ".join(f"{args.flag} {i}" for i in ids) if args.flag else "\n".join(ids))
        return 0

    try:
        report = run_npm_audit(args.prefix, args.omit)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    blocking = blocking_vulnerabilities(report, args.level, set(active_ids(active, "npm-audit")))
    for name in blocking:
        entry = report["vulnerabilities"][name]
        print(f"BLOCKING: {name} ({entry.get('severity')}) fixAvailable={entry.get('fixAvailable')}")
    print(f"npm audit: {len(blocking)} blocking vulnerabilit{'y' if len(blocking) == 1 else 'ies'} at {args.level}+ "
          f"({len(active_ids(active, 'npm-audit'))} exception(s) applied).")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
