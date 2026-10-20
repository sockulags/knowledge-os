"""``GET /api/discoveries/pending`` — observations waiting for review, for
Decide: every proposed (unreviewed) discovery, newest first, with the review
packet ``kos discovery review`` prints, the pages it may overlap with, and the
commands and agent request that review it.

``POST /api/discoveries/{id}/retain``, ``/reject``, and ``/promote`` are the
person's review, with the same fields as ``kos discovery retain|reject|
promote`` takes flags (``reason``, ``reviewer``, ``target_id``, ``title``,
``scope``, ``acknowledge_related``, ``allow_scope_broadening``) plus
``expected_sha256``, the observation as it was shown. They call the same core
functions the CLI does, answer with what its ``--json`` prints plus the
commit, and refuse any request labelled with ``agent``: deciding what an
observation becomes is a trust-boundary crossing only a person makes.

When the corpus or search index cannot produce the packets, the rows still
list every waiting observation, without packets, and ``error`` says why.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from .. import language, markdown, strings
from ..app import get_library, json_response
from ..library import (
    DiscoveryWriteResult,
    Library,
    PendingDiscovery,
    Record,
    WriteError,
    content_sha256,
    pending_discoveries,
    promote_observation,
    reject_observation,
    retain_observation,
    suggest_record_id,
)
from .common import decision_language, pill_for, project_id_for_scope, project_title, relative_date
from .decisions import GENERAL, _excerpt
from .write import _commit_json, _error, _field, _write_error_response, _write_payload, blocking


def _command(root: str, record_id: str, arguments: str) -> str:
    return f'python -m knowledge_os --root "{root}" discovery {arguments.format(id=record_id)}'


def _commands(library: Library, record: Record, details: PendingDiscovery | None) -> list[dict[str, str]]:
    root = str(library.workspace_root)
    commands: list[dict[str, str]] = []
    # General-scope observations cannot be retained, only rejected or promoted.
    if record.scope != "general":
        commands.append({"action": "retain", "command": _command(root, record.id, "retain {id}")})
    commands.append({"action": "reject", "command": _command(root, record.id, 'reject {id} --reason "<why>"')})
    title = record.title.replace('"', "'")
    promote = f'promote {{id}} --target-id <new-id> --title "{title}" --scope {record.scope}'
    if details is None or details.related:
        promote += " --acknowledge-related"
    commands.append({"action": "promote", "command": _command(root, record.id, promote)})
    labels = strings.OBSERVATIONS_LABELS
    return [{"label": labels[item["action"]], **item} for item in commands]


def _row(library: Library, record: Record, details: PendingDiscovery | None) -> dict[str, object]:
    bucket = project_id_for_scope(record.scope) or GENERAL
    proposer = language.proposed_by(library, record)
    when = proposer["when"]
    related = None
    if details is not None:
        related = [
            {
                "id": item.id,
                "title": item.title,
                "reasons": list(item.reasons),
                "exists": item.id in library.records_by_id,
            }
            for item in details.related
        ]
    return {
        "id": record.id,
        "title": record.title,
        "excerpt": _excerpt(record.body),
        "project": {
            "id": bucket,
            "title": strings.SCOPE_GENERAL if bucket == GENERAL else project_title(library, bucket),
        },
        "proposed_by": {"source": proposer["source"], "label": proposer["label"]},
        "proposed_display": relative_date(when),
        "proposed_exact": language.format_date(when),
        "trust": strings.OBSERVATIONS_TRUST,
        "status_pill": pill_for(record),
        "related": related,
        "packet_html": markdown.render(details.packet) if details is not None else None,
        "agent_phrase": strings.OBSERVATIONS_AGENT_PHRASE.format(id=record.id),
        "commands": _commands(library, record, details),
        "content_sha256": content_sha256(record.abs_path),
        "scope": record.scope,
        "actions": {
            # The core refuses to retain a general-scope observation.
            "retain": record.scope != "general",
            "promote": {
                "target_id": suggest_record_id(library, record.title),
                "title": record.title,
                # Promotion needs --acknowledge-related when it found related pages.
                "acknowledge_related": bool(details is not None and details.related),
                # A project observation may become general knowledge only with
                # --allow-scope-broadening; a general one has nothing to broaden.
                "allow_scope_broadening": record.scope != "general",
            },
        },
    }


async def pending_view(request: Request) -> Response:
    library = get_library(request)
    details, error = pending_discoveries(request.app.state.workspace)
    by_id = {item.id: item for item in details}
    if error is None:
        records = [library.records_by_id[item.id] for item in details if item.id in library.records_by_id]
    else:
        records = sorted(
            (r for r in library.records if r.type == "discovery" and r.status == "proposed"), key=lambda r: r.id
        )
        records.sort(key=lambda r: r.created, reverse=True)
    count = len(records)
    count_label = None
    if count == 1:
        count_label = strings.OBSERVATIONS_COUNT_SINGULAR
    elif count > 1:
        count_label = strings.OBSERVATIONS_COUNT_PLURAL.format(count=count)
    return json_response(
        {
            "heading": strings.OBSERVATIONS_HEADING,
            "intro": strings.OBSERVATIONS_INTRO,
            "count": count,
            "count_label": count_label,
            "error": strings.OBSERVATIONS_UNAVAILABLE.format(error=error) if error is not None and count else None,
            "items": [_row(library, record, by_id.get(record.id)) for record in records],
            "labels": strings.OBSERVATIONS_LABELS,
            "notice_labels": decision_language()["labels"],
        }
    )


def _result_json(result: DiscoveryWriteResult) -> dict[str, Any]:
    body: dict[str, Any] = {"id": result.id, "status": result.status}
    if result.status == "promoted":
        body["target_id"] = result.target_id
        body["acknowledged_related"] = list(result.acknowledged_related)
    body["index_count"] = result.index_count
    body["index_error"] = result.index_error
    body["commit"] = _commit_json(result.commit)
    return body


async def _review(request: Request, action: str) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    if "agent" in payload:
        return _error("forbidden", strings.OBSERVATIONS_AGENT_REFUSED)
    workspace = request.app.state.workspace
    record_id = request.path_params["record_id"]
    try:
        expected = _field(payload, "expected_sha256", str, required=True)
        reviewer = _field(payload, "reviewer", str, required=False)
        reason = _field(payload, "reason", str, required=action == "reject")
        if action == "retain":
            result = await blocking(
                retain_observation, workspace, record_id, expected_sha256=expected, reason=reason, reviewer=reviewer
            )
        elif action == "reject":
            result = await blocking(
                reject_observation, workspace, record_id, expected_sha256=expected, reason=reason, reviewer=reviewer
            )
        else:
            result = await blocking(
                promote_observation,
                workspace,
                record_id,
                expected_sha256=expected,
                target_id=_field(payload, "target_id", str, required=True),
                title=_field(payload, "title", str, required=True),
                scope=_field(payload, "scope", str, required=True),
                reason=reason,
                reviewer=reviewer,
                acknowledge_related=_field(payload, "acknowledge_related", bool, required=False) or False,
                allow_scope_broadening=_field(payload, "allow_scope_broadening", bool, required=False) or False,
            )
    except WriteError as exc:
        return _write_error_response(exc)
    return json_response(_result_json(result))


async def retain_view(request: Request) -> Response:
    return await _review(request, "retain")


async def reject_view(request: Request) -> Response:
    return await _review(request, "reject")


async def promote_view(request: Request) -> Response:
    return await _review(request, "promote")
