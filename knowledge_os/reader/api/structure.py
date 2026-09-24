"""Structure endpoints: create projects and folders, move and rename pages
and folders.

- ``POST /api/projects`` creates a project's overview.
- ``POST /api/projects/{project_id}/folders`` creates a folder (its
  ``README.md`` page).
- ``POST /api/projects/{project_id}/folders/move`` moves and/or renames a
  folder with everything in it.
- ``POST /api/records/{record_id}/move`` moves one page.
- ``POST /api/records/{record_id}/rename`` gives one page a new title.

Each calls one ``library`` function, which calls the core's ``structure``
mutation and commits every touched path as one commit. The guard, JSON
parsing, and error mapping are ``write.py``'s.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from ..app import json_response
from ..library import (
    StructureWriteResult,
    WriteError,
    create_folder,
    create_project,
    move_folder,
    move_page,
    rename_page,
)
from .write import _commit_json, _field, _write_error_response, _write_payload


def _structure_json(result: StructureWriteResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "title": result.title,
        "status": result.status,
        "path": result.path,
        "content_sha256": result.content_sha256,
        "project": result.project,
        "folder": result.folder,
        "scope_changed": result.scope_changed,
        "changed": [
            {"id": item.id, "old_path": item.old_path, "path": item.path, "content_sha256": item.sha256}
            for item in result.changed
        ],
        "index": {"refreshed": result.index_refreshed, "count": result.index_count, "error": result.index_error},
        "commit": _commit_json(result.commit),
    }


def _expected(payload: dict[str, Any]) -> dict[str, str] | None:
    """The optional ``expected`` object: ``{workspace-relative path: sha256}``
    for files the caller read and wants unchanged."""

    value = _field(payload, "expected", dict, required=False)
    if value is None:
        return None
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise WriteError("bad_request", "expected must map file paths to sha256 strings")
    return value


async def create_project_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = create_project(
            request.app.state.workspace,
            project_id=_field(payload, "id", str, required=True),
            title=_field(payload, "title", str, required=True),
            description=_field(payload, "description", str, required=False),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result), status_code=201)


async def create_folder_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = create_folder(
            request.app.state.workspace,
            project_id=request.path_params["project_id"],
            path=_field(payload, "path", str, required=True),
            title=_field(payload, "title", str, required=True),
            record_id=_field(payload, "id", str, required=False),
            description=_field(payload, "description", str, required=False),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result), status_code=201)


async def move_folder_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = move_folder(
            request.app.state.workspace,
            request.path_params["project_id"],
            _field(payload, "path", str, required=True),
            to_project=_field(payload, "to_project", str, required=False),
            to_parent=_field(payload, "to_parent", str, required=False),
            name=_field(payload, "name", str, required=False),
            title=_field(payload, "title", str, required=False),
            allow_scope_change=_field(payload, "allow_scope_change", bool, required=False) or False,
            expected=_expected(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result))


async def move_page_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = move_page(
            request.app.state.workspace,
            request.path_params["record_id"],
            expected_sha256=_field(payload, "expected_sha256", str, required=True),
            folder=_field(payload, "folder", str, required=True),
            project=_field(payload, "project", str, required=False),
            allow_scope_change=_field(payload, "allow_scope_change", bool, required=False) or False,
            expected=_expected(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result))


async def rename_page_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = rename_page(
            request.app.state.workspace,
            request.path_params["record_id"],
            expected_sha256=_field(payload, "expected_sha256", str, required=True),
            title=_field(payload, "title", str, required=True),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result))
