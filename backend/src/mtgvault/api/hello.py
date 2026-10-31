"""TEMPORARY skeleton route (issue #1): public on purpose, removed by issue #15 (US-026)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from mtgvault.api.dependencies import get_greeting_service
from mtgvault.application.greeting_service import GreetingService

router = APIRouter(tags=["skeleton"])


class HelloResponse(BaseModel):
    message: str


@router.get("/hello", operation_id="getHello", summary="Skeleton greeting (temporary)")
def get_hello(
    service: Annotated[GreetingService, Depends(get_greeting_service)],
) -> HelloResponse:
    return HelloResponse(message=service.greet().message)
