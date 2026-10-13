"""A project's code repositories and its documentation check (issue #84).

``GET /api/projects/{id}/repositories`` lists the repositories a project
links; ``POST`` links one and ``POST .../repositories/unlink`` removes one.
``GET .../repositories/commit`` shows one commit with its diff.
``GET /api/projects/{id}/documentation-check`` compares the project's pages
with what changed in those repositories since their last check and writes
nothing; ``POST .../documentation-check/propose`` drafts one suggested
decision, and ``POST .../documentation-check/mark`` records the commit a
check covered. Every write goes through a ``library`` function behind the
write guard of ``write.py``, and an optional ``agent`` marks it as an agent's.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from ..app import json_response
from ..library import (
    ProposedWrite,
    WriteError,
    documentation_check,
    link_repository,
    mark_documentation_checked,
    propose_documentation_decision,
    repository_commit,
    repository_links,
    unlink_repository,
)
from .write import _agent, _field, _result_json, _write_error_response, _write_payload, proposed_json


def _written(result: object, status_code: int = 200) -> Response:
    if isinstance(result, ProposedWrite):
        return json_response(proposed_json(result), status_code=202)
    return json_response(_result_json(result), status_code=status_code)  # type: ignore[arg-type]


async def repositories_view(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    try:
        links = repository_links(request.app.state.workspace, project_id)
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response({"project": project_id, "repositories": links})


async def link_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = link_repository(
            request.app.state.workspace,
            request.path_params["project_id"],
            path=_field(payload, "path", str, required=True),
            remote=_field(payload, "remote", str, required=False) or None,
            agent=_agent(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return _written(result)


async def unlink_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = unlink_repository(
            request.app.state.workspace,
            request.path_params["project_id"],
            path=_field(payload, "path", str, required=True),
            agent=_agent(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return _written(result)


async def check_view(request: Request) -> Response:
    """``?since=<commit>`` (with ``&repository=<path>`` when the project links
    more than one) starts the check at another commit than the checked one."""

    since_commit = request.query_params.get("since")
    since = None
    if since_commit:
        since = {request.query_params.get("repository", ""): since_commit}
    try:
        links = repository_links(request.app.state.workspace, request.path_params["project_id"])
        if since is not None and "" in since:
            if len(links) != 1:
                raise WriteError("bad_request", "since needs repository when the project links more than one")
            since = {links[0]["path"]: since_commit}
        check = documentation_check(request.app.state.workspace, request.path_params["project_id"], since=since)
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(check)


async def propose_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = propose_documentation_decision(
            request.app.state.workspace,
            request.path_params["project_id"],
            path=_field(payload, "repository", str, required=True),
            key=_field(payload, "key", str, required=True),
            agent=_agent(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return _written(result, 201)


async def mark_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        result = mark_documentation_checked(
            request.app.state.workspace,
            request.path_params["project_id"],
            path=_field(payload, "repository", str, required=True),
            commit=_field(payload, "commit", str, required=True),
            agent=_agent(payload),
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return _written(result)


async def commit_view(request: Request) -> Response:
    """``?repository=<path>&commit=<hash>``: one commit with its diff."""

    try:
        repository = request.query_params.get("repository") or ""
        commit = request.query_params.get("commit") or ""
        if not repository or not commit:
            raise WriteError("bad_request", "repository and commit are required")
        details = repository_commit(
            request.app.state.workspace, request.path_params["project_id"], path=repository, commit=commit
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(details)
