"""A small JSON client for the running core's local API.

Requests go to ``127.0.0.1`` only (the core refuses any other ``Host``),
send no ``Origin``, and carry the write token from the runtime file on
writes, the same way the desktop app's Referat plugin talks to the core.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .runtime import AppUnavailable, RuntimeInfo

WRITE_TOKEN_HEADER = "X-KOS-Write-Token"
_TIMEOUT = 60.0  # a write validates the corpus, rebuilds the index, and commits


class LocalApi:
    def __init__(self, info: RuntimeInfo):
        self.info = info

    def get(self, path: str, query: dict[str, str] | None = None) -> tuple[int, Any]:
        if query:
            path = f"{path}?{urllib.parse.urlencode(query)}"
        return self._send("GET", path, None)

    def post(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        return self._send("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> tuple[int, Any]:
        return self._send("PATCH", path, payload)

    def _send(self, method: str, path: str, payload: dict[str, Any] | None) -> tuple[int, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.info.base_url + path, data=data, method=method)
        if payload is not None:
            request.add_header("Content-Type", "application/json")
            request.add_header(WRITE_TOKEN_HEADER, self.info.write_token)
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                return response.status, _json(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, _json(exc.read())
        except (urllib.error.URLError, OSError) as exc:
            raise AppUnavailable(
                "request_failed", f"The Knowledge OS app stopped answering during the request: {exc}"
            ) from None


def quote(value: str) -> str:
    """One path segment, such as a record id."""

    return urllib.parse.quote(value, safe="")


def _json(raw: bytes) -> Any:
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return {"detail": raw.decode("utf-8", "replace")[:500]}
