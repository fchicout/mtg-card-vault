"""Authentication for the API surface: every versioned route requires a valid bearer token."""

from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mtgvault.application.ports import TokenVerifier
from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal

_bearer = HTTPBearer(
    auto_error=False,
    description="OIDC access token (JWT) issued for this API's audience.",
)


def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """The verified caller, or a 401 problem document with ``WWW-Authenticate: Bearer``."""
    if credentials is None:
        raise Unauthenticated("Authentication is required.")
    verifier = cast("TokenVerifier", request.app.state.token_verifier)
    return verifier.verify(credentials.credentials)
