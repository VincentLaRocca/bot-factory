"""The one door to the network. Stdlib only, and swappable in tests.

Every listener and sink takes a ``fetch`` callable with this signature, so the
test suite can run the whole system offline against recorded payloads.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Dict, Optional

USER_AGENT = "bot-factory-leads/0.1 (+https://github.com/VincentLaRocca/bot-factory)"


@dataclass
class Response:
    status: int
    body: bytes
    headers: Dict[str, str]

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.text() or "null")


Fetch = Callable[..., Response]


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url.split('?')[0]}: {body[:200]}")
        self.status = status


def fetch(url: str, method: str = "GET", data: Optional[bytes] = None,
          headers: Optional[Dict[str, str]] = None, timeout: float = 30.0,
          retries: int = 2) -> Response:
    """GET/POST with a real User-Agent and polite retry on 429/5xx."""
    request_headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    request_headers.update(headers or {})
    attempt = 0
    while True:
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as reply:
                return Response(reply.status, reply.read(), dict(reply.headers))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code in (429, 500, 502, 503, 504) and attempt < retries:
                attempt += 1
                wait = error.headers.get("Retry-After")
                time.sleep(min(float(wait) if wait and wait.isdigit() else 2 ** attempt, 30))
                continue
            raise HttpError(error.code, url, body) from None
        except urllib.error.URLError:
            if attempt < retries:
                attempt += 1
                time.sleep(2 ** attempt)
                continue
            raise


def post_json(fetcher: Fetch, url: str, payload, content_type: str = "application/json") -> Response:
    body = json.dumps(payload).encode("utf-8")
    return fetcher(url, method="POST", data=body, headers={"Content-Type": content_type})
