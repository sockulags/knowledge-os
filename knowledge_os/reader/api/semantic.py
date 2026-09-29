"""Search by meaning (issue #102): ``GET /api/semantic`` reports where it
stands, ``POST /api/semantic/install`` downloads the search model,
``POST /api/semantic/refresh`` brings the semantic index up to date, and
``POST /api/semantic/remove`` deletes the model.

The model lives outside the knowledge base (see ``knowledge_os.semantic``)
and the index is a disposable file under ``indexes/``. Serving a page never
writes it: only these POST endpoints, behind the write API's guard, start the
background work, and the UI asks for a refresh when a search reports the
index as ``stale``.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import json_response
from ..library import SemanticStatus, install_semantic_model, refresh_semantic_index, remove_semantic_model, semantic_status
from .write import _write_payload


def _json(status: SemanticStatus) -> dict[str, Any]:
    message = strings.SEMANTIC_STATE_MESSAGES.get(status.state, "").format(size=status.size)
    return {
        "state": status.state,
        "message": message,
        "size": status.size,
        "done_bytes": status.done_bytes,
        "total_bytes": status.total_bytes,
        "error": strings.SEMANTIC_INSTALL_FAILED.format(error=status.error) if status.error else None,
        "install_label": strings.SEMANTIC_INSTALL_LABEL,
        "match_hint": strings.SEARCH_MATCH_MEANING_HINT,
    }


def semantic_json(workspace: Any) -> dict[str, Any]:
    return _json(semantic_status(workspace))


async def status_view(request: Request) -> Response:
    return json_response(semantic_json(request.app.state.workspace))


async def install_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    return json_response(_json(install_semantic_model(request.app.state.workspace)))


async def refresh_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    return json_response(_json(refresh_semantic_index(request.app.state.workspace)))


async def remove_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    remove_semantic_model()
    return json_response(semantic_json(request.app.state.workspace))
