"""Proposed changes (issue #86): writes the review rules held back.

- ``GET /api/changes`` lists every proposed change for the Decide inbox,
  oldest first, with the rules' problems when they cannot be read.
- ``GET /api/changes/{id}`` shows one: the new page rendered, or for an edit
  the changed fields and a paragraph diff of the text against the page as it
  is now.
- ``POST /api/changes/{id}/accept`` and ``/discard`` apply or drop it, with
  ``{"expected_sha256": <the proposal file's hash>}``; both commit.
- ``GET /api/review/check?writer=&project=&folder=&writes=`` says whether a
  write would go to review, without writing (the Referat import asks first).
"""

from __future__ import annotations

import hashlib
import posixpath
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from .. import language, markdown, strings
from ..app import get_library, json_response
from ..library import (
    Library,
    LibraryError,
    Proposal,
    ProvenanceEntry,
    WriteError,
    accept_change,
    discard_change,
    editable_source,
    file_resolver,
    path_index,
    proposed_change,
    proposed_changes,
    review_check,
    review_policy,
)
from .common import decision_language, project_title, relative_date, strip_leading_h1
from .decisions import GENERAL, _excerpt
from .record import _diff_blocks, _summarize
from .write import _commit_json, _field, _result_json, _write_error_response, _write_payload

def _entry(proposal: Proposal) -> ProvenanceEntry | None:
    value = proposal.proposed_by
    if not value.get("kind"):
        return None
    captured = value.get("captured")
    return ProvenanceEntry(str(value["kind"]), str(value.get("reference", "")), str(captured) if captured else None, None)


def _place(library: Library, proposal: Proposal) -> tuple[str, str]:
    scope = str(proposal.metadata.get("scope", ""))
    if not scope.startswith("project:"):
        return GENERAL, strings.SCOPE_GENERAL
    project = scope.removeprefix("project:")
    return project, project_title(library, project)


def _current_sha(library: Library, record_id: str) -> str | None:
    record = library.records_by_id.get(record_id)
    if record is None:
        return None
    try:
        return hashlib.sha256(record.abs_path.read_bytes()).hexdigest()
    except OSError:
        return None


def _row(library: Library, proposal: Proposal) -> dict[str, Any]:
    labels = strings.CHANGE_LABELS
    project, project_label = _place(library, proposal)
    proposer = language.proposer_sentence(library, _entry(proposal), proposal.proposed_at)
    when = proposer["when"] or proposal.proposed_at
    record = library.records_by_id.get(proposal.record_id)
    stale = proposal.action == "edit" and _current_sha(library, proposal.record_id) != proposal.base_sha256
    if proposal.action == "create":
        folder = posixpath.dirname(proposal.project_path or "")
        place = f"{project_label} / {folder}" if folder else project_label
        effect = strings.CHANGES_EFFECT_CREATE.format(place=place)
    elif stale:
        effect = strings.CHANGES_STALE.format(title=record.title if record else proposal.title)
    else:
        effect = strings.CHANGES_EFFECT_EDIT.format(title=record.title if record else proposal.title)
    return {
        "id": proposal.id,
        "action": proposal.action,
        "kind_label": strings.CHANGES_NEW_PAGE if proposal.action == "create" else strings.CHANGES_EDIT,
        "title": proposal.title,
        "record": {"id": proposal.record_id, "exists": record is not None, "title": record.title if record else None},
        "excerpt": _excerpt(proposal.body),
        "project": {"id": project, "title": project_label},
        "proposed_by": {"source": proposer["source"], "label": proposer["label"], "kind": proposer["kind"]},
        "proposed_at": when,
        "proposed_display": relative_date(when),
        "proposed_exact": language.format_date(when),
        "rule": proposal.rule,
        "effect": effect,
        "stale": stale,
        "content_sha256": proposal.sha256,
        "actions": {"accept": not stale, "discard": True},
        "outcomes": {
            "accept": (labels["accepted_create"] if proposal.action == "create" else labels["accepted_edit"]).format(
                title=proposal.title
            ),
            "discard": labels["discarded"].format(title=proposal.title),
        },
    }


def changes_payload(library: Library, workspace: Any) -> dict[str, Any]:
    proposals, broken = proposed_changes(workspace)
    try:
        review_policy(workspace)
        policy_error = None
    except WriteError as exc:
        policy_error = strings.CHANGES_POLICY_ERROR.format(error=exc.detail)
    return {
        "heading": strings.CHANGES_HEADING,
        "intro": strings.CHANGES_INTRO,
        "count": len(proposals),
        "items": [_row(library, proposal) for proposal in proposals],
        "broken": [strings.CHANGES_BROKEN.format(path=item.path, error=item.message) for item in broken],
        "policy_error": policy_error,
        "labels": strings.CHANGE_LABELS,
        # The Undo notices' words, shared with decision actions.
        "notice_labels": decision_language()["labels"],
    }


async def list_view(request: Request) -> Response:
    return json_response(changes_payload(get_library(request), request.app.state.workspace))


def _metadata_changes(current: dict[str, Any], proposed: dict[str, Any]) -> list[dict[str, Any]]:
    names = sorted(set(current) | set(proposed))
    return [
        {"field": name, "before": current.get(name), "after": proposed.get(name)}
        for name in names
        if current.get(name) != proposed.get(name)
    ]


async def detail_view(request: Request) -> Response:
    library = get_library(request)
    workspace = request.app.state.workspace
    try:
        proposal = proposed_change(workspace, request.path_params["change_id"])
    except WriteError as exc:
        return _write_error_response(exc)
    row = _row(library, proposal)
    metadata = {key: _plain(value) for key, value in proposal.metadata.items()}
    if proposal.action == "create":
        scope = str(proposal.metadata.get("scope", ""))
        project = scope.removeprefix("project:")
        path = (
            f"projects/{project}/{proposal.project_path or proposal.record_id + '.md'}"
            if scope.startswith("project:")
            else f"{proposal.metadata.get('type', 'knowledge')}/{proposal.record_id}.md"
        )
        row["body_html"] = markdown.render(
            strip_leading_h1(proposal.body),
            source_path=path,
            resolve_link=path_index(library).get,
            resolve_file=file_resolver(workspace),
        )
        row["metadata_changes"] = []
        row["blocks"] = []
        row["summary"] = None
    else:
        record = library.records_by_id.get(proposal.record_id)
        try:
            source = editable_source(record) if record is not None else None
        except (LibraryError, OSError):
            source = None
        current_body = source.raw_body if source is not None else ""
        current_metadata = {key: _plain(value) for key, value in (source.metadata if source is not None else {}).items()}
        proposed_metadata = {key: metadata.get(key, [] if key != "title" else None) for key in current_metadata}
        blocks, counts = _diff_blocks(strip_leading_h1(current_body), strip_leading_h1(proposal.body))
        row["body_html"] = None
        row["metadata_changes"] = _metadata_changes(current_metadata, proposed_metadata)
        row["blocks"] = [{"kind": b.kind, "left_html": b.left_html, "right_html": b.right_html} for b in blocks]
        row["summary"] = _summarize(counts)
    # The Markdown itself, for agents (read_proposed_change) rather than the page.
    row["proposed_markdown"] = proposal.body
    row["current_markdown"] = current_body if proposal.action != "create" else None
    row["labels"] = strings.CHANGE_LABELS
    row["notice_labels"] = decision_language()["labels"]
    return json_response(row)


def _plain(value: Any) -> Any:
    """Frontmatter values as JSON: dates as ISO text."""

    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


async def _act(request: Request, accept: bool) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        expected = _field(payload, "expected_sha256", str, required=False)
        workspace = request.app.state.workspace
        change_id = request.path_params["change_id"]
        if accept:
            return json_response(_result_json(accept_change(workspace, change_id, expected_sha256=expected)))
        discarded = discard_change(workspace, change_id, expected_sha256=expected)
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response({"discarded": discarded.proposal_id, "commit": _commit_json(discarded.commit)})


async def accept_view(request: Request) -> Response:
    return await _act(request, True)


async def discard_view(request: Request) -> Response:
    return await _act(request, False)


async def check_view(request: Request) -> Response:
    params = request.query_params
    writer = params.get("writer") or "person"
    project = params.get("project") or None
    try:
        rule = review_check(
            request.app.state.workspace,
            writer=writer,
            project=None if project == GENERAL else project,
            folder=(params.get("folder") or "").strip("/"),
            write=params.get("writes") or "create",
        )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response({"review": rule is not None, "rule": rule.describe() if rule is not None else None})
