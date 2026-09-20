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

_SNIPPET_MATCH = re.compile(r"(\[[^\[\]]*\])")

#: A markdown link with its URL still attached: `[text](url)`. Deliberately
#: requires the trailing `(...)` so this can never consume a bare FTS match
#: marker (`_SNIPPET_MATCH`, below, uses the *same* bracket characters --
#: `library.search`'s snippet() call wraps a match in literal "[" / "]" --
#: but an FTS marker is never immediately followed by a parenthesized URL,
#: so the two can't be confused). Applied before the FTS-marker split, so a
#: link's brackets are gone by the time that split runs.
#:
#: The link text's own character class allows exactly one level of nested
#: "[...]": when the matched *word* falls inside the link text (e.g.
#: `[OpenKnowledge pivot decision](url)` when the query matches
#: "decision"), FTS's own snippet() has already wrapped that word in its
#: own "[" / "]" *before* this ever runs, nested inside the link's own
#: brackets -- without allowing that one level, this pattern would fail to
#: match the link at all (an unbalanced-looking "[...[...]...]"), leaving
#: the outer "[", "](url)" as literal, unstripped text. The substitution
#: keeps the inner FTS marker intact (group 1), so `_highlight` still finds
#: and marks it once the link's own brackets are gone.
_MD_LINK = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^()]*)\)")
#: A leading heading marker ("## ", "### ", ...).
_MD_HEADING = re.compile(r"#{1,6}\s*")
#: Emphasis/strong markers: **text**, *text*, __text__, _text_.
_MD_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(.+?)\1")
#: Inline code backticks.
_MD_CODE = re.compile(r"`([^`]*)`")

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
        label = project_title(library, slug) if slug in library.records_by_id else strings.SEARCH_SCOPE_PROJECT_FALLBACK.format(slug=slug)
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


def _strip_markdown_syntax(text: str) -> str:
    """A search snippet is a raw slice of a record's own Markdown source
    (``library.search``'s ``snippet()`` call runs over the FTS index, not
    over rendered HTML), so it can contain a heading marker, a link's
    ``[text](url)`` syntax, emphasis asterisks, or backticks verbatim --
    none of that belongs in a search result's preview text. Order matters:
    links are stripped first, specifically because a genuine markdown link
    and an FTS match marker use the exact same bracket characters (see
    ``_MD_LINK``'s own comment); doing this before ``_highlight`` ever
    splits on ``_SNIPPET_MATCH`` is what keeps the two from colliding."""

    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_EMPHASIS.sub(r"\2", text)
    text = _MD_CODE.sub(r"\1", text)
    return text


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
        "snippet_html": _highlight(_strip_markdown_syntax(row["snippet"])),
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
            "result_count_label": _result_count_label(len(results)),
        }
    )


def _result_count_label(count: int) -> str:
    if count == 1:
        return strings.SEARCH_RESULT_COUNT_SINGULAR
    return strings.SEARCH_RESULT_COUNT_PLURAL.format(count=count)
