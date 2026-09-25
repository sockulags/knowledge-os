"""Structure endpoints: create projects and folders, move and rename pages
and folders.

- ``POST /api/projects`` creates a project's overview.
- ``POST /api/projects/{project_id}/folders`` creates a folder (its
  ``README.md`` page).
- ``POST /api/projects/{project_id}/folders/move`` moves and/or renames a
  folder with everything in it.
- ``POST /api/records/{record_id}/move`` moves one page.
- ``POST /api/records/{record_id}/rename`` gives one page a new title.
- ``GET /api/records/{record_id}/delete-preview`` and ``GET
  /api/projects/{project_id}/folders/delete-preview?path=...`` describe a
  deletion for its confirmation dialog without writing anything;
  ``POST /api/records/{record_id}/delete`` and ``POST
  /api/projects/{project_id}/folders/delete`` carry it out.

Each calls one ``library`` function, which calls the core's ``structure``
mutation and commits every touched path as one commit. The guard, JSON
parsing, and error mapping are ``write.py``'s.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import json_response
from ..library import (
    DeletePlan,
    StructureWriteResult,
    WriteError,
    create_folder,
    create_project,
    delete_folder,
    delete_page,
    folder_deletion_plan,
    move_folder,
    move_page,
    page_deletion_plan,
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
        "deleted": list(result.deleted),
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


# ---------------------------------------------------------------------------
# Delete a page or a folder (issue #78)
# ---------------------------------------------------------------------------


def _deletion_json(plan: DeletePlan) -> dict[str, Any]:
    """A deletion preview with the confirmation dialog's finished text.

    ``records`` are the pages removed, ``other_files`` counts the other
    files removed with a folder, ``cleaned`` the pages whose Related or
    Sources lose the reference, ``linked`` the pages whose text links to
    what is removed (left as they are), and ``blockers`` why it cannot be
    deleted. ``expected`` goes back unchanged with the delete request.
    """

    labels = strings.DELETE_LABELS
    folder = plan.kind == "folder"
    page_paths = {record.path for record in plan.records}
    other_files = len([path for path in plan.files if path not in page_paths])
    notes: list[str] = []
    if not folder and plan.records and plan.records[0].record_kind == "decision":
        if plan.records[0].status == "draft":
            notes.append(labels["decision_draft"])
        elif plan.records[0].status == "archived":
            notes.append(labels["decision_withdrawn"])
    if other_files:
        other = (
            labels["folder_other_files_one"]
            if other_files == 1
            else labels["folder_other_files"].format(count=other_files)
        )
    else:
        other = None
    blockers = [
        strings.DELETE_BLOCKERS.get(blocker.kind, blocker.message()).format(
            title=blocker.title, other=blocker.other_title or blocker.other_id or ""
        )
        for blocker in plan.blockers
    ]
    return {
        "kind": plan.kind,
        "id": plan.id,
        "title": plan.title,
        "project": plan.project,
        "folder": plan.folder,
        "path": plan.path,
        "deletable": plan.deletable,
        "records": [{"id": record.id, "title": record.title, "path": record.path} for record in plan.records],
        "other_files": other_files,
        "cleaned": [
            {"id": item.id, "title": item.title, "path": item.path, "fields": list(item.fields)}
            for item in plan.referrers
            if item.fields
        ],
        "linked": [{"id": item.id, "title": item.title, "path": item.path} for item in plan.referrers if item.links],
        "blockers": blockers,
        "expected": dict(plan.expected),
        "dialog": {
            "title": labels["folder_title" if folder else "page_title"].format(title=plan.title),
            "intro": labels["folder_intro" if folder else "page_intro"].format(title=plan.title),
            "other_files": other,
            "notes": notes,
            "cleaned_heading": labels["cleaned_heading"],
            "linked_heading": labels["linked_heading"],
            "nothing_refers": labels["nothing_refers"],
            "blocked_heading": labels["blocked_heading"],
            "history": labels["history"],
            "confirm": labels["confirm_folder" if folder else "confirm_page"],
            "cancel": labels["cancel"],
            "close": labels["close"],
            "working": labels["working"],
            "done": labels["done_folder" if folder else "done_page"].format(title=plan.title),
            "failed": labels["failed"],
        },
    }


async def delete_page_preview_view(request: Request) -> Response:
    try:
        plan = page_deletion_plan(request.app.state.workspace, request.path_params["record_id"])
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_deletion_json(plan))


async def delete_folder_preview_view(request: Request) -> Response:
    path = request.query_params.get("path")
    if not path:
        return _write_error_response(WriteError("bad_request", "path is required"))
    try:
        plan = folder_deletion_plan(request.app.state.workspace, request.path_params["project_id"], path)
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_deletion_json(plan))


async def delete_page_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = delete_page(
            request.app.state.workspace,
            request.path_params["record_id"],
            expected_sha256=_field(payload, "expected_sha256", str, required=True),
            expected=_expected(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result))


async def delete_folder_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = delete_folder(
            request.app.state.workspace,
            request.path_params["project_id"],
            _field(payload, "path", str, required=True),
            expected=_expected(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_structure_json(result))
