"""A Scryfall-shaped server for tests (issue #77). Never shipped in an image.

Serves the recorded fixtures of ``tests/fixtures/scryfall`` for ``/cards/search`` and
``/cards/{id}``, records every request (path, query, headers, time) and can fail on demand.
In-process for pytest (``ScryfallDouble().start()``) or standalone for the E2E stack::

    python tests/support/scryfall_double.py --port 9100

``POST /cards/collection`` answers like the real service: at most 75 identifiers (422 above),
``data`` for the known ids and ``not_found`` for the others.

``POST /__control`` (JSON): ``{"fail": 503}`` (any status; ``0`` heals), ``{"retry_after": 2}``
(sent with 429), ``{"delay": 1.5}`` (seconds before every answer), ``{"garbage": true}`` (200 with
a body that is not JSON), ``{"prices": {"<card id>": {"usd": "9.99", "eur": null}}}`` (new prices
for a card, in every later answer), ``{"reset": true}`` (also forgets the prices).
``GET /__requests`` returns the request log (``method`` and, for the collection, ``identifiers``).
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "scryfall"
MAX_COLLECTION = 75
NOT_FOUND = {"object": "error", "code": "not_found", "status": 404, "details": "No cards found."}


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))  # type: ignore[no-any-return]


class ScryfallDouble:
    def __init__(self, port: int = 0, host: str = "127.0.0.1") -> None:
        self._lock = threading.Lock()
        self.requests: list[dict[str, Any]] = []
        self.reset()
        self._cards: dict[str, dict[str, Any]] = {}
        for name in (
            "search_lightning_bolt.json",
            "search_tokens.json",
            "printings_lightning_bolt.json",
        ):
            for card in _load(name)["data"]:
                self._cards[card["id"]] = card
        for name in (
            "card_transform_delver.json",
            "card_split_fire_ice.json",
            "card_foil_only_no_prices.json",
        ):
            card = _load(name)
            self._cards[card["id"]] = card
        self._server = ThreadingHTTPServer((host, port), _handler(self))
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"

    def reset(self) -> None:
        with self._lock:
            self.fail, self.retry_after, self.delay, self.garbage = 0, 0, 0.0, False
            self.price_overrides: dict[str, dict[str, Any]] = {}
            self.requests.clear()

    def control(self, change: dict[str, Any]) -> None:
        if change.get("reset"):
            self.reset()
            return
        with self._lock:
            self.fail = int(change.get("fail", self.fail))
            self.retry_after = int(change.get("retry_after", self.retry_after))
            self.delay = float(change.get("delay", self.delay))
            self.garbage = bool(change.get("garbage", self.garbage))
            for card_id, prices in (change.get("prices") or {}).items():
                self.price_overrides.setdefault(card_id, {}).update(prices)

    def start(self) -> ScryfallDouble:
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # ------------------------------------------------------------------ data
    def search(self, query: str) -> dict[str, Any]:
        lowered = query.lower()
        if lowered.startswith("oracleid:"):
            return _load("printings_lightning_bolt.json")
        if "treasure" in lowered or "token" in lowered:
            return _load("search_tokens.json")
        if "bolt" in lowered:
            return _load("search_lightning_bolt.json")
        return NOT_FOUND

    def card(self, card_id: str) -> dict[str, Any] | None:
        card = self._cards.get(card_id)
        if card is None:
            return None
        with self._lock:
            overrides = dict(self.price_overrides.get(card_id, {}))
        if not overrides:
            return card
        return {**card, "prices": {**(card.get("prices") or {}), **overrides}}

    def collection(self, identifiers: list[dict[str, str]]) -> dict[str, Any]:
        found, missing = [], []
        for identifier in identifiers:
            card = self.card(str(identifier.get("id")))
            if card is None:
                missing.append(identifier)
            else:
                found.append(card)
        return {"object": "list", "not_found": missing, "data": found}


def _handler(double: ScryfallDouble) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "scryfall-double"
        sys_version = ""

        def _send(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, document: Any, headers: dict[str, str] | None = None) -> None:
            self._send(status, json.dumps(document).encode(), headers)

        def _gate(
            self, method: str, path: str, query: dict[str, str], extra: dict[str, Any]
        ) -> bool:
            """Logs the request and applies the failure controls; True when it was answered."""
            with double._lock:
                double.requests.append(
                    {
                        "method": method,
                        "path": path,
                        "query": query,
                        "user_agent": self.headers.get("User-Agent"),
                        "accept": self.headers.get("Accept"),
                        "at": time.monotonic(),
                        **extra,
                    }
                )
                fail, retry_after, delay, garbage = (
                    double.fail,
                    double.retry_after,
                    double.delay,
                    double.garbage,
                )
            if delay:
                time.sleep(delay)
            if fail:
                headers = {"Retry-After": str(retry_after)} if fail == 429 and retry_after else None
                self._json(fail, {"object": "error", "status": fail}, headers)
                return True
            if garbage:
                self._send(200, b"<html>not json</html>")
                return True
            return False

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) or b"{}"
            if path == "/__control":
                double.control(json.loads(raw))
                self._json(200, {"ok": True})
                return
            if path != "/cards/collection":
                self._json(404, NOT_FOUND)
                return
            try:
                identifiers = list(json.loads(raw)["identifiers"])
            except (ValueError, KeyError, TypeError):
                self._json(422, {"object": "error", "status": 422, "details": "Bad body."})
                return
            if self._gate("POST", path, {}, {"identifiers": len(identifiers)}):
                return
            if len(identifiers) > MAX_COLLECTION:
                self._json(422, {"object": "error", "status": 422, "details": "Too many."})
                return
            self._json(200, double.collection(identifiers))

        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(parts.query).items()}
            if parts.path == "/__requests":
                with double._lock:
                    self._json(200, list(double.requests))
                return
            if self._gate("GET", parts.path, query, {}):
                return
            if parts.path == "/cards/search":
                document = double.search(query.get("q", ""))
                self._json(404 if document.get("object") == "error" else 200, document)
            elif parts.path.startswith("/cards/"):
                card = double.card(parts.path.rsplit("/", 1)[-1])
                self._json(200 if card else 404, card or NOT_FOUND)
            else:
                self._json(404, NOT_FOUND)

        def log_message(self, *_: object) -> None:
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Scryfall test double")
    parser.add_argument("--port", type=int, default=9100)
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104  # inside a test container
    args = parser.parse_args()
    double = ScryfallDouble(args.port, args.host)
    print(f"Scryfall double on port {double.port}", flush=True)
    double._server.serve_forever()


if __name__ == "__main__":
    main()
