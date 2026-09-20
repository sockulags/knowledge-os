"""``GET /api/everything`` — flat catalog of the whole corpus, including raw
sources and rejected discoveries, each carrying its trust label. Never
grouped by meaning: acceptance criterion 10 is owned here, so nothing in
this response is a "governing" group at all.

Filters on type (kind), status, record_kind, scope (project), and trust use
the exact same query-string vocabulary and drop-unknown-values contract
``GET /api/search`` already has (``knowledge_os/reader/api/filters.py``), so
a filtered link works identically -- and is offered identically -- on
either page. Sorting by column/direction is this endpoint's own addition
(search keeps its relevance ordering); an unrecognized ``sort``/``dir``
falls back to the default rather than erroring, matching the filters'
own contract.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language, strings
from ..app import get_library, json_response
from ..library import Library, Record
from .common import project_title, record_summary
from .filters import DEFAULT_SORT, FILTER_DIMENSIONS, matches, read_filters, read_sort, record_kind_for_filter, scope_options

#: sort column -> the decorated entry field it orders by.
_SORT_FIELD = {
    "title": "title",
    "type": "type_label",
    "updated": "updated",
    "project": "project_title",
}


def _entry(record: Record, library: Library) -> dict[str, object]:
    summary = record_summary(record)
    summary["type_label"] = language.type_label(record)
    # The Trust column sits next to a Status pill. For a decision, that
    # pill already carries its lifecycle (in force / waiting on you /
    # replaced); language.catalog_phrase's decision-specific branch would
    # repeat that same full sentence a second time ("In force — accepted
    # ..." next to an "In force" pill), since catalog_phrase was designed
    # for a listing with no separate Status column at all. Every other
    # record type's catalog_phrase (source, discovery, ordinary durable)
    # already answers "how much to trust this" specifically and is not
    # redundant with its pill, so only decisions get the narrower
    # trust_sentence here.
    if record.is_decision:
        trust_sentence, _accent = language.trust_sentence(record)
        summary["trust_phrase"] = trust_sentence
    else:
        summary["trust_phrase"] = language.catalog_phrase(library, record)
    summary["updated_display"] = language.format_date_short(record.updated)
    project_id = summary.get("project")
    summary["project_title"] = project_title(library, project_id) if project_id else None
    return summary


def _values(record: Record) -> dict[str, str | None]:
    return {
        "type": record.type,
        "status": record.status,
        "record_kind": record_kind_for_filter(record),
        "scope": record.scope,
        "trust": record.trust_label,
    }


def _filter_options(library: Library) -> dict[str, list[dict[str, str]]]:
    """Only the options that actually match something (an option nothing in
    the workspace has is not offered), computed fresh from the records
    already loaded for this request -- never a second parse of the
    workspace."""

    present: dict[str, set[str]] = {name: set() for name, _ in FILTER_DIMENSIONS}
    for record in library.records:
        values = _values(record)
        for name in present:
            value = values.get(name)
            if value is not None:
                present[name].add(value)
    options = {
        name: [{"value": value, "label": labels[value]} for value in labels if value in present[name]]
        for name, labels in FILTER_DIMENSIONS
    }
    options["scope"] = scope_options(library)
    return options


def _sort_entries(entries: list[dict[str, object]], column: str, direction: str) -> list[dict[str, object]]:
    # `column` is already validated against `filters.SORT_COLUMNS` by
    # `read_sort` before it ever reaches here, so this `.get` is a defensive
    # fallback, not the enforcement point -- but it keeps this function's own
    # contract (never raise on an odd column) true even if a future caller
    # skips `read_sort`.
    field = _SORT_FIELD.get(column, _SORT_FIELD[DEFAULT_SORT])
    reverse = direction == "desc"
    return sorted(entries, key=lambda entry: (str(entry.get(field) or "").casefold(), entry["id"]), reverse=reverse)


async def view(request: Request) -> Response:
    library = get_library(request)
    filters = read_filters(request)
    column, direction = read_sort(request)

    matched = [record for record in library.records if matches(_values(record), filters)]
    entries = _sort_entries([_entry(record, library) for record in matched], column, direction)

    broken = [
        {"path": item.path, "message": item.message}
        for item in sorted(library.broken, key=lambda b: b.path)
    ]
    skills = [
        {"name": skill.name, "description": skill.description}
        for skill in sorted(library.skills, key=lambda s: s.name)
    ]
    return json_response(
        {
            "entries": entries,
            "broken": broken,
            "skills": skills,
            "filters": filters,
            "filter_labels": strings.EVERYTHING_FILTER_DIMENSIONS,
            "filter_options": _filter_options(library),
            "sort": column,
            "dir": direction,
        }
    )
