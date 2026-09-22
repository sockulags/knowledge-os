"""Write endpoints: ``POST /api/records`` (create) and ``PATCH
/api/records/{record_id}`` (edit), plus ``GET /api/session``, which hands the
UI the per-process write token.

Every write goes through ``library.create_record``/``library.edit_record``,
which call the core's own capture and update mutations. This module only
checks where a request comes from, parses JSON, and maps
``library.WriteError.kind`` to an HTTP status. Decision lifecycle actions
(accept, withdraw, supersede) are meant to follow the same pattern as
``POST /api/records/{record_id}/<action>`` with ``expected_sha256`` in the
body.

Cross-site protection for a server that binds to loopback only: a write must
be addressed to a loopback ``Host`` (defeats DNS rebinding), must not carry a
foreign ``Origin`` or ``Sec-Fetch-Site: cross-site``, must be
``application/json``, and must carry the ``X-KOS-Write-Token`` header with
this process's random token. A web page on another origin can neither set
that header without a CORS preflight this server never grants nor read the
token from ``GET /api/session``, since no response carries CORS headers.
"""

from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import Response

from ..app import json_response
from ..library import WriteError, WriteResult, create_record, edit_record

WRITE_TOKEN_HEADER = "X-KOS-Write-Token"
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

_STATUS_BY_KIND = {
    "bad_request": 400,
    "forbidden": 403,
    "not_found": 404,
    "conflict": 409,
    "duplicate": 409,
    "validation": 422,
}


def new_write_token() -> str:
    return secrets.token_urlsafe(32)


def _error(kind: str, detail: str, **extra: Any) -> Response:
    return json_response({"error": kind, "detail": detail, **extra}, status_code=_STATUS_BY_KIND[kind])


def _is_loopback_host(value: str | None) -> bool:
    if not value:
        return False
    hostname = urlsplit(f"//{value}").hostname
    return hostname in _LOOPBACK_HOSTS


def _is_loopback_origin(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in {"http", "https"} and parts.hostname in _LOOPBACK_HOSTS


def _same_machine_error(request: Request) -> Response | None:
    """Refuse requests that a page on another site could have caused."""

    if not _is_loopback_host(request.headers.get("host")):
        return _error("forbidden", "requests must address this server by a loopback host name")
    origin = request.headers.get("origin")
    if origin is not None and not _is_loopback_origin(origin):
        return _error("forbidden", "cross-origin requests may not use this endpoint")
    if request.headers.get("sec-fetch-site") == "cross-site":
        return _error("forbidden", "cross-site requests may not use this endpoint")
    return None


async def _write_payload(request: Request) -> dict[str, Any] | Response:
    """Guard one write request, then parse its JSON object body."""

    refused = _same_machine_error(request)
    if refused is not None:
        return refused
    token = request.headers.get(WRITE_TOKEN_HEADER, "")
    if not secrets.compare_digest(token.encode(), request.app.state.write_token.encode()):
        return _error("forbidden", f"missing or wrong {WRITE_TOKEN_HEADER} header; read it from GET /api/session")
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "application/json":
        return _error("bad_request", "request body must be application/json")
    try:
        payload = json.loads(await request.body())
    except (ValueError, UnicodeDecodeError):
        return _error("bad_request", "request body is not valid JSON")
    if not isinstance(payload, dict):
        return _error("bad_request", "request body must be a JSON object")
    return payload


_JSON_NAMES = {dict: "object", str: "string", bool: "boolean"}


def _field(payload: dict[str, Any], name: str, kind: type, *, required: bool) -> Any:
    if payload.get(name) is None:
        if required:
            raise WriteError("bad_request", f"{name} is required")
        return None
    value = payload[name]
    if not isinstance(value, kind):
        raise WriteError("bad_request", f"{name} must be a JSON {_JSON_NAMES[kind]}")
    return value


def _result_json(result: WriteResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "status": result.status,
        "path": result.path,
        "content_sha256": result.content_sha256,
        "index": {
            "refreshed": result.index_refreshed,
            "count": result.index_count,
            "error": result.index_error,
        },
    }


def _write_error_response(exc: WriteError) -> Response:
    extra: dict[str, Any] = {}
    if exc.issues:
        extra["issues"] = [{"path": path, "message": message} for path, message in exc.issues]
    if exc.current_sha256 is not None:
        extra["current_sha256"] = exc.current_sha256
    return _error(exc.kind, exc.detail, **extra)


async def session_view(request: Request) -> Response:
    refused = _same_machine_error(request)
    if refused is not None:
        return refused
    return json_response({"write_token": request.app.state.write_token, "write_token_header": WRITE_TOKEN_HEADER})


async def create_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        metadata = _field(payload, "metadata", dict, required=True)
        body = _field(payload, "body", str, required=True)
        project_path = _field(payload, "project_path", str, required=False)
        result = create_record(
            request.app.state.workspace,
            metadata=metadata,
            body=body,
            project_path=project_path,
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_result_json(result), status_code=201)


async def edit_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        expected = _field(payload, "expected_sha256", str, required=True)
        changes = _field(payload, "metadata", dict, required=False) or {}
        body = _field(payload, "body", str, required=False)
        confirm = _field(payload, "confirm_non_material", bool, required=False) or False
        reference = _field(payload, "change_reference", str, required=False)
        result = edit_record(
            request.app.state.workspace,
            request.path_params["record_id"],
            expected_sha256=expected,
            changes=changes,
            body=body,
            confirm_non_material=confirm,
            change_reference=reference,
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_result_json(result))
