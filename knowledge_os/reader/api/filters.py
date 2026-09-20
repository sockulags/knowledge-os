"""Shared filter vocabulary for ``GET /api/search`` and ``GET /api/everything``:
kind (``type``), ``record_kind``, ``status``, ``scope`` (project), and
``trust``, all parsed from the query string the same way for both endpoints
so a filtered link behaves identically no matter which page built it, and
survives reload and the back button either way.

An unknown or malformed value for any dimension is silently dropped --
treated exactly as if the caller had not supplied it at all -- rather than
raising or narrowing to nothing. This was already the contract
``GET /api/search`` shipped with (see
``tests/test_api_search.py::FilterTests.test_unknown_filter_value_is_dropped_not_trusted``);
both endpoints keep it, so a stale or hand-edited query string degrades to
"show everything" instead of a traceback or a 400.
"""

from __future__ import annotations

from starlette.requests import Request

from .. import strings
from ..library import Library, Record
from .common import project_title

#: (query-param name, {token: on-screen label}) for the four fixed-vocabulary
#: dimensions. ``scope`` is not here: its values are workspace-specific
#: (project ids), so there is no fixed dict to validate against -- any
#: non-empty value is accepted and simply matches nothing if it names no
#: record's scope.
FILTER_DIMENSIONS: tuple[tuple[str, dict[str, str]], ...] = (
    ("type", strings.SEARCH_TYPE_FILTER),
    ("status", strings.SEARCH_STATUS_FILTER),
    ("record_kind", strings.SEARCH_RECORD_KIND_FILTER),
    ("trust", strings.SEARCH_TRUST_FILTER),
)

#: Sort columns both the Everything table understands, and their (asc, desc)
#: intent kept identical to the column header buttons already in the UI.
SORT_COLUMNS = ("title", "type", "updated", "project")
SORT_DIRECTIONS = ("asc", "desc")
DEFAULT_SORT = "title"
DEFAULT_DIRECTION = "asc"


def read_filters(request: Request) -> dict[str, str]:
    """type/status/record_kind/trust/scope from the query string. A value
    outside the known vocabulary for a fixed dimension is dropped (see
    module docstring); an empty/missing value is simply absent from the
    result, in both cases meaning "no filter on this dimension"."""

    filters: dict[str, str] = {}
    for name, options in FILTER_DIMENSIONS:
        value = request.query_params.get(name, "")
        if value in options:
            filters[name] = value
    scope = request.query_params.get("scope", "")
    if scope:
        filters["scope"] = scope
    return filters


def read_sort(request: Request) -> tuple[str, str]:
    """(column, direction) from the query string, each falling back to its
    default when missing or not one of the known values -- the same
    drop-unknown-values contract ``read_filters`` uses, so a bad ``sort`` or
    ``dir`` degrades to the default ordering rather than an error."""

    column = request.query_params.get("sort", DEFAULT_SORT)
    if column not in SORT_COLUMNS:
        column = DEFAULT_SORT
    direction = request.query_params.get("dir", DEFAULT_DIRECTION)
    if direction not in SORT_DIRECTIONS:
        direction = DEFAULT_DIRECTION
    return column, direction


def record_kind_for_filter(record: Record) -> str:
    """"decision" or "ordinary" for every record, including the types
    (source, discovery, memory, synthesis) whose own ``record_kind`` field
    is ``None`` -- the ``record_kind`` filter's "Not a decision" option is
    documented (``strings.SEARCH_RECORD_KIND_FILTER``) to cover *every*
    non-decision record, not just knowledge/project ones."""

    return "decision" if record.is_decision else "ordinary"


def matches(values: dict[str, str | None], filters: dict[str, str]) -> bool:
    """True if every active filter agrees with ``values`` -- one lookup per
    dimension (type/status/record_kind/scope/trust), supplied by the
    caller since a search row and a ``Record`` reach their trust/record_kind
    values differently."""

    for name, wanted in filters.items():
        if values.get(name) != wanted:
            return False
    return True


def scope_options(library: Library) -> list[dict[str, str]]:
    """Every scope actually present in the workspace, "general" first, each
    with a project's display title -- the data-driven option list both
    endpoints offer for the ``scope`` filter (there being no fixed
    vocabulary to fall back on)."""

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
