"""Git sync endpoints: ``GET /api/sync/status``, ``POST /api/sync``,
``GET /api/sync/conflicts``, ``POST /api/sync/resolve``, and ``POST
/api/sync/abort``, plus the guided setup (issue #56): ``GET
/api/sync/setup`` and ``POST /api/sync/setup/init``, ``/identity``,
``/check``, and ``/connect``.

They sit behind the same guard as the write API (``write.py``): the GET
routes apply its host and origin checks, the POST routes additionally need
the write token and a JSON body. Git runs in a worker thread so a slow fetch
or push never stalls other requests; the core bounds every Git call with a
timeout and disables credential prompts, and it holds the workspace lock so
a sync never interleaves with a record write.
"""

from __future__ import annotations

from typing import Any

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import json_response
from ..library import (
    GitSyncError,
    SetupStatus,
    SyncStatus,
    WriteError,
    abort_sync,
    resolve_sync_conflict,
    run_sync,
    sync_check_remote,
    sync_conflicts,
    sync_connect_remote,
    sync_set_identity,
    sync_setup_init,
    sync_setup_status,
    sync_status,
)
from .write import _field, _same_machine_error, _write_payload

#: HTTP status per ``GitSyncError.kind``. Remote trouble is 502; a
#: repository state the person must change first is 409.
_STATUS_BY_KIND = {
    "git_missing": 409,
    "not_a_repo": 409,
    "source_repo": 409,
    "no_branch": 409,
    "no_identity": 409,
    "no_upstream": 409,
    "blocked": 409,
    "conflict": 409,
    "no_merge": 409,
    "not_conflicted": 400,
    "lint": 422,
    "auth": 502,
    "network": 502,
    "timeout": 502,
    "rejected": 502,
    "not_found": 502,
    "bad_url": 400,
    "bad_identity": 400,
    "remote_not_empty": 409,
    "wrong_step": 409,
    "failed": 500,
}


def setup_summary(setup: SetupStatus) -> dict[str, Any]:
    """The setup state with its one sentence and the sync bar's label."""

    template = strings.SYNC_SETUP_SENTENCES.get(setup.state)
    sentence = None
    if template is not None:
        sentence = template.format(
            branch=setup.branch or "",
            remote=setup.remote_url or setup.remote or "",
            folder=setup.detail or "",
            detail=setup.detail or "",
        )
    return {"state": setup.state, "sentence": sentence, "label": strings.SYNC_SETUP_BAR.get(setup.state)}


def setup_json(setup: SetupStatus) -> dict[str, Any]:
    return {
        **setup_summary(setup),
        "branch": setup.branch,
        "remote": setup.remote,
        "remote_url": setup.remote_url,
        "identity": setup.identity,
        "language": strings.SYNC_SETUP_LABELS,
    }


async def _current_setup(request: Request) -> SetupStatus:
    return await run_in_threadpool(sync_setup_status, request.app.state.workspace)


def status_json(status: SyncStatus, setup: SetupStatus | None = None) -> dict[str, Any]:
    return {
        "setup": setup_summary(setup) if setup is not None else None,
        "available": status.available,
        "reason": status.reason,
        "detail": status.detail,
        "branch": status.branch,
        "upstream": status.upstream,
        "remotes": list(status.remotes),
        "ahead": status.ahead,
        "behind": status.behind,
        "uncommitted": status.uncommitted,
        "merging": status.merging,
        "conflicts": status.conflicts,
        "last_sync": status.last_sync,
        "identity": status.identity,
        "warnings": list(status.warnings),
    }


async def _current_status(request: Request) -> dict[str, Any]:
    status = await run_in_threadpool(sync_status, request.app.state.workspace)
    return status_json(status, await _current_setup(request))


async def _git_error(request: Request, exc: GitSyncError) -> Response:
    payload: dict[str, Any] = {"error": exc.kind, "detail": exc.message}
    if exc.issues:
        payload["issues"] = [{"path": path, "message": message} for path, message in exc.issues]
    if exc.conflicts:
        payload["conflicts"] = list(exc.conflicts)
    payload["status"] = await _current_status(request)
    return json_response(payload, status_code=_STATUS_BY_KIND.get(exc.kind, 500))


async def status_view(request: Request) -> Response:
    refused = _same_machine_error(request)
    if refused is not None:
        return refused
    return json_response(await _current_status(request))


async def sync_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        outcome = await run_in_threadpool(run_sync, request.app.state.workspace)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return json_response(
        {
            "state": outcome.state,
            "pulled": outcome.pulled,
            "pushed": outcome.pushed,
            "reindexed": outcome.reindexed,
            "index_error": outcome.index_error,
            "status": await _current_status(request),
        }
    )


async def conflicts_view(request: Request) -> Response:
    refused = _same_machine_error(request)
    if refused is not None:
        return refused
    try:
        files = await run_in_threadpool(sync_conflicts, request.app.state.workspace)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return json_response(
        {
            "files": [
                {
                    "path": item.path,
                    "ours": item.ours,
                    "theirs": item.theirs,
                    "working": item.working,
                    "binary": item.binary,
                    "resolved": item.resolved,
                }
                for item in files
            ],
            "status": await _current_status(request),
        }
    )


async def resolve_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        path = _field(payload, "path", str, required=True)
        choice = _field(payload, "choice", str, required=True)
        content = _field(payload, "content", str, required=False)
    except WriteError as exc:
        return json_response({"error": exc.kind, "detail": exc.detail}, status_code=400)
    if choice not in {"ours", "theirs", "merged"}:
        return json_response({"error": "bad_request", "detail": "choice must be ours, theirs, or merged"}, status_code=400)
    if choice == "merged" and content is None:
        return json_response({"error": "bad_request", "detail": "a merged resolution needs content"}, status_code=400)
    try:
        outcome = await run_in_threadpool(resolve_sync_conflict, request.app.state.workspace, path, choice, content)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return json_response(
        {
            "path": outcome.path,
            "remaining": list(outcome.remaining),
            "issues": [{"path": item_path, "message": message} for item_path, message in outcome.issues],
            "status": await _current_status(request),
        }
    )


async def abort_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        await run_in_threadpool(abort_sync, request.app.state.workspace)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return json_response({"status": await _current_status(request)})


# ---------------------------------------------------------------------------
# Guided setup (issue #56)
# ---------------------------------------------------------------------------


async def _setup_response(request: Request, extra: dict[str, Any]) -> Response:
    return json_response(
        {**extra, "setup": setup_json(await _current_setup(request)), "status": await _current_status(request)}
    )


async def setup_view(request: Request) -> Response:
    refused = _same_machine_error(request)
    if refused is not None:
        return refused
    return json_response(setup_json(await _current_setup(request)))


def _identity_fields(payload: dict[str, Any], *, required: bool) -> tuple[str, str] | None:
    name = _field(payload, "name", str, required=required)
    email = _field(payload, "email", str, required=required)
    if name is None and email is None:
        return None
    return (name or "", email or "")


async def setup_init_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        identity = _identity_fields(payload, required=False)
    except WriteError as exc:
        return json_response({"error": exc.kind, "detail": exc.detail}, status_code=400)
    try:
        outcome = await run_in_threadpool(sync_setup_init, request.app.state.workspace, identity)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return await _setup_response(
        request, {"created_repository": outcome.created_repository, "files": outcome.files, "sha": outcome.sha}
    )


async def setup_identity_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        name, email = _identity_fields(payload, required=True) or ("", "")
    except WriteError as exc:
        return json_response({"error": exc.kind, "detail": exc.detail}, status_code=400)
    try:
        identity = await run_in_threadpool(sync_set_identity, request.app.state.workspace, name, email)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return await _setup_response(request, {"identity": identity})


async def setup_check_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        url = _field(payload, "url", str, required=False)
    except WriteError as exc:
        return json_response({"error": exc.kind, "detail": exc.detail}, status_code=400)
    try:
        check = await run_in_threadpool(sync_check_remote, request.app.state.workspace, url)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    return await _setup_response(
        request,
        {
            "check": {
                "url": check.url,
                "empty": check.empty,
                "branches": list(check.branches),
                "branch": check.branch,
                "related": check.related,
            }
        },
    )


async def setup_connect_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        url = _field(payload, "url", str, required=False)
    except WriteError as exc:
        return json_response({"error": exc.kind, "detail": exc.detail}, status_code=400)
    try:
        outcome = await run_in_threadpool(sync_connect_remote, request.app.state.workspace, url)
    except GitSyncError as exc:
        return await _git_error(request, exc)
    synced = outcome.sync
    return await _setup_response(
        request,
        {
            "state": outcome.state,
            "remote": outcome.remote,
            "branch": outcome.branch,
            "pushed": outcome.pushed,
            "pulled": synced.pulled if synced is not None else 0,
            "reindexed": synced.reindexed if synced is not None else False,
            "index_error": synced.index_error if synced is not None else None,
        },
    )
