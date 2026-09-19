"""``GET /search`` — a view, not a modal: filters on type, status, scope,
``record_kind``, and trust; filter state survives navigating into a
document and back because it lives entirely in the query string (a plain
GET form, no client-side state, no JavaScript).

Uses ``library.search(workspace, query, limit=...)`` for results (it never
raises: a blank query, a missing index, or an unparseable FTS expression all
come back as a clean empty list). ``Library.index`` decides whether to
attempt a search at all: when unavailable, this view shows why and how to
rebuild it (``strings.INDEX_HEALTH``) instead of a form (Sec.6 "Missing
index" / acceptance criterion 7); when stale, the form still works but a
notice is shown above it.

Search results are records only; skills are never in the FTS index (see
library.search's docstring and knowledge_os/index.py), so this view never
implies a skill is searchable.
"""

from __future__ import annotations

import re

from markupsafe import Markup, escape
from starlette.requests import Request
from starlette.responses import Response

from .. import states, strings
from ..app import get_library, render
from ..library import Library, search

#: library.search()'s snippet wraps each match in "[" and "]" (see its
#: docstring / knowledge_os/index.py's snippet() call). Splitting on this
#: keeps the delimiters with their bracketed run so the loop below can tell
#: a highlighted run from plain text.
_SNIPPET_MATCH = re.compile(r"(\[[^\[\]]*\])")

#: A generous fetch size: filters are applied in Python after the FTS query
#: (library.search's row shape has no filter parameters of its own), so the
#: pool fetched from SQLite needs to be larger than what is ultimately
#: displayed or a filter could appear to "lose" matches that bm25 ranked
#: past the display limit. Local workspaces are small; this stays cheap.
_FETCH_LIMIT = 200

#: How many filtered results to show. Not a hard contract requirement, just
#: a sane cap so one very broad query cannot render a page of unbounded
#: length.
_DISPLAY_LIMIT = 100

#: Filter dimensions, in the order the form (and the query string) presents
#: them, each paired with the raw-value -> plain-label dict that supplies
#: both its <option> list and its per-result display text.
_FILTER_DIMENSIONS: tuple[tuple[str, dict[str, str]], ...] = (
    ("type", strings.SEARCH_TYPE_FILTER),
    ("status", strings.SEARCH_STATUS_FILTER),
    ("record_kind", strings.SEARCH_RECORD_KIND_FILTER),
    ("trust", strings.SEARCH_TRUST_FILTER),
)


def _read_filters(request: Request) -> dict[str, str]:
    """Read every filter dimension from the query string, ``scope`` included.

    For the four dict-backed dimensions, a value not present in that
    dimension's known vocabulary is dropped rather than trusted: a
    hand-edited or stale URL must never make its way into ``_matches`` as
    anything but one of the values the reader itself offers. ``scope`` has
    no such fixed vocabulary (see ``_scope_options``, built from whatever
    projects this workspace actually has), so it is taken as given; an
    unrecognised scope is still only ever compared with ``==`` in
    ``_matches``, so at worst it narrows a search to zero results, exactly
    like a mistyped id in a document URL.
    """

    filters: dict[str, str] = {}
    for name, options in _FILTER_DIMENSIONS:
        value = request.query_params.get(name, "")
        if value in options:
            filters[name] = value
    scope = request.query_params.get("scope", "")
    if scope:
        filters["scope"] = scope
    return filters


def _scope_options(library: Library) -> list[tuple[str, str]]:
    """Build the "Applies to" dimension's options from the corpus itself.

    Unlike the other four dimensions, scope's project half is open-ended
    (one option per project actually in this workspace), so it cannot be a
    static dict in strings.py. "general" always sorts first; project scopes
    follow, labelled with that project's own title when its overview record
    resolves, or a plain fallback when it does not (Sec.6-style graceful
    degradation for a stale index pointing at a renamed project).
    """

    options = [("general", strings.SCOPE_GENERAL)]
    seen: set[str] = set()
    for record in library.records:
        scope = record.scope
        if scope == "general" or scope in seen:
            continue
        seen.add(scope)
        slug = scope.removeprefix("project:")
        project = library.records_by_id.get(slug)
        label = project.title if project is not None else strings.SEARCH_SCOPE_PROJECT_FALLBACK.format(slug=slug)
        options.append((scope, label))
    return options


#: The dimensions _matches can check directly against a search row's own
#: keys. "trust" is deliberately excluded: library.search()'s row has no
#: trust column (see its docstring -- only id, title, type, record_kind,
#: status, scope, path, snippet), so it is matched separately below via
#: trust_by_id, built from the freshly loaded Library instead.
_ROW_KEY_DIMENSIONS = tuple(name for name, _ in _FILTER_DIMENSIONS if name != "trust") + ("scope",)


def _matches(row: dict[str, str], filters: dict[str, str], trust_by_id: dict[str, str]) -> bool:
    for name in _ROW_KEY_DIMENSIONS:
        wanted = filters.get(name)
        if wanted and row.get(name) != wanted:
            return False
    wanted_trust = filters.get("trust")
    if wanted_trust and trust_by_id.get(row["id"]) != wanted_trust:
        return False
    return True


def _highlight(snippet: str) -> Markup:
    """Escape a raw FTS snippet and turn its "[match]" runs into <mark>.

    The snippet comes straight from record body text of unknown provenance,
    so every piece (matched or not) is escaped individually; only the
    <mark> tags themselves are trusted markup, giving a template a
    pre-escaped, safe-to-render string rather than needing ``|safe`` on
    unescaped user content.
    """

    pieces: list[Markup] = []
    for chunk in _SNIPPET_MATCH.split(snippet):
        if chunk.startswith("[") and chunk.endswith("]"):
            pieces.append(Markup("<mark>") + escape(chunk[1:-1]) + Markup("</mark>"))
        else:
            pieces.append(escape(chunk))
    return Markup("").join(pieces)


def _decorate(row: dict[str, str], trust_by_id: dict[str, str]) -> dict[str, object]:
    """Add plain-language display fields to one result row.

    ``row`` keeps its original eight keys (see library.search's docstring);
    this only adds presentation fields the template reads, so the raw
    values stay available for the filter-matching above. Trust comes from
    ``trust_by_id`` (built from the freshly loaded Library, not from the
    FTS row, which has no trust column) and is left blank rather than
    guessed when the id no longer resolves (a stale index entry).
    """

    decorated: dict[str, object] = dict(row)
    decorated["type_label"] = strings.SEARCH_TYPE_FILTER.get(row["type"], row["type"])
    decorated["status_label"] = strings.SEARCH_STATUS_FILTER.get(row["status"], row["status"])
    decorated["record_kind_label"] = (
        strings.SEARCH_RECORD_KIND_FILTER.get(row["record_kind"], "") if row["record_kind"] else ""
    )
    trust = trust_by_id.get(row["id"])
    decorated["trust_label"] = strings.SEARCH_TRUST_FILTER.get(trust, "") if trust else ""
    decorated["snippet_html"] = _highlight(row["snippet"])
    return decorated


async def view(request: Request) -> Response:
    library = get_library(request)
    index = library.index
    # Sec.6 "Stale index" disables search the same way "Missing index" does,
    # with the reason and the `kos index` command, while browsing keeps
    # working; states.HealthSummary already encodes exactly that rule
    # (search_disabled is set for either an absent/unreadable index or a
    # stale one), so this view follows it rather than only warning on stale.
    health = states.build_health_summary(library)
    search_available = not health.search_disabled
    query = request.query_params.get("q", "").strip()
    filters = _read_filters(request) if search_available else {}

    results: list[dict[str, str]] = []
    if search_available and query:
        workspace = request.app.state.workspace
        trust_by_id = {record.id: record.trust_label for record in library.records}
        rows = search(workspace, query, limit=_FETCH_LIMIT)
        matched = [row for row in rows if _matches(row, filters, trust_by_id)]
        results = [_decorate(row, trust_by_id) for row in matched[:_DISPLAY_LIMIT]]

    filter_options = {name: [(value, options[value]) for value in options] for name, options in _FILTER_DIMENSIONS}
    filter_options["scope"] = _scope_options(library)
    # Display order follows the plan's own listing of the five dimensions
    # (Sec.4: "type, status, scope, record_kind, and trust"), not the
    # _FILTER_DIMENSIONS tuple order above (which groups the four
    # dict-backed dimensions before the one built from the corpus).
    filter_order = ["type", "status", "scope", "record_kind", "trust"]

    return render(
        request,
        "search.html",
        page_title=strings.PAGE_TITLES["search"],
        library=library,
        index=index,
        search_available=search_available,
        search_disabled_reason=health.search_disabled_reason,
        query=query,
        filters=filters,
        filter_dimensions=filter_order,
        filter_options=filter_options,
        results=results,
        has_filters=bool(filters),
    )
