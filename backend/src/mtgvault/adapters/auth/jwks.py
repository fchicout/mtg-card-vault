"""Locally validated JWT access tokens against the provider's cached JWKS (ADR-003, FR-AUTH-05).

* Algorithms come from an allow-list of asymmetric ones; ``none`` and HMAC are never accepted.
* ``iss``, ``aud``, ``exp`` and ``sub`` are required; ``nbf`` is honoured; clock leeway <= 60 s.
* Keys are cached for ``jwks_ttl`` seconds. An unknown ``kid`` triggers one refresh, at most
  once per ``min_refresh_interval`` (forged key ids cannot make us hammer the provider).
* If the provider is down, cached keys keep working for up to ``max_stale`` seconds; with no usable
  keys at all the verifier raises ``UpstreamUnavailable`` (HTTP 503), never a 401.
* Validation details are logged, never returned to the caller.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
import jwt

from mtgvault.config import ASYMMETRIC_ALGORITHMS, is_acceptable_url
from mtgvault.domain.errors import Unauthenticated, UpstreamUnavailable
from mtgvault.domain.identity import Principal, principal_from_claims

_log = logging.getLogger("mtgvault.auth")
_GENERIC = "The access token is invalid or expired."

JsonFetcher = Callable[[str], dict[str, Any]]


class ProviderUnreachable(Exception):
    """The discovery document or the key set could not be fetched or understood."""


def httpx_json_fetcher(timeout: float = 5.0) -> JsonFetcher:
    """GET a JSON document; redirects are not followed and the body is size-limited."""

    def fetch(url: str) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                response = client.get(url, headers={"Accept": "application/json"})
                response.raise_for_status()
                if len(response.content) > 1_000_000:
                    raise ProviderUnreachable("the document is unreasonably large")
                document = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise ProviderUnreachable(type(error).__name__) from error
        if not isinstance(document, dict):
            raise ProviderUnreachable("not a JSON object")
        return document

    return fetch


class JwksTokenVerifier:
    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        algorithms: list[str],
        fetch_json: JsonFetcher,
        clock: Callable[[], float] = time.monotonic,
        jwks_ttl: float = 600.0,
        min_refresh_interval: float = 30.0,
        max_stale: float = 86_400.0,
        leeway: int = 60,
    ) -> None:
        unsafe = set(algorithms) - ASYMMETRIC_ALGORITHMS
        if unsafe or not algorithms:
            raise ValueError(f"unsupported token algorithms: {sorted(unsafe) or 'none given'}")
        if not is_acceptable_url(issuer):
            raise ValueError("the issuer must be an https URL")
        self._issuer = issuer.rstrip("/")
        self._audience = audience
        self._algorithms = list(algorithms)
        self._fetch = fetch_json
        self._clock = clock
        self._ttl = jwks_ttl
        self._min_refresh = min_refresh_interval
        self._max_stale = max_stale
        self._leeway = min(leeway, 60)
        self._lock = threading.Lock()
        self._jwks_uri: str | None = None
        self._keys: dict[str, jwt.PyJWK] = {}
        self._fetched_at: float | None = None
        self._last_attempt: float | None = None

    # ------------------------------------------------------------------ public API
    def verify(self, token: str) -> Principal:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as error:
            raise self._reject("malformed token") from error
        algorithm = header.get("alg")
        if algorithm not in self._algorithms:
            raise self._reject(f"algorithm {algorithm!r} is not allowed")
        key = self._key_for(header.get("kid"))
        try:
            claims = jwt.decode(
                token,
                key.key,
                algorithms=[algorithm],
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as error:
            raise self._reject(type(error).__name__) from error
        try:
            return principal_from_claims(claims)
        except ValueError:
            raise self._reject("empty subject") from None

    # ------------------------------------------------------------------ keys
    def _key_for(self, kid: object) -> jwt.PyJWK:
        with self._lock:
            self._refresh_if_stale()
            key = self._lookup(kid)
            if key is None and self._may_refresh():
                self._refresh(force=True)
                key = self._lookup(kid)
        if key is None:
            raise self._reject("unknown signing key")
        return key

    def _lookup(self, kid: object) -> jwt.PyJWK | None:
        if isinstance(kid, str) and kid in self._keys:
            return self._keys[kid]
        if kid is None and len(self._keys) == 1:
            return next(iter(self._keys.values()))
        return None

    def _may_refresh(self) -> bool:
        return self._last_attempt is None or self._clock() - self._last_attempt >= self._min_refresh

    def _refresh_if_stale(self) -> None:
        now = self._clock()
        if self._fetched_at is None or now - self._fetched_at >= self._ttl:
            self._refresh(force=False)

    def _refresh(self, *, force: bool) -> None:
        now = self._clock()
        if (
            not force
            and self._last_attempt is not None
            and now - self._last_attempt < self._min_refresh
        ):
            self._require_usable_keys(now)
            return
        self._last_attempt = now
        try:
            uri = self._discover()
            document = self._fetch(uri)
            keys = {
                k["kid"]: jwt.PyJWK(k)
                for k in document.get("keys", [])
                if isinstance(k, dict) and k.get("kid") and k.get("use", "sig") == "sig"
            }
            if not keys:
                raise ProviderUnreachable("the key set holds no signing keys")
        except (ProviderUnreachable, jwt.PyJWTError, KeyError, TypeError) as error:
            _log.warning("could not refresh the signing keys: %s", type(error).__name__)
            self._require_usable_keys(now)
            return
        self._keys, self._fetched_at = keys, now

    def _discover(self) -> str:
        if self._jwks_uri is None:
            document = self._fetch(f"{self._issuer}/.well-known/openid-configuration")
            if str(document.get("issuer", "")).rstrip("/") != self._issuer:
                raise ProviderUnreachable("the discovery document names another issuer")
            uri = document.get("jwks_uri")
            if not isinstance(uri, str) or not is_acceptable_url(uri):
                raise ProviderUnreachable("no acceptable jwks_uri")
            self._jwks_uri = uri
        return self._jwks_uri

    def _require_usable_keys(self, now: float) -> None:
        """Keep serving from the cache while it is young enough; otherwise report the outage."""
        if self._fetched_at is None or now - self._fetched_at >= self._max_stale:
            raise UpstreamUnavailable("The identity provider is currently unreachable.")

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _reject(reason: str) -> Unauthenticated:
        _log.info("token rejected: %s", reason)
        return Unauthenticated(_GENERIC, invalid_token=True)
