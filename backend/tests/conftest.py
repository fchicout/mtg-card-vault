import pytest


@pytest.fixture(autouse=True)
def _identity_provider_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API refuses to start without an issuer and audience; tests get harmless defaults."""
    monkeypatch.setenv("OIDC_ISSUER_URL", "https://idp.example.test")
    monkeypatch.setenv("OIDC_AUDIENCE", "mtgvault-api")
