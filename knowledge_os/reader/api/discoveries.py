"""``GET /api/discoveries/pending`` — observations waiting for review, for
Decide: every proposed (unreviewed) discovery, newest first, with the review
packet ``kos discovery review`` prints, the pages it may overlap with, and the
commands and agent request that review it. Read-only: the app does not
retain, reject, or promote yet.

When the corpus or search index cannot produce the packets, the rows still
list every waiting observation, without packets, and ``error`` says why.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language, markdown, strings
from ..app import get_library, json_response
from ..library import Library, PendingDiscovery, Record, pending_discoveries
from .common import pill_for, project_id_for_scope, project_title, relative_date
from .decisions import GENERAL, _excerpt


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
        }
    )
