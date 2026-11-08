"""The caller's own profile (US-004, FR-AUTH-04)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mtgvault.api.dependencies import get_user_service
from mtgvault.api.security import current_principal
from mtgvault.application.user_service import UserService
from mtgvault.domain.identity import Principal

router = APIRouter(tags=["account"])


class Me(BaseModel):
    """What the application knows about the caller: nothing beyond this."""

    id: UUID
    display_name: str | None = None
    email: str | None = None


@router.get("/me", operation_id="getMe", summary="The signed-in user's profile")
def get_me(
    principal: Annotated[Principal, Depends(current_principal)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> Me:
    """Provisions the account on the first authenticated request, then returns the profile."""
    user = service.ensure_user(principal)
    return Me(id=user.id, display_name=user.display_name, email=user.email)
