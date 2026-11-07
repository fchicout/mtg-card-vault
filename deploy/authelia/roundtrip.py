#!/usr/bin/env python3
"""Authorization-code + PKCE round trip against the development Authelia (issue #4, ADR-003).

Proves, with no dependency but the standard library, that the SPA client receives a verifiable
RS256 JWT access token for the API audience, and probes refresh-token rotation, revocation, PKCE
enforcement and what "sign out" can mean on this identity provider.

  deploy/authelia/dev-secrets.sh && docker compose -f deploy/compose.yaml --profile ci up -d authelia
  python3 deploy/authelia/roundtrip.py
Exit code 0 = every check passed, 1 = at least one failed. Prints the decoded claims as evidence.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.cookiejar
import json
import os
import socket
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REDIRECT_URI = "https://app.localtest.me:4200/callback"
SCOPE = "openid profile email offline_access"
CLIENT_ID = "mtgvault-spa"
AUDIENCE = "mtgvault-api"


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def decode_jwt(token: str) -> tuple[dict, dict, bytes, bytes]:
    header, payload, signature = token.split(".")
    return (json.loads(b64u_decode(header)), json.loads(b64u_decode(payload)),
            f"{header}.{payload}".encode(), b64u_decode(signature))


def verify_rs256(signing_input: bytes, signature: bytes, jwk: dict) -> bool:
    """RSASSA-PKCS1-v1_5 with SHA-256, computed with plain integers (RFC 8017 section 8.2.2)."""
    n, e = int.from_bytes(b64u_decode(jwk["n"]), "big"), int.from_bytes(b64u_decode(jwk["e"]), "big")
    size = (n.bit_length() + 7) // 8
    if len(signature) != size:
        return False
    em = pow(int.from_bytes(signature, "big"), e, n).to_bytes(size, "big")
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(signing_input).digest()
    return em == b"\x00\x01" + b"\xff" * (size - len(digest_info) - 3) + b"\x00" + digest_info


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None


class Client:
    """A tiny browser: cookies, no automatic redirects, a pinned CA, *.localtest.me -> 127.0.0.1."""

    def __init__(self, cafile: str) -> None:
        original = socket.getaddrinfo
        socket.getaddrinfo = lambda host, *a, **k: original(  # type: ignore[assignment]
            "127.0.0.1" if str(host).endswith(".localtest.me") else host, *a, **k)
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            NoRedirect, urllib.request.HTTPCookieProcessor(self.jar),
            urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=cafile)))

    def request(self, url: str, data: bytes | None = None, headers: dict | None = None,
                method: str | None = None) -> tuple[int, dict, bytes]:
        request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
        try:
            response = self.opener.open(request, timeout=20)
        except urllib.error.HTTPError as error:
            response = error
        return response.status, dict(response.headers), response.read()


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.failures += 0 if ok else 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))

    def info(self, name: str, value: object) -> None:
        print(f"INFO  {name}: {value}")


def main(argv: list[str]) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--base", default="https://auth.localtest.me:9091")
    parser.add_argument("--cacert", default=str(here / "secrets" / "tls.crt"))
    parser.add_argument("--password", default="dev-only-password")
    args = parser.parse_args(argv[1:])
    report = Report()
    base = args.base

    def new_login(user: str, state: str | None = None, challenge_override: str | None = None,
                  client: Client | None = None, pkce: bool = True) -> tuple[Client, str, str, dict]:
        """Run authorize + first factor; returns (client, verifier, code, redirect query)."""
        client = client or Client(args.cacert)
        verifier = b64u(os.urandom(48))
        challenge = challenge_override or b64u(hashlib.sha256(verifier.encode()).digest())
        state = state or b64u(os.urandom(12))
        fields = {
            "client_id": CLIENT_ID, "response_type": "code", "scope": SCOPE, "redirect_uri": REDIRECT_URI,
            "state": state, "nonce": "nonce-" + b64u(os.urandom(9)), "audience": AUDIENCE}
        if pkce:
            fields.update({"code_challenge": challenge, "code_challenge_method": "S256"})
        query = urllib.parse.urlencode(fields)
        status, headers, _ = client.request(f"{base}/api/oidc/authorization?{query}")
        location = headers.get("Location", "")
        if not location.startswith(base + "/?"):  # already signed in, or an error redirect
            return client, verifier, "", dict(urllib.parse.parse_qsl(urllib.parse.urlparse(location).query))
        flow_id = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)["flow_id"][0]
        body = json.dumps({"username": user, "password": args.password, "keepMeLoggedIn": False,
                           "flowID": flow_id, "flow": "openid_connect"}).encode()
        status, _, answer = client.request(f"{base}/api/firstfactor", body, {"Content-Type": "application/json"}, "POST")
        if status != 200:
            return client, verifier, "", {"error": f"login failed ({status})"}
        status, headers, _ = client.request(json.loads(answer)["data"]["redirect"])
        # The portal's consent page: with consent_mode 'implicit' it only has to confirm.
        consent_flow = urllib.parse.parse_qs(urllib.parse.urlparse(headers.get("Location", "")).query).get("flow_id", [""])[0]
        accept = json.dumps({"flow_id": consent_flow, "client_id": CLIENT_ID, "consent": True, "pre_configure": False}).encode()
        status, _, answer = client.request(f"{base}/api/oidc/consent", accept, {"Content-Type": "application/json"}, "POST")
        if status != 200 or json.loads(answer).get("status") != "OK":
            return client, verifier, "", {"error": f"consent failed ({status})"}
        status, headers, _ = client.request(json.loads(answer)["data"]["redirect_uri"])
        result = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(headers.get("Location", "")).query))
        result["_state_sent"] = state
        return client, verifier, result.get("code", ""), result

    def token(client: Client, fields: dict) -> tuple[int, dict]:
        status, _, body = client.request(f"{base}/api/oidc/token", urllib.parse.urlencode(fields).encode(),
                                         {"Content-Type": "application/x-www-form-urlencoded"}, "POST")
        return status, json.loads(body or b"{}")

    # ---- discovery -------------------------------------------------------------------------
    anonymous = Client(args.cacert)
    status, _, body = anonymous.request(f"{base}/.well-known/openid-configuration")
    discovery = json.loads(body)
    report.check("discovery over HTTPS", status == 200 and discovery["issuer"] == base)
    report.check("PKCE S256 and refresh_token supported",
                 "S256" in discovery["code_challenge_methods_supported"]
                 and "refresh_token" in discovery["grant_types_supported"])
    report.info("end_session_endpoint advertised", discovery.get("end_session_endpoint"))
    report.info("revocation_endpoint", discovery.get("revocation_endpoint"))
    _, _, body = anonymous.request(discovery["jwks_uri"])
    jwks = {key["kid"]: key for key in json.loads(body)["keys"]}
    report.check("JWKS is published", bool(jwks), ", ".join(jwks))

    # ---- authorization code + PKCE -----------------------------------------------------------
    client, verifier, code, redirect = new_login("alice")
    report.check("authorization code returned with the sent state and the issuer",
                 bool(code) and redirect.get("state") == redirect.get("_state_sent")
                 and redirect.get("iss") == discovery["issuer"], f"keys={sorted(k for k in redirect if k[0] != '_')}")
    status, tokens = token(client, {"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI,
                                    "client_id": CLIENT_ID, "code_verifier": verifier})
    report.check("token endpoint accepts the code with the PKCE verifier", status == 200, f"HTTP {status}")
    access, refresh, id_token = tokens.get("access_token", ""), tokens.get("refresh_token", ""), tokens.get("id_token", "")
    report.check("response carries access, refresh and id tokens, type Bearer",
                 bool(access and refresh and id_token) and tokens.get("token_type", "").lower() == "bearer")
    report.check("access token is a JWT (3 segments)", access.count(".") == 2)
    if access.count(".") != 2:
        print("Cannot continue without a JWT access token."); return 1

    header, claims, signing_input, signature = decode_jwt(access)
    report.info("access token header", json.dumps(header))
    report.info("access token claims", json.dumps(claims, sort_keys=True))
    report.check("alg is RS256 and kid is published in the JWKS", header.get("alg") == "RS256" and header.get("kid") in jwks)
    report.check("RS256 signature verifies against the JWKS key", verify_rs256(signing_input, signature, jwks.get(header.get("kid"), {"n": "AA", "e": "AQ"})))
    now = int(time.time())
    report.check("iss is the Authelia issuer", claims.get("iss") == discovery["issuer"])
    report.check(f"aud contains the API audience '{AUDIENCE}'", AUDIENCE in (claims.get("aud") if isinstance(claims.get("aud"), list) else [claims.get("aud")]))
    report.check("sub is present", bool(claims.get("sub")))
    report.check("exp is in the future, iat not in the future", claims.get("exp", 0) > now and claims.get("iat", now + 1) <= now + 5)
    report.check("client_id identifies the SPA", claims.get("client_id") == CLIENT_ID or claims.get("azp") == CLIENT_ID)
    scopes = claims.get("scp") or claims.get("scope") or []
    scopes = scopes.split() if isinstance(scopes, str) else scopes
    report.check("scopes include openid", "openid" in scopes, str(scopes))
    report.check("jti is present", bool(claims.get("jti")))
    report.info("access token lifetime (s)", claims.get("exp", 0) - claims.get("iat", 0))
    report.info("typ header (RFC 9068 expects at+jwt)", header.get("typ"))

    id_header, id_claims, id_input, id_sig = decode_jwt(id_token)
    report.check("id token verifies and is for the SPA client", verify_rs256(id_input, id_sig, jwks.get(id_header.get("kid"), {"n": "AA", "e": "AQ"}))
                 and (CLIENT_ID in (id_claims["aud"] if isinstance(id_claims["aud"], list) else [id_claims["aud"]])))
    report.check("access token and id token share the same sub", id_claims.get("sub") == claims.get("sub"))

    # ---- identity isolation ------------------------------------------------------------------
    bob_client, bob_verifier, bob_code, _ = new_login("bob")
    _, bob_tokens = token(bob_client, {"grant_type": "authorization_code", "code": bob_code, "redirect_uri": REDIRECT_URI,
                                       "client_id": CLIENT_ID, "code_verifier": bob_verifier})
    bob_sub = decode_jwt(bob_tokens.get("access_token", "a.e30.c"))[1].get("sub")
    report.check("two users get two different, stable subs", bool(bob_sub) and bob_sub != claims.get("sub"))

    # ---- refresh rotation ---------------------------------------------------------------------
    status, rotated = token(client, {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": CLIENT_ID})
    report.check("refresh token grants new tokens", status == 200 and bool(rotated.get("access_token")), f"HTTP {status}")
    report.check("the refresh token is rotated", bool(rotated.get("refresh_token")) and rotated.get("refresh_token") != refresh)
    report.check("the new access token keeps the sub and the audience",
                 decode_jwt(rotated["access_token"])[1].get("sub") == claims.get("sub")
                 and AUDIENCE in (decode_jwt(rotated["access_token"])[1].get("aud") or []))
    status, answer = token(client, {"grant_type": "refresh_token", "refresh_token": refresh, "client_id": CLIENT_ID})
    report.check("the old refresh token is rejected after rotation", status >= 400, f"HTTP {status} {answer.get('error', '')}")

    # ---- PKCE enforcement and code reuse ------------------------------------------------------
    c2, v2, code2, _ = new_login("alice", client=Client(args.cacert))
    status, _ = token(c2, {"grant_type": "authorization_code", "code": code2, "redirect_uri": REDIRECT_URI,
                           "client_id": CLIENT_ID, "code_verifier": b64u(os.urandom(48))})
    report.check("a wrong code_verifier is rejected", status >= 400, f"HTTP {status}")
    c3, v3, code3, _ = new_login("alice", client=Client(args.cacert), pkce=False)
    status = token(c3, {"grant_type": "authorization_code", "code": code3, "redirect_uri": REDIRECT_URI,
                        "client_id": CLIENT_ID})[0] if code3 else 400
    report.check("an authorization request without PKCE gets no usable code", status >= 400, "no code" if not code3 else f"HTTP {status}")
    c4, v4, code4, _ = new_login("alice", client=Client(args.cacert))
    first, first_tokens = token(c4, {"grant_type": "authorization_code", "code": code4, "redirect_uri": REDIRECT_URI,
                                     "client_id": CLIENT_ID, "code_verifier": v4})
    reuse, _ = token(c4, {"grant_type": "authorization_code", "code": code4, "redirect_uri": REDIRECT_URI,
                          "client_id": CLIENT_ID, "code_verifier": v4})
    report.check("an authorization code cannot be used twice", first == 200 and reuse >= 400, f"HTTP {reuse}")
    status, answer = token(c4, {"grant_type": "refresh_token", "refresh_token": first_tokens.get("refresh_token", ""), "client_id": CLIENT_ID})
    report.check("code reuse revokes the tokens issued from that code (the SPA must then sign in again)", status >= 400,
                 f"HTTP {status} {answer.get('error', '')}: Authelia answers 500, not 400 (upstream issue 13390)")

    # ---- revocation and sign out ----------------------------------------------------------------
    current = rotated.get("refresh_token", "")
    status, _, _ = client.request(discovery["revocation_endpoint"], urllib.parse.urlencode({"token": current, "client_id": CLIENT_ID,
                                  "token_type_hint": "refresh_token"}).encode(), {"Content-Type": "application/x-www-form-urlencoded"}, "POST")
    report.check("a refresh token can be revoked by the public client", status == 200, f"HTTP {status}")
    status, _ = token(client, {"grant_type": "refresh_token", "refresh_token": current, "client_id": CLIENT_ID})
    report.check("a revoked refresh token no longer works", status >= 400, f"HTTP {status}")

    status, _, _ = client.request(f"{base}/api/logout", b"{}", {"Content-Type": "application/json"}, "POST")
    _, headers, _ = client.request(f"{base}/api/oidc/authorization?" + urllib.parse.urlencode({
        "client_id": CLIENT_ID, "response_type": "code", "scope": SCOPE, "redirect_uri": REDIRECT_URI, "state": b64u(os.urandom(12)),
        "nonce": "nonce-0123456789", "code_challenge": b64u(hashlib.sha256(b"x").digest()), "code_challenge_method": "S256"}))
    report.check("after the portal logout the browser must sign in again", headers.get("Location", "").startswith(base + "/?"),
                 f"logout HTTP {status}")

    print(f"\n{'ALL CHECKS PASSED' if not report.failures else str(report.failures) + ' CHECK(S) FAILED'}")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
