#!/usr/bin/env python3
"""Run every quality and security gate locally, mirroring .github/workflows/ci.yml job by job.

    python3 scripts/run_local_gates.py                 # everything
    python3 scripts/run_local_gates.py --skip e2e,container-scan
    python3 scripts/run_local_gates.py --only quality-gate,docs-sync
    python3 scripts/run_local_gates.py --sonar         # also scan + judge with SonarQube

Requires uv, Node/npm and Docker (for integration tests, e2e, gitleaks and Trivy).
SonarQube never decides: scripts/quality_gate.py does (NFR-MNT-01). Exit code 1 if any gate fails.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable
GATE = [PY, "-I", str(ROOT / "scripts" / "quality_gate.py")]


@dataclass
class Result:
    name: str
    ok: bool
    seconds: float
    detail: str = ""


def run(cmd: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> tuple[bool, str]:
    completed = subprocess.run(  # noqa: S603
        cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=False)
    output = (completed.stdout + completed.stderr).strip()
    return completed.returncode == 0, output


def sequence(*commands: tuple[list[str], Path]) -> Callable[[], tuple[bool, str]]:
    def step() -> tuple[bool, str]:
        logs: list[str] = []
        for cmd, cwd in commands:
            ok, output = run(cmd, cwd)
            logs.append(f"$ {' '.join(cmd)}\n{output}")
            if not ok:
                return False, "\n".join(logs)
        return True, logs[-1]
    return step


BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
API_FILES = [BACKEND / "openapi.json", *sorted((FRONTEND / "src/app/api").rglob("*.ts"))]


def snapshot() -> dict[Path, bytes]:
    return {p: p.read_bytes() for p in API_FILES if p.is_file()}


def contract_drift() -> tuple[bool, str]:
    before = snapshot()
    ok, out = run(["uv", "run", "python", "-m", "mtgvault.export_openapi", "openapi.json"], BACKEND)
    if ok:
        ok, out = run(["npm", "run", "api:generate"], FRONTEND)
    after = {p: p.read_bytes() for p in [BACKEND / "openapi.json", *sorted((FRONTEND / "src/app/api").rglob("*.ts"))]}
    changed = sorted(str(p.relative_to(ROOT)) for p in set(before) | set(after) if before.get(p) != after.get(p))
    if not ok:
        return False, out
    return (not changed), ("contract and generated client are current" if not changed
                           else "stale, regenerate and commit: " + ", ".join(changed))


def secret_scan() -> tuple[bool, str]:
    """gitleaks over exactly the tracked files (ignored files such as deploy/.env are not scanned)."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout  # noqa: S603, S607
    with tempfile.TemporaryDirectory() as tmp:
        for name in filter(None, tracked.decode().split("\0")):
            source = ROOT / name
            if source.is_file():
                target = Path(tmp) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        return run(["docker", "run", "--rm", "-v", f"{tmp}:/repo", "ghcr.io/gitleaks/gitleaks:latest",
                    "dir", "/repo", "--redact", "--exit-code", "1", "--no-banner"])


def container_scan() -> tuple[bool, str]:
    logs = []
    for image, context in (("mtgvault-api:gates", "backend"), ("mtgvault-frontend:gates", "frontend")):
        ok, out = run(["docker", "build", "-q", "-t", image, context])
        if not ok:
            return False, out
        ok, uid = run(["docker", "run", "--rm", "--entrypoint", "id", image, "-u"])
        if not ok or uid.strip() == "0":
            return False, f"{image} must not run as root (uid {uid.strip()})"
        ok, out = run(["docker", "run", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock",
                       "aquasec/trivy:latest", "image", "--severity", "HIGH,CRITICAL", "--ignore-unfixed",
                       "--exit-code", "1", "--no-progress", image])
        logs.append(f"{image}: uid {uid.strip()}, trivy {'clean' if ok else 'FINDINGS'}")
        if not ok:
            return False, "\n".join(logs) + "\n" + out[-2000:]
    return True, "\n".join(logs)


def e2e() -> tuple[bool, str]:
    port = _free_port()
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / "e2e.env"
        env_file.write_text(f"POSTGRES_USER=mtgvault\nPOSTGRES_DB=mtgvault\n"
                            f"POSTGRES_PASSWORD={secrets.token_hex(16)}\nHTTP_PORT={port}\n")
        compose = ["docker", "compose", "-p", "mtgvault-gates", "-f", "deploy/compose.yaml", "--env-file", str(env_file)]
        try:
            ok, out = run([*compose, "up", "-d", "--build", "--wait", "--wait-timeout", "240"])
            if not ok:
                return False, out[-2500:]
            ok, out = run(["npm", "run", "e2e"], FRONTEND, {"E2E_BASE_URL": f"http://127.0.0.1:{port}"})
            return ok, out[-2500:]
        finally:
            run([*compose, "down", "-v"])


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sonar() -> tuple[bool, str]:
    """Scan both projects, then judge their issues with our own gate. Needs scan permission."""
    host, token = os.environ.get("SONAR_HOST_URL", ""), os.environ.get("SONAR_TOKEN", "")
    if not (host and token and shutil.which("sonar-scanner")):
        return False, "set SONAR_HOST_URL and SONAR_TOKEN and install sonar-scanner to use --sonar"
    logs = []
    for project, directory in (("mtg-vault-backend", BACKEND), ("mtg-vault-frontend", FRONTEND)):
        ok, out = run(["sonar-scanner", f"-Dsonar.host.url={host}"], directory, {"SONAR_TOKEN": token})
        if not ok:
            return False, out[-2000:]
        ok, out = run([*GATE, "sonar", "--project", project, "--require",
                       "--report-task", str(directory / ".scannerwork/report-task.txt")])
        logs.append(out)
        if not ok:
            return False, "\n".join(logs)
    return True, "\n".join(logs)


STEPS: dict[str, Callable[[], tuple[bool, str]]] = {
    "docs-sync": sequence(([PY, "-I", "scripts/check_docs_sync.py"], ROOT)),
    "gate-tests": sequence(([PY, "-I", "-m", "unittest", "discover", "-s", "scripts/tests"], ROOT)),
    "backend-quality": sequence(
        (["uv", "run", "ruff", "check", "."], BACKEND), (["uv", "run", "ruff", "format", "--check", "."], BACKEND),
        (["uv", "run", "mypy"], BACKEND), (["uv", "run", "lint-imports"], BACKEND)),
    "backend-tests": sequence((["uv", "run", "pytest", "--cov", "--cov-report=xml", "-q"], BACKEND)),
    "frontend-quality": sequence(
        (["npm", "run", "lint"], FRONTEND), (["npm", "run", "format:check"], FRONTEND),
        (["npm", "run", "test:coverage"], FRONTEND), (["npm", "run", "build"], FRONTEND)),
    "contract-drift": contract_drift,
    "quality-gate": sequence(([*GATE, "coverage", "--base", os.environ.get("GATE_BASE", "origin/develop")], ROOT),
                             ([*GATE, "duplication"], ROOT)),
    "secret-scan": secret_scan,
    "dependency-audit": sequence(
        (["uv", "run", "pip-audit"], BACKEND), (["npm", "audit", "--audit-level=high"], FRONTEND),
        (["npm", "audit", "--omit=dev", "--audit-level=moderate"], FRONTEND)),
    "container-scan": container_scan,
    "e2e": e2e,
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--only", default="", help="comma-separated step names")
    parser.add_argument("--skip", default="", help="comma-separated step names")
    parser.add_argument("--sonar", action="store_true", help="also scan with SonarQube and judge issues")
    args = parser.parse_args(argv)
    only = {s for s in args.only.split(",") if s}
    skip = {s for s in args.skip.split(",") if s}
    unknown = (only | skip) - set(STEPS)
    if unknown:
        print(f"unknown step(s): {', '.join(sorted(unknown))}; valid: {', '.join(STEPS)}", file=sys.stderr)
        return 2
    steps = {n: f for n, f in STEPS.items() if (not only or n in only) and n not in skip}
    if args.sonar:
        steps["sonar"] = sonar

    results: list[Result] = []
    for name, step in steps.items():
        print(f"-> {name} ...", flush=True)
        started = time.monotonic()
        ok, detail = step()
        results.append(Result(name, ok, time.monotonic() - started, detail))
        print(f"   {'PASS' if ok else 'FAIL'} ({results[-1].seconds:.0f}s)", flush=True)
        if not ok:
            print("\n".join("   | " + line for line in detail.splitlines()[-25:]), flush=True)

    print("\n== local quality gates ==")
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL':<5} {r.name:<18} {r.seconds:6.0f}s")
    failed = [r.name for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} gates passed" + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    print(json.dumps({"failed": failed}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
