"""The HTTP side of key retrieval, against a real local server."""

import http.server
import json
import threading
from collections.abc import Iterator

import pytest

from mtgvault.adapters.auth.deny_all import DenyAllTokenVerifier
from mtgvault.adapters.auth.jwks import ProviderUnreachable, httpx_json_fetcher
from mtgvault.domain.errors import Unauthenticated


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        routes = {
            "/ok": (200, json.dumps({"keys": []})),
            "/list": (200, json.dumps([1, 2])),
            "/broken": (200, "not json"),
            "/missing": (404, "{}"),
            "/redirect": (302, ""),
        }
        code, body = routes.get(self.path, (404, "{}"))
        self.send_response(code)
        if code == 302:
            self.send_header("Location", "/ok")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture(scope="module")
def base() -> Iterator[str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_a_json_object_is_returned(base: str) -> None:
    assert httpx_json_fetcher()(f"{base}/ok") == {"keys": []}


@pytest.mark.parametrize("path", ["/list", "/broken", "/missing", "/redirect"])
def test_anything_else_is_reported_as_unreachable(base: str, path: str) -> None:
    fetch = httpx_json_fetcher()
    url = f"{base}{path}"
    with pytest.raises(ProviderUnreachable):
        fetch(url)


def test_an_unreachable_host_is_reported_not_raised_raw() -> None:
    fetch = httpx_json_fetcher(timeout=0.5)
    with pytest.raises(ProviderUnreachable):
        fetch("http://127.0.0.1:1/x")


def test_deny_all_rejects_everything() -> None:
    verifier = DenyAllTokenVerifier()
    with pytest.raises(Unauthenticated):
        verifier.verify("anything")
