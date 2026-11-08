"""The test double behaves like the provider the application expects, over real HTTP (#59)."""

import base64
import hashlib
import time
from collections.abc import Iterator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from tests.support.oidc_double import OidcDouble

from mtgvault.adapters.auth.jwks import JwksTokenVerifier, httpx_json_fetcher
from mtgvault.domain.errors import Unauthenticated

REDIRECT = "https://app.example.test/callback"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)


@pytest.fixture(scope="module")
def provider() -> Iterator[OidcDouble]:
    double = OidcDouble(redirect_uris=(REDIRECT,)).start()
    yield double
    double.stop()


@pytest.fixture(autouse=True)
def _fresh(provider: OidcDouble) -> None:
    provider.reset()


def verifier_for(provider: OidcDouble) -> JwksTokenVerifier:
    return JwksTokenVerifier(
        issuer=provider.issuer, audience=provider.audience, algorithms=["RS256"],
        fetch_json=httpx_json_fetcher(),
    )  # fmt: skip


def authorize(provider: OidcDouble, **extra: str) -> dict[str, list[str]]:
    params = {
        "client_id": "mtgvault-test", "redirect_uri": REDIRECT, "response_type": "code",
        "state": "st", "code_challenge": CHALLENGE, "code_challenge_method": "S256",
        "scope": "openid profile email offline_access", **extra,
    }  # fmt: skip
    response = httpx.get(f"{provider.issuer}/authorize", params=params, follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlsplit(response.headers["location"]).query)


def exchange(provider: OidcDouble, code: str) -> httpx.Response:
    return httpx.post(
        f"{provider.issuer}/token",
        data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
            "code_verifier": VERIFIER, "client_id": "mtgvault-test",
        },
    )  # fmt: skip


def sign_in(provider: OidcDouble, **extra: str) -> dict[str, str]:
    return exchange(provider, authorize(provider, **extra)["code"][0]).json()  # type: ignore[no-any-return]


def test_a_token_from_the_double_passes_the_real_verifier(provider: OidcDouble) -> None:
    tokens = sign_in(provider)
    principal = verifier_for(provider).verify(tokens["access_token"])
    assert (principal.subject, principal.display_name) == ("user-1", "Ada Lovelace")
    assert principal.email == "ada@example.org"


def test_state_is_echoed_and_the_code_is_single_use(provider: OidcDouble) -> None:
    query = authorize(provider)
    assert query["state"] == ["st"]
    assert exchange(provider, query["code"][0]).status_code == 200
    assert exchange(provider, query["code"][0]).status_code == 400


def test_a_wrong_pkce_verifier_is_refused(provider: OidcDouble) -> None:
    code = authorize(provider)["code"][0]
    response = httpx.post(
        f"{provider.issuer}/token",
        data={"grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
              "code_verifier": "x" * 64},
    )  # fmt: skip
    assert response.status_code == 400


def test_cancelled_login_and_unlisted_audience_come_back_as_errors(provider: OidcDouble) -> None:
    assert authorize(provider, login_hint="deny")["error"] == ["access_denied"]
    assert authorize(provider, audience="other-api")["error"] == ["invalid_target"]


def test_refresh_rotates_and_the_old_token_dies(provider: OidcDouble) -> None:
    tokens = sign_in(provider)
    refreshed = httpx.post(
        f"{provider.issuer}/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
    ).json()
    assert refreshed["refresh_token"] != tokens["refresh_token"]
    again = httpx.post(
        f"{provider.issuer}/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
    )
    assert again.status_code == 400


def test_revocation_and_revoke_all(provider: OidcDouble) -> None:
    tokens = sign_in(provider)
    httpx.post(f"{provider.issuer}/revoke", data={"token": tokens["refresh_token"]})
    assert tokens["refresh_token"] in provider.revoked
    other = sign_in(provider)
    httpx.post(f"{provider.issuer}/__control", json={"revoke_all": True})
    result = httpx.post(
        f"{provider.issuer}/token",
        data={"grant_type": "refresh_token", "refresh_token": other["refresh_token"]},
    )
    assert result.status_code == 400


def test_fault_injection_makes_the_token_endpoint_fail(provider: OidcDouble) -> None:
    tokens = sign_in(provider)
    httpx.post(f"{provider.issuer}/__control", json={"token_status": 500})
    result = httpx.post(
        f"{provider.issuer}/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
    )
    assert result.status_code == 500


def test_short_lifetimes_and_wrong_audience_tokens_are_rejected_by_the_verifier(
    provider: OidcDouble,
) -> None:
    verifier = verifier_for(provider)
    expired = provider.access_token("user-1", ttl=-120)
    wrong_audience = provider.access_token("user-1", audience="another-api")
    for bad in (expired, wrong_audience):
        with pytest.raises(Unauthenticated):
            verifier.verify(bad)
    httpx.post(f"{provider.issuer}/__control", json={"access_ttl": 1})
    short = sign_in(provider)["access_token"]
    assert verifier.verify(short).subject == "user-1"
    time.sleep(0.1)


def test_users_without_name_or_email_and_cors_for_the_browser(provider: OidcDouble) -> None:
    bare = verifier_for(provider).verify(sign_in(provider, login_hint="user-3")["access_token"])
    assert (bare.display_name, bare.email) == (None, None)
    preflight = httpx.options(f"{provider.issuer}/token", headers={"Origin": "https://a.example"})
    assert preflight.headers["access-control-allow-origin"] == "*"


def test_logout_redirects_back(provider: OidcDouble) -> None:
    response = httpx.get(
        f"{provider.issuer}/logout", params={"rd": REDIRECT}, follow_redirects=False
    )
    assert response.headers["location"] == REDIRECT


def test_state_counts_grants_and_next_login_applies_once(provider: OidcDouble) -> None:
    tokens = sign_in(provider)
    httpx.post(
        f"{provider.issuer}/token",
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]},
    )
    state = httpx.get(f"{provider.issuer}/__state").json()
    assert (state["code_grants"], state["refresh_grants"]) == (1, 1)
    httpx.post(f"{provider.issuer}/__control", json={"next_login": "deny"})
    assert authorize(provider)["error"] == ["access_denied"]
    assert "code" in authorize(provider)  # one-shot: the following login works again
