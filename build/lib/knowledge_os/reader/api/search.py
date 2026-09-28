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
from .common import project_title
from .filters import FILTER_DIMENSIONS, matches, read_filters, scope_options
from .mdtext import escape_html, strip_markdown_syntax

#: A run of one or more words `library.search`'s own `snippet()` call
#: wrapped in literal "[" / "]" to mark an FTS match. Applying
#: `mdtext.strip_markdown_syntax`'s link stripper *first* (see `_decorate`)
#: is what keeps this from ever colliding with a genuine markdown link's
#: own "[text](url)" brackets: an FTS marker is never immediately followed
#: by a parenthesized URL, but the two brackets are otherwise identical, so
#: order matters -- the link syntax must already be gone before this runs.
_SNIPPET_MATCH = re.compile(r"(\[[^\[\]]*\])")

_FETCH_LIMIT = 200
_DISPLAY_LIMIT = 100


def _row_values(row: dict[str, str], trust_by_id: dict[str, str]) -> dict[str, str | None]:
    """A search row's own value per filter dimension. ``record_kind`` is
    normalized the same way ``filters.record_kind_for_filter`` normalizes a
    ``Record``: the FTS index stores ``""`` for every non-knowledge/project
    type (``index.py``'s own ``_record_kind``), which must still count as
    "ordinary", not as a value no filter can ever match."""

    return {
        "type": row["type"],
        "status": row["status"],
        "record_kind": "decision" if row["record_kind"] == "decision" else "ordinary",
        "scope": row["scope"],
        "trust": trust_by_id.get(row["id"]),
    }


def _highlight(snippet: str) -> str:
    """Turn the FTS snippet's ``[match]`` runs into ``<mark>`` tags, on text
    already put through ``mdtext.strip_markdown_syntax`` (see ``_decorate``).
    The rest of ``body_html`` is already trusted HTML from
    ``markdown.render`` (``html=False``); a search snippet is plain text
    straight from the FTS index, so it still needs its own light escaping
    here."""

    pieces: list[str] = []
    for chunk in _SNIPPET_MATCH.split(snippet):
        if chunk.startswith("[") and chunk.endswith("]"):
            pieces.append("<mark>" + escape_html(chunk[1:-1]) + "</mark>")
        else:
            pieces.append(escape_html(chunk))
    return "".join(pieces)


def _decorate(row: dict[str, str], trust_by_id: dict[str, str], library: Library) -> dict[str, object]:
    project_id = row["scope"].removeprefix("project:") if row["scope"].startswith("project:") else None
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
        "project": project_title(library, project_id) if project_id else None,
        "project_id": project_id,
        "snippet_html": _highlight(strip_markdown_syntax(row["snippet"])),
    }


async def view(request: Request) -> Response:
    library = get_library(request)
    health = states.build_health_summary(library)
    search_available = not health.search_disabled
    query = request.query_params.get("q", "").strip()
    filters = read_filters(request) if search_available else {}

    results: list[dict[str, object]] = []
    if search_available and query:
        workspace = request.app.state.workspace
        trust_by_id = {record.id: record.trust_label for record in library.records}
        rows = search(workspace, query, limit=_FETCH_LIMIT)
        matched = [row for row in rows if matches(_row_values(row, trust_by_id), filters)]
        results = [_decorate(row, trust_by_id, library) for row in matched[:_DISPLAY_LIMIT]]

    filter_options = {
        name: [{"value": value, "label": options[value]} for value in options] for name, options in FILTER_DIMENSIONS
    }
    filter_options["scope"] = scope_options(library)

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
            "result_count_label": _result_count_label(len(results)),
        }
    )


def _result_count_label(count: int) -> str:
    if count == 1:
        return strings.SEARCH_RESULT_COUNT_SINGULAR
    return strings.SEARCH_RESULT_COUNT_PLURAL.format(count=count)
