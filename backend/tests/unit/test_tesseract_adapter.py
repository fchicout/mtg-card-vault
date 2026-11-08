"""The Tesseract adapter's behaviour with a fake process runner (no engine needed)."""

import io
import subprocess
import threading
import time

import pytest
from PIL import Image

from mtgvault.adapters.ocr.tesseract import COLLECTOR_ARGS, TITLE_ARGS, TesseractRecognizer
from mtgvault.application.ports import TextRecognizer
from mtgvault.domain.errors import UpstreamUnavailable, ValidationFailed


def frame_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1280, 720), (40, 40, 40)).save(buffer, format="JPEG")
    return buffer.getvalue()


class Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], int]] = []

    def __call__(self, command: list[str], payload: bytes, timeout: float) -> str:
        self.calls.append((command, len(payload)))
        return "Lightning Bolt\n" if "7" in command else "146/249 C\nM10 EN\n"


def test_it_reads_both_regions_through_standard_input_only() -> None:
    runner = Runner()
    engine: TextRecognizer = TesseractRecognizer(runner=runner)
    text = engine.read(frame_bytes())
    assert (text.title, text.collector) == ("Lightning Bolt", "146/249 C\nM10 EN")
    assert [c[0][1:3] for c in runner.calls] == [["stdin", "stdout"]] * 2  # nothing on disk
    assert TITLE_ARGS[1] == "7"
    assert "tessedit_char_whitelist" in " ".join(COLLECTOR_ARGS)
    assert all(size > 100 for _, size in runner.calls)


def test_an_undecodable_image_is_a_validation_error() -> None:
    recognizer = TesseractRecognizer(runner=Runner())
    with pytest.raises(ValidationFailed):
        recognizer.read(b"\xff\xd8\xff garbage")


@pytest.mark.parametrize(
    "failure",
    [subprocess.TimeoutExpired("tesseract", 1), RuntimeError("exit 1"), FileNotFoundError("x")],
)
def test_engine_failures_are_a_typed_503(failure: Exception) -> None:
    def broken(command: list[str], payload: bytes, timeout: float) -> str:
        raise failure

    recognizer = TesseractRecognizer(runner=broken)
    frame = frame_bytes()
    with pytest.raises(UpstreamUnavailable):
        recognizer.read(frame)


def test_concurrency_is_bounded() -> None:
    active = 0
    peak = 0
    lock = threading.Lock()

    def slow(command: list[str], payload: bytes, timeout: float) -> str:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "x"

    engine = TesseractRecognizer(max_concurrent=2, runner=slow)
    data = frame_bytes()
    threads = [threading.Thread(target=engine.read, args=(data,)) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak <= 2
