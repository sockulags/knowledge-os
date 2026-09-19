"""``GET /api/search`` — full-text search with filters on type, status,
scope, record_kind, and trust, all readable from and written back to the
query string by the frontend (so the browser's own back button restores a
previous search).

Uses ``library.search`` for results (never raises: a blank query, a missing
index, or an unparseable FTS expression all come back as a clean empty
list). ``Library.index`` decides whether search is offered at all; a stale
or missing index both disable it with a plain-language reason, exactly like
the original HTML search view.
"""

from __future__ import annotations

import re

from starlette.requests import Request
from starlette.responses import Response

from .. import states, strings
from ..app import get_library, json_response
from ..library import Library, search

_SNIPPET_MATCH = re.compile(r"(\[[^\[\]]*\])")

_FETCH_LIMIT = 200
_DISPLAY_LIMIT = 100

_FILTER_DIMENSIONS: tuple[tuple[str, dict[str, str]], ...] = (
    ("type", strings.SEARCH_TYPE_FILTER),
    ("status", strings.SEARCH_STATUS_FILTER),
    ("record_kind", strings.SEARCH_RECORD_KIND_FILTER),
    ("trust", strings.SEARCH_TRUST_FILTER),
)

_ROW_KEY_DIMENSIONS = tuple(name for name, _ in _FILTER_DIMENSIONS if name != "trust") + ("scope",)


def _read_filters(request: Request) -> dict[str, str]:
    filters: dict[str, str] = {}
    for name, options in _FILTER_DIMENSIONS:
        value = request.query_params.get(name, "")
        if value in options:
            filters[name] = value
    scope = request.query_params.get("scope", "")
    if scope:
        filters["scope"] = scope
    return filters


def _scope_options(library: Library) -> list[dict[str, str]]:
    options = [{"value": "general", "label": strings.SCOPE_GENERAL}]
    seen: set[str] = set()
    for record in library.records:
        scope = record.scope
        if scope == "general" or scope in seen:
            continue
        seen.add(scope)
        slug = scope.removeprefix("project:")
        project = library.records_by_id.get(slug)
        label = project.title if project is not None else strings.SEARCH_SCOPE_PROJECT_FALLBACK.format(slug=slug)
        options.append({"value": scope, "label": label})
    return options


def _matches(row: dict[str, str], filters: dict[str, str], trust_by_id: dict[str, str]) -> bool:
    for name in _ROW_KEY_DIMENSIONS:
        wanted = filters.get(name)
        if wanted and row.get(name) != wanted:
            return False
    wanted_trust = filters.get("trust")
    if wanted_trust and trust_by_id.get(row["id"]) != wanted_trust:
        return False
    return True


def _highlight(snippet: str) -> str:
    """Turn the FTS snippet's ``[match]`` runs into ``<mark>`` tags. The rest
    of ``body_html`` is already trusted HTML from ``markdown.render``
    (``html=False``); a search snippet is plain text straight from the FTS
    index, so it still needs its own light escaping here."""

    pieces: list[str] = []
    for chunk in _SNIPPET_MATCH.split(snippet):
        if chunk.startswith("[") and chunk.endswith("]"):
            pieces.append("<mark>" + _escape(chunk[1:-1]) + "</mark>")
        else:
            pieces.append(_escape(chunk))
    return "".join(pieces)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _decorate(row: dict[str, str], trust_by_id: dict[str, str], library: Library) -> dict[str, object]:
    project_id = row["scope"].removeprefix("project:") if row["scope"].startswith("project:") else None
    project = library.records_by_id.get(project_id) if project_id else None
    trust = trust_by_id.get(row["id"])
    return {
        "id": row["id"],
        "title": row["title"],
        "type": row["type"],
        "type_label": strings.SEARCH_TYPE_FILTER.get(row["type"], row["type"]),
        "status": row["status"],
        "status_label": strings.SEARCH_STATUS_FILTER.get(row["status"], row["status"]),
        "record_kind": row["record_kind"] or None,
        "record_kind_label": strings.SEARCH_RECORD_KIND_FILTER.get(row["record_kind"], "") if row["record_kind"] else "",
        "trust_label": strings.SEARCH_TRUST_FILTER.get(trust, "") if trust else "",
        "scope": row["scope"],
        "project": project.title if project is not None else project_id,
        "project_id": project_id,
        "snippet_html": _highlight(row["snippet"]),
    }


async def view(request: Request) -> Response:
    library = get_library(request)
    health = states.build_health_summary(library)
    search_available = not health.search_disabled
    query = request.query_params.get("q", "").strip()
    filters = _read_filters(request) if search_available else {}

    results: list[dict[str, object]] = []
    if search_available and query:
        workspace = request.app.state.workspace
        trust_by_id = {record.id: record.trust_label for record in library.records}
        rows = search(workspace, query, limit=_FETCH_LIMIT)
        matched = [row for row in rows if _matches(row, filters, trust_by_id)]
        results = [_decorate(row, trust_by_id, library) for row in matched[:_DISPLAY_LIMIT]]

    filter_options = {
        name: [{"value": value, "label": options[value]} for value in options] for name, options in _FILTER_DIMENSIONS
    }
    filter_options["scope"] = _scope_options(library)

    return json_response(
        {
            "query": query,
            "filters": filters,
            "filter_labels": strings.SEARCH_FILTER_DIMENSIONS,
            "filter_options": filter_options,
            "search_available": search_available,
            "disabled_reason": health.search_disabled_reason,
            "results": results,
            "result_count": len(results),
        }
    )
