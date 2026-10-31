#!/usr/bin/env python3
"""Project-owned quality gate (NFR-MNT-01). SonarQube's own gate is never consulted.

The conditions and thresholds live here, in version control, and are evaluated identically on a
developer machine and in GitHub Actions. SonarQube is only an *issue source* for what cannot be
computed locally; it never decides pass or fail.

Sub-commands
  coverage     coverage of NEW code (lines added vs a base ref) for the back end and the front end
  duplication  duplicated-lines percentage, computed locally with jscpd
  sonar        open bugs, vulnerabilities and blocker/critical issues read from SonarQube
               (plus hotspots and maintainability rating when the token may read them)

Exit code: 0 all evaluated conditions pass, 1 at least one fails, 2 usage or input error.
Standard library only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET  # noqa: S405  # reads only our own coverage reports
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# ---- thresholds (docs/03 NFR-MNT-01) -----------------------------------------------------------
MIN_NEW_CODE_COVERAGE = 80.0
MAX_DUPLICATION = 3.0
MAX_RATING = 1  # 1 = A, 2 = B, ... (SonarQube rating scale)

PASS, FAIL, SKIPPED = "PASS", "FAIL", "SKIPPED"
Lines = dict[str, dict[int, int]]  # repo-relative path -> {line number: hits}


@dataclass(frozen=True)
class Condition:
    name: str
    status: str
    actual: str
    threshold: str
    detail: str = ""


# ---- diff and coverage parsing -----------------------------------------------------------------
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def parse_added_lines(diff: str) -> dict[str, set[int]]:
    """Added line numbers per file from ``git diff -U0`` output."""
    added: dict[str, set[int]] = {}
    current: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:]
            current = None if target == "/dev/null" else target.removeprefix("b/")
        elif current and (hunk := _HUNK.match(line)):
            start, count = int(hunk.group(1)), int(hunk.group(2) or "1")
            added.setdefault(current, set()).update(range(start, start + count))
    return added


def parse_cobertura(xml_text: str, prefix: str) -> Lines:
    """coverage.xml (relative filenames): ``<source>`` + ``filename`` -> path under ``prefix``."""
    root = ET.fromstring(xml_text)  # noqa: S314
    sources = [s.text or "" for s in root.iter("source")] or [""]
    base = sources[0].strip("/")
    result: Lines = {}
    for cls in root.iter("class"):
        path = "/".join(p for p in (prefix, base, cls.get("filename", "")) if p)
        lines = result.setdefault(path, {})
        for line in cls.iter("line"):
            lines[int(line.get("number", "0"))] = int(line.get("hits", "0"))
    return result


def parse_lcov(text: str, prefix: str) -> Lines:
    result: Lines = {}
    current: dict[int, int] | None = None
    for raw in text.splitlines():
        if raw.startswith("SF:"):
            path = raw[3:].strip().removeprefix("./")
            current = result.setdefault("/".join(p for p in (prefix, path) if p), {})
        elif raw.startswith("DA:") and current is not None:
            number, hits, *_ = raw[3:].split(",")
            current[int(number)] = int(hits)
        elif raw == "end_of_record":
            current = None
    return result


def new_code_coverage(added: dict[str, set[int]], coverage: Lines) -> tuple[int, int]:
    """(covered, total) executable lines among the lines added in the diff."""
    covered = total = 0
    for path, hits_by_line in coverage.items():
        for line in added.get(path, set()) & hits_by_line.keys():
            total += 1
            covered += hits_by_line[line] > 0
    return covered, total


def coverage_condition(label: str, covered: int, total: int, minimum: float) -> Condition:
    threshold = f">= {minimum:g}%"
    if total == 0:
        return Condition(f"{label} coverage on new code", PASS, "n/a", threshold,
                         "no executable lines were added")
    percent = 100.0 * covered / total
    status = PASS if percent >= minimum else FAIL
    return Condition(f"{label} coverage on new code", status, f"{percent:.1f}%", threshold,
                     f"{covered}/{total} new executable lines covered")


# ---- git ----------------------------------------------------------------------------------------
def run_git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout  # noqa: S603, S607


def added_lines_since(base: str | None) -> dict[str, set[int]]:
    """Lines added vs ``base`` (working tree included). Untracked files count as fully new.

    Without a usable base every line is treated as new code (the strictest reading).
    """
    untracked = [p for p in run_git("ls-files", "--others", "--exclude-standard").splitlines() if p]
    tracked = [p for p in run_git("ls-files").splitlines() if p]
    everything = {p: _line_numbers(p) for p in tracked + untracked}
    if not base:
        return everything
    try:
        diff = run_git("diff", "-U0", "--no-color", "--no-ext-diff", base, "--")
    except subprocess.CalledProcessError:
        print(f"warning: base ref '{base}' not found: treating all code as new", file=sys.stderr)
        return everything
    added = parse_added_lines(diff)
    for path in untracked:
        added[path] = _line_numbers(path)
    return added


def _line_numbers(path: str) -> set[int]:
    try:
        with open(path, "rb") as handle:
            return set(range(1, sum(1 for _ in handle) + 1))
    except OSError:
        return set()


# ---- SonarQube as an issue source ---------------------------------------------------------------
# A read-only token can always search issues; measures and hotspots need extra permissions. The
# gate therefore derives its verdict from issue counts and treats whatever it cannot read as
# SKIPPED (visible, never silently passed).
HttpGet = Callable[[str, str], tuple[int, dict]]


def sonar_get(url: str, token: str) -> tuple[int, dict]:
    auth = base64.b64encode(f"{token}:".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read() or b"{}")
        except ValueError:
            return error.code, {}


def wait_for_analysis(report_task: Path, token: str, get: HttpGet, timeout: int = 300,
                      sleep: Callable[[float], None] = time.sleep) -> None:
    """Block until SonarQube finished processing the report written by the scanner."""
    props = dict(line.split("=", 1) for line in report_task.read_text().splitlines() if "=" in line)
    url = props["ceTaskUrl"]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = get(url, token)
        state = body.get("task", {}).get("status")
        if status == 200 and state == "SUCCESS":
            return
        if state in {"FAILED", "CANCELED"}:
            raise RuntimeError(f"SonarQube analysis {state}: {body['task'].get('errorMessage', '')}")
        sleep(3)
    raise TimeoutError("SonarQube did not finish processing the analysis in time")


@dataclass(frozen=True)
class IssueCounts:
    bugs: int
    vulnerabilities: int
    blocker_or_critical: int


def fetch_issue_counts(host: str, key: str, token: str, get: HttpGet) -> IssueCounts:
    query = urllib.parse.urlencode({"componentKeys": key, "resolved": "false", "ps": "1",
                                    "facets": "types,severities"})
    status, body = get(f"{host}/api/issues/search?{query}", token)
    if status != 200:
        raise RuntimeError(f"issue search failed for {key}: HTTP {status} {body.get('errors', '')}")
    facets = {f["property"]: {v["val"]: int(v["count"]) for v in f["values"]}
              for f in body.get("facets", [])}
    types, severities = facets.get("types", {}), facets.get("severities", {})
    return IssueCounts(bugs=types.get("BUG", 0), vulnerabilities=types.get("VULNERABILITY", 0),
                       blocker_or_critical=severities.get("BLOCKER", 0) + severities.get("CRITICAL", 0))


def fetch_optional_number(url: str, token: str, get: HttpGet, extract: Callable[[dict], float | None]) -> float | None:
    """A number SonarQube only reveals to tokens with extra permissions: None when not readable."""
    status, body = get(url, token)
    return extract(body) if status == 200 else None


def fetch_server_gate_status(host: str, key: str, token: str, get: HttpGet) -> str | None:
    """SonarQube's own gate status. Shown for information; it never influences the verdict."""
    query = urllib.parse.urlencode({"projectKey": key})
    status, body = get(f"{host}/api/qualitygates/project_status?{query}", token)
    return str(body["projectStatus"]["status"]) if status == 200 else None


def sonar_conditions(counts: IssueCounts, hotspots_to_review: float | None,
                     maintainability_rating: float | None) -> list[Condition]:
    def at_most_zero(name: str, value: int, detail: str) -> Condition:
        return Condition(name, PASS if value == 0 else FAIL, str(value), "0", detail)

    if hotspots_to_review is None:
        hotspots = Condition("Security hotspots to review", SKIPPED, "n/a", "0", "token cannot read hotspots")
    else:
        hotspots = Condition("Security hotspots to review", PASS if hotspots_to_review == 0 else FAIL,
                             f"{hotspots_to_review:.0f}", "0", "equivalent to 100% reviewed")
    if maintainability_rating is None:
        maintainability = Condition("Maintainability rating", SKIPPED, "n/a", "A", "token cannot read measures")
    else:
        value = int(maintainability_rating)
        maintainability = Condition("Maintainability rating", PASS if value <= MAX_RATING else FAIL,
                                    "ABCDE"[value - 1] if 1 <= value <= 5 else str(value), "A")
    return [
        at_most_zero("Open bugs (reliability rating A)", counts.bugs, "any open bug lowers the rating"),
        at_most_zero("Open vulnerabilities (security rating A)", counts.vulnerabilities,
                     "any open vulnerability lowers the rating"),
        at_most_zero("Open Blocker/Critical issues", counts.blocker_or_critical, ""),
        maintainability,
        hotspots,
    ]


# ---- duplication, computed locally ---------------------------------------------------------------
def measure_duplication(paths: list[str], jscpd: Path) -> float:
    """Duplicated-lines percentage across ``paths`` using jscpd (no server involved)."""
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(  # noqa: S603
            [str(jscpd), *paths, "--reporters", "json", "--output", out, "--min-lines", "6",
             "--min-tokens", "60", "--ignore", "**/api/**,**/*.spec.ts,**/node_modules/**,**/.venv/**",
             "--silent"], check=True, capture_output=True, text=True)
        report = json.loads((Path(out) / "jscpd-report.json").read_text(encoding="utf-8"))
    return float(report["statistics"]["total"]["percentage"])


def duplication_condition(percentage: float) -> Condition:
    return Condition("Duplicated lines", PASS if percentage <= MAX_DUPLICATION else FAIL,
                     f"{percentage:.1f}%", f"<= {MAX_DUPLICATION:.0f}%")


# ---- reporting ----------------------------------------------------------------------------------
def render(title: str, conditions: list[Condition]) -> str:
    rows = [f"{c.status:<8} {c.name:<36} {c.actual:>8}  (required {c.threshold})"
            + (f"  - {c.detail}" if c.detail else "") for c in conditions]
    return "\n".join([f"== {title} ==", *rows])


def verdict(conditions: list[Condition]) -> int:
    return 1 if any(c.status == FAIL for c in conditions) else 0


# ---- CLI ----------------------------------------------------------------------------------------
def cmd_coverage(args: argparse.Namespace) -> int:
    added = added_lines_since(args.base)
    conditions: list[Condition] = []
    for label, path, prefix, parser in (
        ("Back end", args.backend, "backend", parse_cobertura),
        ("Front end", args.frontend, "frontend", parse_lcov),
    ):
        report = Path(path)
        if not report.is_file():
            print(f"error: coverage report not found: {report}", file=sys.stderr)
            return 2
        covered, total = new_code_coverage(added, parser(report.read_text(encoding="utf-8"), prefix))
        conditions.append(coverage_condition(label, covered, total, args.min_coverage))
    print(render(f"Quality gate - coverage (base: {args.base or 'all code is new'})", conditions))
    return verdict(conditions)


def cmd_duplication(args: argparse.Namespace) -> int:
    jscpd = Path(args.jscpd)
    if not jscpd.is_file():
        print(f"error: jscpd not found at {jscpd} (run `npm ci` in frontend/)", file=sys.stderr)
        return 2
    condition = duplication_condition(measure_duplication(args.paths, jscpd))
    print(render("Quality gate - duplication (computed locally)", [condition]))
    return verdict([condition])


def cmd_sonar(args: argparse.Namespace) -> int:
    token = os.environ.get(args.token_env, "")
    host = (args.host or os.environ.get("SONAR_HOST_URL", "")).rstrip("/")
    if not token or not host:
        print(f"SKIPPED: SonarQube not configured ({args.token_env} / SONAR_HOST_URL)")
        return 2 if args.require else 0
    key = urllib.parse.quote(args.project)
    try:
        if args.report_task:
            wait_for_analysis(Path(args.report_task), token, sonar_get)
        counts = fetch_issue_counts(host, args.project, token, sonar_get)
    except (RuntimeError, TimeoutError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    hotspots = fetch_optional_number(
        f"{host}/api/hotspots/search?project={key}&status=TO_REVIEW&ps=1", token, sonar_get,
        lambda body: float(body["paging"]["total"]))
    maintainability = fetch_optional_number(
        f"{host}/api/measures/component?component={key}&metricKeys=sqale_rating", token, sonar_get,
        lambda body: next((float(m["value"]) for m in body["component"]["measures"]), None))
    conditions = sonar_conditions(counts, hotspots, maintainability)
    print(render(f"Quality gate - SonarQube issues for {args.project} (judged by this script)", conditions))
    server = fetch_server_gate_status(host, args.project, token, sonar_get)
    print("INFO     SonarQube's own gate: "
          + (f"{server} (informational only, never used for the verdict)" if server
             else "not readable with this token (never used for the verdict)"))
    return verdict(conditions)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    cov = sub.add_parser("coverage", help="coverage of new code")
    cov.add_argument("--base", default="origin/develop", help="base ref (empty: all code is new)")
    cov.add_argument("--backend", default="backend/coverage.xml")
    cov.add_argument("--frontend", default="frontend/coverage/frontend/lcov.info")
    cov.add_argument("--min-coverage", type=float, default=MIN_NEW_CODE_COVERAGE)
    cov.set_defaults(run=cmd_coverage)
    dup = sub.add_parser("duplication", help="duplicated lines, computed locally with jscpd")
    dup.add_argument("--jscpd", default="frontend/node_modules/.bin/jscpd")
    dup.add_argument("paths", nargs="*", default=["backend/src", "frontend/src"])
    dup.set_defaults(run=cmd_duplication)
    son = sub.add_parser("sonar", help="issue counts read from SonarQube, judged here")
    son.add_argument("--project", required=True, help="SonarQube project key")
    son.add_argument("--host", help="defaults to $SONAR_HOST_URL")
    son.add_argument("--token-env", default="SONAR_TOKEN")
    son.add_argument("--report-task", help="path to .scannerwork/report-task.txt to wait on")
    son.add_argument("--require", action="store_true", help="fail (exit 2) when SonarQube is not configured")
    son.set_defaults(run=cmd_sonar)
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
