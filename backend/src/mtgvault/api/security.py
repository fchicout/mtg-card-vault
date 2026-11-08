"""Authentication for the API surface: every versioned route requires a valid bearer token."""

from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mtgvault.api.dependencies import get_user_service
from mtgvault.application.ports import TokenVerifier
from mtgvault.application.user_service import UserService
from mtgvault.domain.errors import Unauthenticated
from mtgvault.domain.identity import Principal
from mtgvault.domain.user import User

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


def current_user(
    principal: Annotated[Principal, Depends(current_principal)],
    users: Annotated[UserService, Depends(get_user_service)],
) -> User:
    """The caller's user record (created on first sight). The ONLY source of the user id for
    every owner-scoped operation: never a request field (FR-VLT-07)."""
    return users.ensure_user(principal)
