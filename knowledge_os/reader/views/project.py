"""``GET /p/{project_id}`` -- a project's overview plus content grouped by
meaning: governing now, proposed, historical, observations, raw material,
and a side group of general knowledge, memory, and skills that does not
belong to the project. The project's own ordinary content is reachable
through a directory tree that follows the accepted
``project-directory-layout`` decision, kept separate from the meaning
groups so nothing is shown twice.

All of the actual bucketing lives in ``grouping.py`` (pure, no I/O, no
``knowledge_os.*`` import) so it is directly unit-testable; this module only
resolves display strings against ``Library`` data (replacement titles/dates
for a superseded record, trust labels, ``content_sha256``) and renders the
template.
"""

from __future__ import annotations

import calendar
from typing import Mapping

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import get_library, render
from ..grouping import (
    ProjectGroups,
    ProjectTreeNode,
    build_project_tree,
    group_project_records,
    related_general_records,
)
from ..library import Library, Record, content_sha256


def _format_date(value: str | None) -> str | None:
    """"2026-08-30" or "2026-08-30T00:00:00Z" -> "30 August" (Sec.5's own
    example: "accepted 30 August"). Returns None unchanged so a caller can
    decide how to degrade when a record has no date to show."""

    if value is None:
        return None
    date_part = value[:10]
    try:
        year, month, day = date_part.split("-")
        return f"{int(day)} {calendar.month_name[int(month)]}"
    except (ValueError, IndexError):
        return date_part


def _find_replacement(record: Record, records_by_id: Mapping[str, Record]) -> Record | None:
    """The record that superseded ``record``, found through the reversed
    ``supersedes`` edge on ``record.inbound`` (the contract has no backlink
    subsystem, so library.py already built this inbound map)."""

    for relation in record.inbound:
        if relation.field == "supersedes" and relation.resolved:
            return records_by_id.get(relation.record_id)
    return None


def _status_text(record: Record, records_by_id: Mapping[str, Record]) -> str:
    """The meaning-facing status sentence for a decision or an ordinary
    durable record (DECISION_STATUS / LIFECYCLE_STATUS in strings.py share
    the same shape: a plain sentence, or one with a {date} or {title}+{date}
    template), never the raw status string itself."""

    if record.record_kind == "decision":
        table = strings.DECISION_STATUS
        key = "draft" if record.accepted_at is None else record.status
    else:
        table = strings.LIFECYCLE_STATUS
        key = record.status
    template = table.get(key)
    if template is None:
        return strings.PROJECT_STATUS_UNKNOWN
    if "{title}" in template:
        replacement = _find_replacement(record, records_by_id)
        if replacement is None:
            return strings.TRUST_LABELS["unusable durable record"]
        date = _format_date(replacement.accepted_at) or _format_date(replacement.updated)
        return template.format(title=replacement.title, date=date)
    if "{date}" in template:
        date = _format_date(record.accepted_at) or _format_date(record.verified) or _format_date(record.updated)
        return template.format(date=date)
    return template


def _observation_text(record: Record) -> str:
    return strings.DISCOVERY_STATUS.get(record.status, strings.PROJECT_STATUS_UNKNOWN)


def _raw_material_text(record: Record) -> str:
    return strings.TRUST_LABELS.get(record.trust_label, strings.PROJECT_STATUS_UNKNOWN)


def _badge_class(record: Record) -> str | None:
    """Which of the four restrained accent badges (see static/reader.css's
    token comment) applies, if any -- most records stay neutral on purpose.
    Mirrors the module docstring's grouping rules: type and record_kind
    decide this, never directory."""

    if record.type == "source":
        return "raw"
    if record.type == "discovery":
        return None if record.status == "retained" else "raw"
    if record.record_kind == "decision":
        if record.accepted_at is None:
            return "proposed"
        if record.status == "superseded":
            return "retired"
        return None
    if record.status in {"superseded", "deprecated", "archived"}:
        return "retired"
    if record.verified is None and record.status in {"draft", "active"}:
        return "unverified"
    return None


def _entry(record: Record, text: str) -> dict[str, object]:
    accent = _badge_class(record)
    return {
        "record": record,
        "text": text,
        "badge_class": f"badge--{accent}" if accent else None,
        "badge_label": strings.PROJECT_BADGE_LABELS.get(accent) if accent else None,
    }


def _decision_entries(records: tuple[Record, ...], records_by_id: Mapping[str, Record]) -> list[dict[str, object]]:
    return [_entry(record, _status_text(record, records_by_id)) for record in records]


def _observation_entries(records: tuple[Record, ...]) -> list[dict[str, object]]:
    return [_entry(record, _observation_text(record)) for record in records]


def _raw_material_entries(records: tuple[Record, ...]) -> list[dict[str, object]]:
    return [_entry(record, _raw_material_text(record)) for record in records]


def _tree_has_content(node: ProjectTreeNode) -> bool:
    return not node.is_empty()


async def view(request: Request) -> Response:
    library: Library = get_library(request)
    project_id = request.path_params["project_id"]
    groups: ProjectGroups = group_project_records(library.records, project_id)

    if groups.overview is None:
        # render()'s signature is fixed by app.py (never edited by a
        # stage-B unit); set the real HTTP status after the fact rather
        # than smuggling it through the template context.
        response = render(
            request,
            "project.html",
            page_title=strings.PAGE_TITLES["project"],
            found=False,
            project_id=project_id,
            library=library,
        )
        response.status_code = 404
        return response

    records_by_id = library.records_by_id
    overview = groups.overview

    governing = _decision_entries(groups.governing, records_by_id)
    proposed = _decision_entries(groups.proposed, records_by_id)
    historical = _decision_entries(groups.historical, records_by_id)
    observations = _observation_entries(groups.observations)
    raw_material = _raw_material_entries(groups.raw_material)

    general_records = related_general_records(library.records)
    related_general = [_entry(record, _status_text(record, records_by_id)) for record in general_records]

    tree = build_project_tree(project_id, groups.ordinary, library.broken)

    overview_status_text = _status_text(overview, records_by_id)
    # Sec.5: the technical-details disclosure holds *exact* contract
    # vocabulary (status, scope, trust label, path, content_sha256) -- the
    # friendly overview_status_text above is what the reading path shows.
    overview_details = {
        "status": overview.status,
        "scope": overview.scope,
        "trust_label": overview.trust_label,
        "path": overview.path,
        "content_sha256": content_sha256(overview.abs_path),
    }

    return render(
        request,
        "project.html",
        page_title=overview.title,
        found=True,
        project_id=project_id,
        overview=overview,
        overview_status_text=overview_status_text,
        overview_details=overview_details,
        groups=groups,
        governing=governing,
        proposed=proposed,
        historical=historical,
        observations=observations,
        raw_material=raw_material,
        related_general=related_general,
        related_skills=library.skills,
        tree=tree,
        tree_has_content=_tree_has_content(tree),
        library=library,
    )
