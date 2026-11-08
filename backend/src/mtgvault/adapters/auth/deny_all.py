"""Verifier used when no identity provider is configured: nothing is ever authenticated."""

from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal


class DenyAllTokenVerifier:
    def verify(self, token: str) -> Principal:
        raise Unauthenticated("The access token is invalid or expired.", invalid_token=True)
