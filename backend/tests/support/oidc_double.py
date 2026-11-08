"""A deterministic OIDC provider for tests (issue #59). Never shipped in an image.

Implements just what the application uses: discovery, JWKS, authorization endpoint with PKCE
(S256) and automatic login, token endpoint (authorization_code, refresh_token with rotation),
revocation and a logout redirect. Browsers may call it cross-origin (CORS is answered).

Runs in-process for pytest (``OidcDouble().start()``) or standalone for the compose stack::

    python tests/support/oidc_double.py --port 9000 --issuer http://localhost:9000

Behaviour is steered through ``POST /__control`` (JSON), e.g. ``{"access_ttl": 3}``,
``{"token_status": 500}`` (every token request fails), ``{"revoke_all": true}``,
``{"reset": true}``.
``login_hint=<sub>`` on the authorize request picks the user; ``login_hint=deny`` cancels the login.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

USERS: dict[str, dict[str, str]] = {
    "user-1": {"name": "Ada Lovelace", "email": "ada@example.org"},
    "user-2": {"name": "Grace Hopper", "email": "grace@example.org"},
    "user-3": {"name": "", "email": ""},  # a token without name or email
}
KID = "double-key-1"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class OidcDouble:
    def __init__(
        self,
        issuer: str = "",
        *,
        audience: str = "mtgvault-api",
        client_id: str = "mtgvault-test",
        redirect_uris: tuple[str, ...] = (),
        port: int = 0,
        host: str = "127.0.0.1",
    ) -> None:
        self.audience, self.client_id, self.redirect_uris = audience, client_id, redirect_uris
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer((host, port), _make_handler(self))
        self.port = self._server.server_address[1]
        self.issuer = (issuer or f"http://127.0.0.1:{self.port}").rstrip("/")
        self.reset()

    # ------------------------------------------------------------------ control
    def reset(self) -> None:
        with self._lock:
            self.access_ttl, self.refresh_ttl, self.token_status = 600, 3600, 0
            self.codes: dict[str, dict[str, Any]] = {}
            self.refresh_tokens: dict[str, dict[str, Any]] = {}
            self.token_requests = 0
            self.revoked: list[str] = []

    def control(self, change: dict[str, Any]) -> None:
        with self._lock:
            for name in ("access_ttl", "refresh_ttl", "token_status"):
                if name in change:
                    setattr(self, name, int(change[name]))
            if change.get("revoke_all"):
                self.refresh_tokens.clear()
        if change.get("reset"):
            self.reset()

    def start(self) -> OidcDouble:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # ------------------------------------------------------------------ tokens
    def jwks(self) -> dict[str, Any]:
        public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self._key.public_key()))
        return {"keys": [{**public, "kid": KID, "use": "sig", "alg": "RS256"}]}

    def access_token(self, sub: str, *, audience: str | None = None, ttl: int | None = None) -> str:
        now = int(time.time())
        user = USERS.get(sub, {})
        claims: dict[str, Any] = {
            "iss": self.issuer, "aud": audience or self.audience, "sub": sub,
            "iat": now, "exp": now + (self.access_ttl if ttl is None else ttl),
            "scope": "openid profile email offline_access",
        }  # fmt: skip
        if user.get("name"):
            claims["name"] = user["name"]
        if user.get("email"):
            claims["email"] = user["email"]
        return jwt.encode(claims, self._key, algorithm="RS256", headers={"kid": KID})

    def _issue(self, sub: str, audience: str, *, with_refresh: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "access_token": self.access_token(sub, audience=audience),
            "token_type": "bearer",
            "expires_in": self.access_ttl,
            "scope": "openid profile email offline_access",
        }
        if with_refresh:
            refresh = secrets.token_urlsafe(32)
            self.refresh_tokens[refresh] = {
                "sub": sub,
                "aud": audience,
                "exp": time.time() + self.refresh_ttl,
            }
            body["refresh_token"] = refresh
        return body

    # ------------------------------------------------------------------ endpoints
    def discovery(self) -> dict[str, Any]:
        return {
            "issuer": self.issuer,
            "jwks_uri": f"{self.issuer}/jwks.json",
            "authorization_endpoint": f"{self.issuer}/authorize",
            "token_endpoint": f"{self.issuer}/token",
            "revocation_endpoint": f"{self.issuer}/revoke",
            "code_challenge_methods_supported": ["S256"],
            "response_types_supported": ["code"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "subject_types_supported": ["public"],
        }

    @staticmethod
    def _error_redirect(redirect: str, error: str, state: str) -> tuple[int, dict[str, str], None]:
        return 302, {"Location": f"{redirect}?{urlencode({'error': error, 'state': state})}"}, None

    def authorize(self, query: dict[str, str]) -> tuple[int, dict[str, str], dict[str, Any] | None]:
        redirect = query.get("redirect_uri", "")
        if query.get("client_id") != self.client_id or (
            self.redirect_uris and redirect not in self.redirect_uris
        ):
            return 400, {}, {"error": "invalid_request"}
        state = query.get("state", "")
        if query.get("code_challenge_method") != "S256" or not query.get("code_challenge"):
            return self._error_redirect(redirect, "invalid_request", state)
        hint = query.get("login_hint", "user-1")
        if hint == "deny":
            return self._error_redirect(redirect, "access_denied", state)
        audience = query.get("audience", self.audience)
        if audience != self.audience:
            return self._error_redirect(redirect, "invalid_target", state)
        code = secrets.token_urlsafe(24)
        with self._lock:
            self.codes[code] = {
                "sub": hint,
                "challenge": query["code_challenge"],
                "redirect": redirect,
                "aud": audience,
            }
        return 302, {"Location": f"{redirect}?{urlencode({'code': code, 'state': state})}"}, None

    def token(self, form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        with self._lock:
            self.token_requests += 1
            if self.token_status:
                return self.token_status, {"error": "server_error"}
            grant = form.get("grant_type")
            if grant == "authorization_code":
                entry = self.codes.pop(form.get("code", ""), None)
                verifier = form.get("code_verifier", "")
                ok = (
                    entry is not None
                    and entry["redirect"] == form.get("redirect_uri")
                    and (_b64(hashlib.sha256(verifier.encode()).digest()) == entry["challenge"])
                )
                if not ok or entry is None:
                    return 400, {"error": "invalid_grant"}
                return 200, self._issue(entry["sub"], entry["aud"])
            if grant == "refresh_token":
                entry = self.refresh_tokens.pop(form.get("refresh_token", ""), None)  # rotation
                if entry is None or entry["exp"] < time.time():
                    return 400, {"error": "invalid_grant"}
                return 200, self._issue(entry["sub"], entry["aud"])
            return 400, {"error": "unsupported_grant_type"}

    def revoke(self, form: dict[str, str]) -> None:
        with self._lock:
            token = form.get("token", "")
            self.refresh_tokens.pop(token, None)
            self.revoked.append(token)


def _make_handler(provider: OidcDouble) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "oidc-double"
        sys_version = ""

        def _send(
            self,
            status: int,
            body: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "content-type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            payload = json.dumps(body).encode() if body is not None else b""
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).decode()
            if "json" in (self.headers.get("Content-Type") or ""):
                return {k: str(v) for k, v in json.loads(raw or "{}").items()}
            return {k: v[0] for k, v in parse_qs(raw).items()}

        def do_OPTIONS(self) -> None:
            self._send(204)

        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            if parts.path == "/.well-known/openid-configuration":
                self._send(200, provider.discovery())
            elif parts.path == "/jwks.json":
                self._send(200, provider.jwks())
            elif parts.path == "/authorize":
                status, headers, body = provider.authorize(query)
                self._send(status, body, headers)
            elif parts.path == "/logout":
                self._send(302, None, {"Location": query.get("rd", "/")})
            else:
                self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path == "/token":
                status, body = provider.token(self._form())
                self._send(status, body, {"Cache-Control": "no-store"})
            elif path == "/revoke":
                provider.revoke(self._form())
                self._send(200, {})
            elif path == "/__control":
                provider.control(self._form())
                self._send(200, {"ok": True})
            else:
                self._send(404, {"error": "not_found"})

        def log_message(self, *_: object) -> None:
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="OIDC test double")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104  # inside a test container
    parser.add_argument("--issuer", required=True)
    parser.add_argument("--audience", default="mtgvault-api")
    parser.add_argument("--client-id", default="mtgvault-test")
    parser.add_argument("--redirect-uri", action="append", default=[])
    args = parser.parse_args()
    double = OidcDouble(
        args.issuer, audience=args.audience, client_id=args.client_id,
        redirect_uris=tuple(args.redirect_uri), port=args.port, host=args.host,
    )  # fmt: skip
    print(f"OIDC double for {double.issuer} on port {double.port}", flush=True)
    double._server.serve_forever()


if __name__ == "__main__":
    main()
