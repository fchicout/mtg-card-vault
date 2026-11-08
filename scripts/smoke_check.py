#!/usr/bin/env python3
"""Post-deploy smoke check of a running environment (issue #54, NFR-SEC-06, FR-OPS-01/02).

  smoke_check.py https://staging.mtg.fchicout.dev
  smoke_check.py https://localhost:8443 --insecure       (local CA not trusted yet)
  smoke_check.py http://127.0.0.1:8080 --allow-http      (no TLS in front: skips the HTTPS-only checks)

Checks, in order: plain HTTP redirects to HTTPS, ``/healthz`` and ``/readyz`` answer 200, the
security headers of NFR-SEC-06 are present on the front page (CSP without ``unsafe-inline`` for
scripts and with ``frame-ancestors`` or ``X-Frame-Options``, ``X-Content-Type-Options``,
``Referrer-Policy``, ``Permissions-Policy`` with the camera for self only), HSTS is sent over HTTPS
and no ``Server``/``X-Powered-By`` header reveals a version.

Exit code 0 = every check passed, 1 = at least one failed, 2 = the URL is unusable.
Standard library only.
"""

from __future__ import annotations

import argparse
import http.client
import re
import ssl
import sys
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

TIMEOUT = 10


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    detail: str


Fetch = Callable[[str, str, str], tuple[int, dict[str, str]]]
"""``fetch(scheme_and_authority, method, path) -> (status, lower-cased headers)``."""


def make_fetch(insecure: bool) -> Fetch:
    context = ssl.create_default_context()
    if insecure:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    def fetch(origin: str, method: str, path: str) -> tuple[int, dict[str, str]]:
        parts = urlsplit(origin)
        host, port = parts.hostname or "", parts.port
        if parts.scheme == "https":
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                host, port, timeout=TIMEOUT, context=context
            )
        else:
            conn = http.client.HTTPConnection(host, port, timeout=TIMEOUT)
        try:
            conn.request(method, path, headers={"User-Agent": "mtg-vault-smoke-check"})
            response = conn.getresponse()
            response.read()
            return response.status, {k.lower(): v for k, v in response.getheaders()}
        finally:
            conn.close()

    return fetch


def _http_origin(base: str) -> str | None:
    """The plain-HTTP origin to probe for the redirect; None when the port is not derivable."""
    parts = urlsplit(base)
    if parts.scheme != "https":
        return None
    if parts.port in (None, 443):
        return f"http://{parts.hostname}"
    return None  # a non-standard HTTPS port has no fixed HTTP sibling (compose uses 8080/8443)


def check_redirect(fetch: Fetch, base: str, http_origin: str | None) -> Result:
    name = "HTTP redirects to HTTPS"
    origin = http_origin or _http_origin(base)
    if origin is None:
        return Result(name, True, "skipped (pass --http-origin to check a non-standard port)")
    status, headers = fetch(origin, "GET", "/")
    location = headers.get("location", "")
    ok = status in (301, 302, 307, 308) and location.startswith("https://")
    return Result(name, ok, f"{status} {location}".strip())


def check_status(fetch: Fetch, base: str, path: str) -> Result:
    status, _ = fetch(base, "GET", path)
    return Result(f"GET {path} answers 200", status == 200, str(status))


def _csp_ok(csp: str) -> tuple[bool, str]:
    directives = {d.split()[0]: d.split()[1:] for d in csp.split(";") if d.strip()}
    script = directives.get("script-src", directives.get("default-src", []))
    if "'unsafe-inline'" in script and not any(s.startswith("'nonce-") for s in script):
        return False, "script-src allows unsafe-inline"
    if "'unsafe-eval'" in script:
        return False, "script-src allows unsafe-eval"
    return True, "ok"


def check_headers(headers: dict[str, str], https: bool) -> list[Result]:
    results: list[Result] = []
    csp = headers.get("content-security-policy", "")
    ok, why = _csp_ok(csp) if csp else (False, "missing")
    results.append(Result("Content-Security-Policy", ok, why))
    framed = "frame-ancestors" in csp or headers.get("x-frame-options", "").upper() in ("DENY", "SAMEORIGIN")
    results.append(Result("framing is refused", framed, headers.get("x-frame-options", "via CSP" if framed else "missing")))
    results.append(
        Result(
            "X-Content-Type-Options: nosniff",
            headers.get("x-content-type-options", "").lower() == "nosniff",
            headers.get("x-content-type-options", "missing"),
        )
    )
    results.append(Result("Referrer-Policy", bool(headers.get("referrer-policy")), headers.get("referrer-policy", "missing")))
    pp = headers.get("permissions-policy", "")
    camera = re.search(r"camera=\(([^)]*)\)", pp)
    camera_ok = bool(camera) and camera.group(1).strip() in ("self", '"self"')
    results.append(Result("Permissions-Policy: camera for self only", camera_ok, pp or "missing"))
    if https:
        results.append(
            Result("Strict-Transport-Security", bool(headers.get("strict-transport-security")), headers.get("strict-transport-security", "missing"))
        )
    leaked = [h for h in ("server", "x-powered-by") if re.search(r"\d+\.\d+", headers.get(h, ""))]
    results.append(Result("no version in Server / X-Powered-By", not leaked, ", ".join(f"{h}: {headers[h]}" for h in leaked) or "ok"))
    return results


def run(fetch: Fetch, base: str, http_origin: str | None = None, allow_http: bool = False) -> list[Result]:
    https = base.startswith("https://")
    results: list[Result] = []
    if https:
        results.append(check_redirect(fetch, base, http_origin))
    elif not allow_http:
        results.append(Result("served over HTTPS", False, "use an https:// URL (or --allow-http for a local stack)"))
    results.append(check_status(fetch, base, "/healthz"))
    results.append(check_status(fetch, base, "/readyz"))
    _, headers = fetch(base, "GET", "/")
    results.extend(check_headers(headers, https))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="base URL of the environment")
    parser.add_argument("--insecure", action="store_true", help="do not verify the TLS certificate")
    parser.add_argument("--allow-http", action="store_true", help="accept a plain-HTTP base URL")
    parser.add_argument("--http-origin", help="plain-HTTP origin to probe for the redirect")
    args = parser.parse_args(argv)
    parts = urlsplit(args.url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        print(f"unusable URL: {args.url}", file=sys.stderr)
        return 2
    base = f"{parts.scheme}://{parts.netloc}"
    try:
        results = run(make_fetch(args.insecure), base, args.http_origin, args.allow_http)
    except (OSError, http.client.HTTPException) as error:
        print(f"FAIL     {base} is not reachable: {error}")
        return 1
    for r in results:
        print(f"{'ok      ' if r.ok else 'FAIL    '} {r.name} - {r.detail}")
    failed = [r for r in results if not r.ok]
    print(f"{len(results) - len(failed)}/{len(results)} checks passed for {base}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
