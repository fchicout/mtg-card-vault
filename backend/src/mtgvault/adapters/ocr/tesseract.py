"""Tesseract as the ``TextRecognizer`` (FR-SCN-03, ADR-004).

The engine is run as a child process that reads the cleaned region from standard input and writes
the text to standard output: no temporary files, so an image never touches the disk (FR-SCN-06).
A bounded number of recognitions run at once, so scans cannot starve the API of CPU, and every
call has a timeout.
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess  # fixed command, no shell, arguments are constants
import threading
from collections.abc import Callable

from PIL import Image, UnidentifiedImageError

from mtgvault.adapters.ocr.preprocess import decode, regions_from_frame
from mtgvault.application.ports import RecognizedText
from mtgvault.domain.errors import FieldError, UpstreamUnavailable, ValidationFailed

_log = logging.getLogger("mtgvault.ocr")
TITLE_ARGS = ("--psm", "7", "--oem", "1")
COLLECTOR_ARGS = (
    "--psm", "6", "--oem", "1",
    "-c", "tessedit_char_whitelist=0123456789/ABCDEFGHIJKLMNOPQRSTUVWXYZ-",
)  # fmt: skip

Runner = Callable[[list[str], bytes, float], str]


def _run_process(command: list[str], payload: bytes, timeout: float) -> str:
    completed = subprocess.run(  # noqa: S603  # fixed executable and constant arguments
        command, input=payload, capture_output=True, timeout=timeout, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"tesseract exited with {completed.returncode}")
    return completed.stdout.decode("utf-8", errors="replace")


def find_tesseract(command: str = "tesseract") -> str | None:
    return shutil.which(command)


class TesseractRecognizer:
    def __init__(
        self,
        command: str = "tesseract",
        *,
        max_concurrent: int = 2,
        timeout: float = 6.0,
        binarize: bool = False,
        runner: Runner = _run_process,
    ) -> None:
        self._command = command
        self._timeout = timeout
        self._binarize = binarize
        self._run = runner
        self._slots = threading.BoundedSemaphore(max_concurrent)

    def read(self, image: bytes) -> RecognizedText:
        try:
            frame = decode(image)
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise ValidationFailed(
                "The image cannot be read.",
                (FieldError("image", "The file is damaged or not an image."),),
            ) from error
        regions = regions_from_frame(frame, binarize=self._binarize)
        with self._slots:
            title = self._recognise(regions.title, TITLE_ARGS)
            collector = self._recognise(regions.collector, COLLECTOR_ARGS)
        return RecognizedText(title=title, collector=collector)

    def _recognise(self, region: Image.Image, args: tuple[str, ...]) -> str:
        buffer = io.BytesIO()
        region.save(buffer, format="PNG")  # in memory only
        command = [self._command, "stdin", "stdout", "-l", "eng", *args]
        try:
            return self._run(command, buffer.getvalue(), self._timeout).strip()
        except (subprocess.TimeoutExpired, RuntimeError, OSError) as error:
            _log.warning("text recognition failed: %s", type(error).__name__)
            raise UpstreamUnavailable("Card recognition is temporarily unavailable.") from error
