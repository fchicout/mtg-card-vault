"""Token verification: forged, expired, wrong issuer/audience, alg none, key rotation, outages."""

import base64
import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mtgvault.adapters.auth.jwks import JwksTokenVerifier, ProviderUnreachable
from mtgvault.domain.errors import Unauthenticated, UpstreamUnavailable

ISSUER = "https://idp.example.test"
AUDIENCE = "mtgvault-api"


def make_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwk(key: rsa.RSAPrivateKey, kid: str) -> dict[str, Any]:
    data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    return {**data, "kid": kid, "use": "sig", "alg": "RS256"}


def token(key: rsa.RSAPrivateKey, kid: str = "k1", **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": ISSUER, "aud": AUDIENCE, "sub": "user-1", "iat": now, "exp": now + 600,
        "name": "Ada",
    }  # fmt: skip
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


class Provider:
    """A fake identity provider: discovery + JWKS with counters and an outage switch."""

    def __init__(self, *keys: tuple[str, rsa.RSAPrivateKey]) -> None:
        self.keys = list(keys)
        self.down = False
        self.calls: list[str] = []
        self.issuer_in_document = ISSUER

    def __call__(self, url: str) -> dict[str, Any]:
        self.calls.append(url)
        if self.down:
            raise ProviderUnreachable("down")
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": self.issuer_in_document, "jwks_uri": f"{ISSUER}/jwks.json"}
        return {"keys": [jwk(key, kid) for kid, key in self.keys]}

    @property
    def jwks_calls(self) -> int:
        return sum(1 for c in self.calls if c.endswith("jwks.json"))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(scope="module")
def key() -> rsa.RSAPrivateKey:
    return make_key()


@pytest.fixture(scope="module")
def other_key() -> rsa.RSAPrivateKey:
    return make_key()


def build(provider: Provider, clock: Clock | None = None, **kwargs: Any) -> JwksTokenVerifier:
    return JwksTokenVerifier(
        issuer=ISSUER, audience=AUDIENCE, algorithms=["RS256"], fetch_json=provider,
        clock=clock or Clock(), **kwargs,
    )  # fmt: skip


def test_a_valid_token_yields_the_principal(key: rsa.RSAPrivateKey) -> None:
    principal = build(Provider(("k1", key))).verify(token(key))
    assert principal.subject == "user-1"
    assert principal.display_name == "Ada"
    assert not hasattr(principal, "claims")  # everything else is dropped at the boundary


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 3600},
        {"nbf": int(time.time()) + 3600},
        {"iss": "https://evil.example"},
        {"aud": "another-api"},
        {"sub": None},
        {"sub": "  "},
        {"exp": None},
    ],
    ids=[
        "expired",
        "not-yet-valid",
        "wrong-issuer",
        "wrong-audience",
        "no-sub",
        "blank-sub",
        "no-exp",
    ],
)
def test_defective_tokens_are_rejected(key: rsa.RSAPrivateKey, overrides: dict[str, Any]) -> None:
    with pytest.raises(Unauthenticated) as rejected:
        build(Provider(("k1", key))).verify(token(key, **overrides))
    assert rejected.value.invalid_token
    assert rejected.value.detail == "The access token is invalid or expired."  # one generic text


def test_small_clock_skew_is_tolerated(key: rsa.RSAPrivateKey) -> None:
    assert build(Provider(("k1", key))).verify(token(key, exp=int(time.time()) - 30)).subject


def test_token_signed_by_another_key_is_rejected(
    key: rsa.RSAPrivateKey, other_key: rsa.RSAPrivateKey
) -> None:
    with pytest.raises(Unauthenticated):
        build(Provider(("k1", key))).verify(token(other_key))


def test_alg_none_and_hmac_tokens_are_rejected(key: rsa.RSAPrivateKey) -> None:
    def b64(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    claims = {"iss": ISSUER, "aud": AUDIENCE, "sub": "x", "exp": int(time.time()) + 600}
    unsigned = f"{b64({'alg': 'none', 'kid': 'k1'})}.{b64(claims)}."
    hmac_token = jwt.encode(claims, "secret" * 8, algorithm="HS256", headers={"kid": "k1"})
    verifier = build(Provider(("k1", key)))
    for bad in (unsigned, hmac_token):
        with pytest.raises(Unauthenticated):
            verifier.verify(bad)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_is_rejected(key: rsa.RSAPrivateKey, garbage: str) -> None:
    with pytest.raises(Unauthenticated):
        build(Provider(("k1", key))).verify(garbage)


def test_keys_are_cached_between_requests(key: rsa.RSAPrivateKey) -> None:
    provider = Provider(("k1", key))
    verifier = build(provider)
    for _ in range(5):
        verifier.verify(token(key))
    assert provider.jwks_calls == 1


def test_unknown_kid_refreshes_once_then_picks_up_a_rotated_key(
    key: rsa.RSAPrivateKey, other_key: rsa.RSAPrivateKey
) -> None:
    provider, clock = Provider(("k1", key)), Clock()
    verifier = build(provider, clock)
    verifier.verify(token(key))
    provider.keys = [("k1", key), ("k2", other_key)]
    clock.now += 31  # beyond the minimum refresh interval
    assert verifier.verify(token(other_key, kid="k2")).subject == "user-1"
    assert provider.jwks_calls == 2


def test_forged_key_ids_cannot_make_us_hammer_the_provider(key: rsa.RSAPrivateKey) -> None:
    provider = Provider(("k1", key))
    verifier = build(provider)
    verifier.verify(token(key))
    for index in range(20):
        with pytest.raises(Unauthenticated):
            verifier.verify(token(key, kid=f"forged-{index}"))
    assert provider.jwks_calls <= 2


def test_cached_keys_keep_working_while_the_provider_is_down(key: rsa.RSAPrivateKey) -> None:
    provider, clock = Provider(("k1", key)), Clock()
    verifier = build(provider, clock)
    verifier.verify(token(key))
    provider.down = True
    clock.now += 3600  # past the TTL, still younger than the stale limit
    assert verifier.verify(token(key)).subject == "user-1"


def test_too_stale_keys_become_a_503(key: rsa.RSAPrivateKey) -> None:
    provider, clock = Provider(("k1", key)), Clock()
    verifier = build(provider, clock, max_stale=7200)
    verifier.verify(token(key))
    provider.down = True
    clock.now += 7201
    with pytest.raises(UpstreamUnavailable):
        verifier.verify(token(key))


def test_provider_down_from_the_start_is_a_503_not_a_401(key: rsa.RSAPrivateKey) -> None:
    provider = Provider(("k1", key))
    provider.down = True
    with pytest.raises(UpstreamUnavailable):
        build(provider).verify(token(key))


def test_discovery_document_for_another_issuer_is_refused(key: rsa.RSAPrivateKey) -> None:
    provider = Provider(("k1", key))
    provider.issuer_in_document = "https://evil.example"
    with pytest.raises(UpstreamUnavailable):
        build(provider).verify(token(key))


@pytest.mark.parametrize("algorithms", [[], ["HS256"], ["none"], ["RS256", "HS512"]])
def test_unsafe_algorithm_configuration_is_refused(algorithms: list[str]) -> None:
    with pytest.raises(ValueError, match="algorithms"):
        JwksTokenVerifier(
            issuer=ISSUER, audience=AUDIENCE, algorithms=algorithms, fetch_json=Provider()
        )


def test_plain_http_issuer_is_refused_except_for_loopback() -> None:
    with pytest.raises(ValueError, match="https"):
        JwksTokenVerifier(
            issuer="http://idp.example",
            audience=AUDIENCE,
            algorithms=["RS256"],
            fetch_json=Provider(),
        )
    JwksTokenVerifier(
        issuer="http://localhost:9000",
        audience=AUDIENCE,
        algorithms=["RS256"],
        fetch_json=Provider(),
    )
