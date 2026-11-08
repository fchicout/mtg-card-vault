#!/usr/bin/env python3
"""Commit-message, branch-name and semantic-version policy (ADR-010, CON-05).

Rules (docs/05 section 7.5):
  * Conventional Commits header ``type(scope)!: subject [IDs]``, at most 100 characters before
    the ID list;
  * ``feat``/``fix`` commits reference a story or requirement ID (warning, or error with
    ``--require-ids error``);
  * pull-request branches are ``feature/*``, ``release/X.Y.Z``, ``hotfix/X.Y.Z`` (or ``develop``,
    ``main``, ``dependabot/*``); release and hotfix versions are valid SemVer and newer than the
    latest ``vX.Y.Z`` tag;
  * tags are ``vX.Y.Z`` or a SemVer pre-release such as ``v1.0.0-rc.1``.

Usage:
  check_commit_policy.py --range origin/develop..HEAD --branch feature/x
  check_commit_policy.py --message-file .git/COMMIT_EDITMSG      (commit-msg hook)
  check_commit_policy.py --tag v0.1.0

Exit code 0 = compliant (warnings allowed), 1 = violations, 2 = usage or git error.
Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_docs_sync import ID_RE  # noqa: E402  # one definition of what an ID looks like

TYPES = ("feat", "fix", "docs", "refactor", "test", "chore", "ci", "build", "perf", "revert",
         "spike", "security")
SCOPES = ("auth", "vault", "catalog", "scan", "pricing", "api", "ui", "deploy", "ci", "docs",
          "skeleton", "repo",
          # used by the project since M0
          "core", "db", "gates", "sonar", "e2e", "arch", "dev", "github", "frontend", "backend",
          "docs-sync", "release", "security", "deps", "deps-dev",
          "scryfall", "resilience")
MAX_HEADER = 100  # measured without the trailing "[US-005, FR-VLT-01]" ID list
ID_LIST_RE = re.compile(r"\s*\[[^\]]*\]\s*$")

HEADER_RE = re.compile(
    rf"^(?P<type>{'|'.join(TYPES)})(?:\((?P<scope>[a-z0-9-]+)\))?(?P<breaking>!)?: (?P<subject>\S.*)$"
)
EXEMPT_RE = re.compile(r'^(Merge |Revert "|fixup! |squash! |amend! )')
SEMVER_CORE = r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
PRERELEASE = r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
BRANCH_RE = re.compile(
    rf"^(?:develop|main|feature/[a-z0-9][a-z0-9._-]*|dependabot/.+"
    rf"|(?:release|hotfix)/(?P<version>{SEMVER_CORE}))$"
)
TAG_RE = re.compile(rf"^v{SEMVER_CORE}{PRERELEASE}$")


def check_message(message: str, require_ids: str = "warn") -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for one full commit message."""
    errors: list[str] = []
    warnings: list[str] = []
    header = message.strip().splitlines()[0] if message.strip() else ""
    if not header:
        return ["empty commit message"], []
    if EXEMPT_RE.match(header):
        return [], []
    match = HEADER_RE.match(header)
    if not match:
        return [f"not a Conventional Commit (type(scope): subject, types {', '.join(TYPES)}): {header!r}"], []
    length = len(ID_LIST_RE.sub("", header))
    if length > MAX_HEADER:
        errors.append(f"header is {length} characters (without the [IDs] list), the limit is {MAX_HEADER}: "
                      f"{header[:60]!r}...")
    if match["scope"] and match["scope"] not in SCOPES:
        errors.append(f"unknown scope '{match['scope']}' (allowed: {', '.join(SCOPES)}): {header!r}")
    if match["subject"].rstrip().endswith("."):
        errors.append(f"subject must not end with a period: {header!r}")
    if match["type"] in ("feat", "fix") and not ID_RE.search(message):
        text = f"{match['type']} commit references no story or requirement ID (e.g. [US-005, FR-VLT-01]): {header!r}"
        (errors if require_ids == "error" else warnings).append(text)
    return errors, warnings


def check_branch(branch: str, latest_tag: str | None = None) -> list[str]:
    match = BRANCH_RE.match(branch)
    if not match:
        return [f"branch '{branch}' must be feature/<name>, release/X.Y.Z, hotfix/X.Y.Z, develop or main"]
    version = match["version"]
    if version and latest_tag:
        latest = tuple(int(part) for part in latest_tag.lstrip("v").split("-")[0].split("."))
        if tuple(int(part) for part in version.split(".")) <= latest:
            return [f"branch '{branch}': version {version} is not newer than the latest tag {latest_tag}"]
    return []


def check_tag(tag: str) -> list[str]:
    if TAG_RE.match(tag):
        return []
    return [f"tag '{tag}' must be vMAJOR.MINOR.PATCH, optionally with a SemVer pre-release (v1.0.0-rc.1)"]


def git(args: list[str]) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout  # noqa: S603, S607


def commit_messages(revision_range: str) -> list[str]:
    out = git(["log", "--no-merges", "--format=%B%x01", revision_range])
    return [entry.strip() for entry in out.split("\x01") if entry.strip()]


def latest_version_tag() -> str | None:
    tags = [t for t in git(["tag", "--list", "v*"]).split() if TAG_RE.match(t) and "-" not in t]
    if not tags:
        return None
    return max(tags, key=lambda t: tuple(int(p) for p in t.lstrip("v").split(".")))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--range", dest="revision_range", metavar="REV..REV", help="commits to check")
    parser.add_argument("--message-file", type=Path, help="one commit message (commit-msg hook)")
    parser.add_argument("--branch", help="branch name of the pull request")
    parser.add_argument("--tag", help="release tag to validate")
    parser.add_argument("--require-ids", choices=("warn", "error"), default="warn")
    args = parser.parse_args(argv[1:])
    if not (args.revision_range or args.message_file or args.branch or args.tag):
        parser.error("nothing to check")

    errors: list[str] = []
    warnings: list[str] = []
    checked = 0
    try:
        messages = []
        if args.revision_range:
            messages += commit_messages(args.revision_range)
        if args.message_file:
            messages.append(args.message_file.read_text(encoding="utf-8"))
        for message in messages:
            checked += 1
            e, w = check_message(message, args.require_ids)
            errors += e
            warnings += w
        if args.branch:
            errors += check_branch(args.branch, latest_version_tag())
        if args.tag:
            errors += check_tag(args.tag)
    except (subprocess.CalledProcessError, OSError) as error:
        print(f"error: {getattr(error, 'stderr', '') or error}", file=sys.stderr)
        return 2

    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    print(f"Checked {checked} commit message(s): {len(errors)} error(s), {len(warnings)} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
