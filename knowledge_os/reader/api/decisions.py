"""``GET /api/decisions/proposed`` — the Decide inbox: every proposed
decision in the workspace, newest first, optionally narrowed to one project
with ``?project=<id>`` (``general`` for decisions that apply everywhere).

Each row carries what a person needs to act without opening the decision:
its title and first lines, who or what proposed it and when (from
provenance, through ``language.proposed_by``), what accepting would change
(including which decision a replacement retires), the content hash the
action endpoints need, and the same action and dialog data the decision
page gets (``common.decision_actions_json``).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language, strings
from ..app import get_library, json_response
from ..library import Library, Record, content_sha256
from .common import (
    decision_actions_json,
    decision_language,
    pill_for,
    project_id_for_scope,
    project_title,
    relative_date,
    strip_leading_h1,
)
from .mdtext import strip_markdown_syntax

#: The general-scope bucket's filter value (decisions that apply everywhere).
GENERAL = "general"

#: Characters of body text a row shows under its title.
_EXCERPT_LIMIT = 220


def _excerpt(body: str) -> str:
    """The first lines of prose in a decision body: headings, code fences,
    and blank lines skipped, Markdown syntax removed, cut at a word."""

    parts: list[str] = []
    length = 0
    in_fence = False
    for line in strip_leading_h1(body).splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence or not stripped or stripped.startswith("#"):
            continue
        text = strip_markdown_syntax(stripped).strip()
        if not text:
            continue
        parts.append(text)
        length += len(text) + 1
        if length > _EXCERPT_LIMIT:
            break
    excerpt = " ".join(parts)
    if len(excerpt) <= _EXCERPT_LIMIT:
        return excerpt
    cut = excerpt[:_EXCERPT_LIMIT].rsplit(" ", 1)[0].rstrip(",.;:")
    return f"{cut}…"


def _bucket(record: Record) -> str:
    return project_id_for_scope(record.scope) or GENERAL


def _bucket_title(library: Library, bucket: str) -> str:
    return strings.SCOPE_GENERAL if bucket == GENERAL else project_title(library, bucket)


def _named_replacement(library: Library, record: Record) -> dict[str, object] | None:
    """The decision this proposal names in ``supersedes``, whether or not it
    can still be replaced (the row's effect sentence says which)."""

    for relation in record.outbound:
        if relation.field != "supersedes":
            continue
        target = library.records_by_id.get(relation.record_id)
        sentence = language.status_sentence(library, target)[0] if target is not None else None
        return {"id": relation.record_id, "title": relation.title or relation.record_id, "sentence": sentence}
    return None


def _effect(project: str, actions: dict[str, object], replaces: dict[str, object] | None) -> str:
    if actions["supersede"] is not None:
        return strings.DECIDE_EFFECT_REPLACE.format(title=actions["supersede"]["title"])  # type: ignore[index]
    if replaces is not None or not actions["accept"]:
        return strings.DECIDE_EFFECT_BLOCKED
    return strings.DECIDE_EFFECT_ACCEPT.format(project=project)


def _row(library: Library, record: Record) -> dict[str, object]:
    bucket = _bucket(record)
    project = _bucket_title(library, bucket)
    proposer = language.proposed_by(library, record)
    when = proposer["when"]
    actions = decision_actions_json(library, record)
    assert actions is not None  # every row is a decision
    replaces = _named_replacement(library, record)
    try:
        sha = content_sha256(record.abs_path)
    except OSError:
        sha = None
    return {
        "id": record.id,
        "title": record.title,
        "excerpt": _excerpt(record.body),
        "project": {"id": bucket, "title": project},
        "proposed_by": {"source": proposer["source"], "label": proposer["label"], "kind": proposer["kind"]},
        "proposed_at": when,
        "proposed_display": relative_date(when),
        "proposed_exact": language.format_date(when),
        "replaces": replaces,
        "effect": _effect(project, actions, replaces),
        "status_pill": pill_for(record),
        "content_sha256": sha,
        "actions": actions,
    }


def proposed_decisions(library: Library) -> list[Record]:
    """Every proposed (draft) decision, newest first by when it was
    proposed, then by title."""

    drafts = sorted(
        (r for r in library.records if r.is_decision and r.status == "draft"), key=lambda r: r.title.lower()
    )
    drafts.sort(key=lambda r: language.proposed_by(library, r)["when"] or "", reverse=True)
    return drafts


def count_label(count: int) -> str:
    if count == 1:
        return strings.DECIDE_COUNT_SINGULAR
    return strings.DECIDE_COUNT_PLURAL.format(count=count)


async def proposed_view(request: Request) -> Response:
    library = get_library(request)
    wanted = request.query_params.get("project") or None
    drafts = proposed_decisions(library)

    counts: dict[str, int] = {}
    for record in drafts:
        counts[_bucket(record)] = counts.get(_bucket(record), 0) + 1
    projects = sorted(
        ({"id": bucket, "title": _bucket_title(library, bucket), "count": count} for bucket, count in counts.items()),
        key=lambda entry: str(entry["title"]).lower(),
    )

    shown = [record for record in drafts if wanted is None or _bucket(record) == wanted]
    empty_body = strings.DECIDE_EMPTY_FILTERED if wanted is not None and drafts else strings.DECIDE_EMPTY_BODY

    return json_response(
        {
            "title": strings.DECIDE_TITLE,
            "intro": strings.DECIDE_INTRO,
            "count": len(drafts),
            "count_label": count_label(len(drafts)) if drafts else None,
            # For the count while an action waits for Undo: "{count}" is filled in.
            "count_templates": {"one": strings.DECIDE_COUNT_SINGULAR, "other": strings.DECIDE_COUNT_PLURAL},
            "project": wanted,
            "filter_label": strings.DECIDE_PROJECT_FILTER_LABEL,
            "all_projects_label": strings.DECIDE_ALL_PROJECTS,
            "projects": projects,
            "items": [_row(library, record) for record in shown],
            "empty": {"title": strings.DECIDE_EMPTY_TITLE, "body": empty_body},
            "open_label": strings.DECIDE_OPEN,
            "language": decision_language(),
        }
    )
