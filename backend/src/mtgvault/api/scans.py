"""Scan endpoint (US-016, US-018, UC-02): one image in, recognised text and candidates out.

The image lives only in this request's memory: it is read, recognised and dropped (FR-SCN-06).
A scan never touches the vault (FR-SCN-05)."""

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartParser

from mtgvault.adapters.ocr.upload import inspect_upload
from mtgvault.api.catalog import CardSummary, card_summary
from mtgvault.api.security import current_principal
from mtgvault.application.ports import RateLimiter
from mtgvault.application.scan_service import ScanResult, ScanService
from mtgvault.domain.errors import FieldError, UnsupportedMediaType, ValidationFailed
from mtgvault.domain.identity import Principal

# Uploads never reach the disk: Starlette would spool a file part above 1 MB into a temporary file.
# Everything this endpoint accepts (2 MB, enforced before parsing) stays in memory (FR-SCN-06).
MultiPartParser.spool_max_size = 4 * 1024 * 1024

router = APIRouter(prefix="/scans", tags=["scan"])


class RecognizedTextDto(BaseModel):
    title: str
    collector: str


class CandidateDto(BaseModel):
    card: CardSummary
    confidence: float
    exact: bool


class ScanResponse(BaseModel):
    text: RecognizedTextDto
    candidates: list[CandidateDto]
    reason: Literal["unreadable", "no_match"] | None = None


def _limited(request: Request, principal: Annotated[Principal, Depends(current_principal)]) -> None:
    """Counts the scan for the caller BEFORE the body is read."""
    cast("RateLimiter", request.app.state.scan_rate_limiter).check(principal.subject)


def _dto(result: ScanResult) -> ScanResponse:
    return ScanResponse(
        text=RecognizedTextDto(title=result.title_text, collector=result.collector_text),
        candidates=[
            CandidateDto(card=card_summary(c.card), confidence=c.confidence, exact=c.exact)
            for c in result.candidates
        ],
        reason=result.reason,
    )


@router.post(
    "",
    operation_id="scanCard",
    summary="Recognise a card in one camera frame",
    dependencies=[Depends(_limited)],
    # The endpoint reads the multipart form itself (to keep it in memory); declare it for the contract.
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["image"],
                        "properties": {"image": {"type": "string", "format": "binary"}},
                    }
                }
            },
        }
    },
    responses={
        413: {"description": "The image is larger than 2 MB"},
        415: {"description": "Not a JPEG, PNG or WebP image"},
    },
)
async def scan_card(request: Request) -> ScanResponse:
    """Multipart form with one field, ``image``. At most 5 candidates, best first."""
    form = await request.form(max_files=1, max_fields=1)
    upload = form.get("image")
    if not isinstance(upload, UploadFile):
        raise ValidationFailed(
            "Send the image as the form field 'image'.", (FieldError("image", "Missing."),)
        )
    data = await upload.read()
    await upload.close()
    if not data:
        raise UnsupportedMediaType("Send a JPEG, PNG or WebP image.")
    inspect_upload(data)  # size, magic bytes, pixels: before any decode or OCR
    service = cast("ScanService", request.app.state.scan_service)
    result = await run_in_threadpool(service.scan, data)
    return _dto(result)
