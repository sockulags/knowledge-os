"""Degradation and health states: pure helpers over ``library.Library``.

Unit 9 owns every state in ``docs/plans/reader-v1.md`` Sec.6 except the last
three (empty project group's rendering, empty workspace, and the long-document
table of contents), which units 2, 3, and 1 render themselves. This module
turns ``Library`` data into view-ready values; ``templates/partials/health.html``
and ``templates/partials/broken.html`` render them. Nothing here does I/O or
imports ``knowledge_os.*``: every function takes data already produced by
``library.load_library`` (or a ``LibraryError`` a caller already caught) and
returns a frozen dataclass or a formatted string.

How a sibling view uses this module
------------------------------------

1. Compute the values in Python, in the view module, then pass them into
   ``render()`` under the exact names below — Jinja's ``{% include %}``
   shares its parent's context, so the partial only needs those names to be
   present somewhere in the call chain that included it.

   Health line (any page; typically the rail or nav)::

       from .. import states
       ...
       health = states.build_health_summary(library)
       return render(request, "my_view.html", health=health, ...)

   and in ``my_view.html``::

       {% include "partials/health.html" %}

2. Broken record, rendered in place (Sec.6 "Broken record"). A document view
   checks ``record_id`` against ``library.broken`` before ``records_by_id``;
   the Everything view lists every entry from ``states.broken_entries()``
   alongside ordinary record cards, in path order, so one bad file cannot
   hide the rest of the corpus::

       broken = next((b for b in library.broken if ...), None)
       diagnostic = states.diagnostic_for_broken(broken)
       return render(request, "broken_document.html", diagnostic=diagnostic, ...)

   and in the template::

       {% include "partials/broken.html" %}

3. Unreadable repo-document content (Sec.6 "Unreadable content"). A view that
   calls ``library.read_repo_document`` catches ``LibraryError`` and turns it
   into the same shape::

       try:
           title, text = read_repo_document(workspace, rel_path)
       except LibraryError as exc:
           diagnostic = states.diagnostic_for_unreadable(rel_path, exc)
           return render(request, "repodoc_unreadable.html", diagnostic=diagnostic, ...)

   ``partials/broken.html`` renders any ``Diagnostic`` the same way regardless
   of which of the two helpers built it: a label, an optional path, and the
   exact detail text. This is the one place a lint message or a file path
   legitimately reaches the reader (see the contract note in the plan); both
   fields are pre-formatted here so a template never has to call
   ``strings.*.format()`` itself.

4. Broken relation (Sec.6 "Broken relation"). A document view renders each
   ``Relation`` in ``Record.outbound``/``Record.inbound`` through
   ``states.relation_label()`` instead of ``relation.title`` directly, so an
   unresolved id renders as "points at unknown id X" rather than a blank::

       {% for relation in record.outbound %}
         <li>{{ states.relation_label(relation) }}</li>
       {% endfor %}

   (``states`` is also registered as a Jinja global in ``app.py``, so a
   template that builds its own list of entries -- the project view's
   recursive directory tree, one broken file per node -- can call
   ``states.diagnostic_for_broken(item)`` in place and ``{% include
   "partials/broken.html" %}`` it, instead of a view precomputing a
   diagnostic for a structure the template itself builds. A view computing
   a single, page-level value still passes it in directly, as above.)
"""

from __future__ import annotations

from dataclasses import dataclass

from . import strings
from .library import BrokenRecord, IndexHealth, Library, Relation

__all__ = [
    "Diagnostic",
    "IssueEntry",
    "HealthSummary",
    "diagnostic_for_broken",
    "diagnostic_for_unreadable",
    "broken_entries",
    "issue_entries",
    "build_health_summary",
    "relation_label",
    "is_relation_broken",
    "lint_summary_line",
]


@dataclass(frozen=True)
class Diagnostic:
    """One thing that could not be shown normally, framed as a diagnostic.

    Covers both "Broken record" (a managed file that failed metadata
    validation) and "Unreadable content" (a file that read as bytes but
    could not be shown: non-UTF-8, deleted mid-session, or rejected by path
    safety). ``path`` is ``None`` only in a context where no path is
    meaningful; every state.py caller today always has one.
    """

    label: str
    path: str | None
    detail: str


@dataclass(frozen=True)
class IssueEntry:
    """One ``kos lint`` issue, for the health line's "affected records" list.

    ``record_id`` is set when the issue's path still produced a readable
    record (the file parsed but failed a relational check, e.g. a type
    mismatch or duplicate id) so the entry can link to it; it is ``None``
    when the path never parsed at all (the same file also appears in
    ``Library.broken``).
    """

    path: str
    message: str
    record_id: str | None


@dataclass(frozen=True)
class HealthSummary:
    """Everything a health line needs, computed once per request.

    ``search_disabled`` covers both "Stale index" and "Missing index" from
    Sec.6: the plan's state table asks for search to be disabled with an
    explanation in either case, not only when the index is absent, so both
    ``stale`` and ``not available`` set the flag. ``search_disabled_reason``
    is always ``IndexHealth.message`` when the flag is set, and always the
    already-user-facing text from ``strings.INDEX_HEALTH`` — never ``None``
    when ``search_disabled`` is ``True``.
    """

    lint_ok: bool
    lint_message: str
    issue_count: int
    issues: tuple[IssueEntry, ...]
    index_available: bool
    index_stale: bool
    search_disabled: bool
    search_disabled_reason: str | None


def diagnostic_for_broken(broken: BrokenRecord) -> Diagnostic:
    """Sec.6 "Broken record": exact lint message and path, clearly framed."""

    return Diagnostic(
        label=strings.BROKEN_RECORD_LABEL,
        path=broken.path,
        detail=strings.BROKEN_RECORD_DETAIL.format(message=broken.message),
    )


def diagnostic_for_unreadable(path: str, error: Exception) -> Diagnostic:
    """Sec.6 "Unreadable content".

    ``error`` is a ``library.LibraryError`` a view already caught around
    ``read_repo_document``; its message is already a complete, user-facing
    sentence (``strings.REPO_DOCUMENT_*``), so it is used as-is rather than
    reformatted here.
    """

    return Diagnostic(label=strings.UNREADABLE_CONTENT_LABEL, path=path, detail=str(error))


def broken_entries(library: Library) -> tuple[Diagnostic, ...]:
    """Every managed file that never parsed, as diagnostics, path-ordered.

    For "rendered in place" (Sec.6): a listing view (e.g. the Everything
    catalog) includes these alongside ordinary record cards so a broken file
    is visible where it would otherwise have appeared, instead of vanishing.
    """

    return tuple(
        diagnostic_for_broken(broken) for broken in sorted(library.broken, key=lambda entry: entry.path)
    )


def issue_entries(library: Library) -> tuple[IssueEntry, ...]:
    """Every ``kos lint`` issue, path-ordered, linkable when still readable.

    ``Library.issues`` is a superset of ``Library.broken``: a file that
    parsed but failed a relational check lands in ``issues`` only, still
    carrying a real record id; a file that never parsed lands in both,
    with no id. Matching by path (not by scanning ``Library.broken`` again)
    keeps this the single place that distinguishes the two, so a caller
    never double-counts by adding ``len(Library.broken)`` on top.
    """

    path_to_id = {record.path: record.id for record in library.records}
    return tuple(
        IssueEntry(path=issue.path, message=issue.message, record_id=path_to_id.get(issue.path))
        for issue in sorted(library.issues, key=lambda entry: entry.path)
    )


def _search_disabled_reason(index: IndexHealth) -> str | None:
    if not index.available:
        # Absent or unreadable: IndexHealth.message is already one of
        # strings.INDEX_HEALTH["absent"] / ["unreadable"].
        return index.message
    if index.stale:
        return strings.INDEX_HEALTH["stale"]
    return None


def build_health_summary(library: Library) -> HealthSummary:
    """Sec.6 "Lint failing globally" / "Stale index" / "Missing index".

    ``issue_count`` is ``len(Library.issues)``, never
    ``len(Library.broken) + len(Library.issues)``: see ``issue_entries``.
    The library never goes down regardless of what this returns; a caller
    always has a page to render, degraded or not.
    """

    issue_count = len(library.issues)
    lint_ok = issue_count == 0
    if lint_ok:
        lint_message = strings.LINT_OK
    elif issue_count == 1:
        lint_message = strings.LINT_ISSUES_SINGULAR
    else:
        lint_message = strings.LINT_ISSUES_PLURAL.format(count=issue_count)
    reason = _search_disabled_reason(library.index)
    return HealthSummary(
        lint_ok=lint_ok,
        lint_message=lint_message,
        issue_count=issue_count,
        issues=issue_entries(library),
        index_available=library.index.available,
        index_stale=library.index.stale,
        search_disabled=reason is not None,
        search_disabled_reason=reason,
    )


def relation_label(relation: Relation) -> str:
    """Sec.6 "Broken relation": "points at unknown id X", never a blank.

    A resolved relation shows the target's title, exactly as the document
    view would otherwise show it directly; only the unresolved branch is
    this unit's concern, but both are handled here so a caller never needs
    a second call site to decide which string applies.
    """

    if relation.resolved:
        return relation.title or relation.record_id
    return strings.BROKEN_RELATION.format(record_id=relation.record_id)


def is_relation_broken(relation: Relation) -> bool:
    """Whether a relation should render with the broken-relation treatment."""

    return not relation.resolved


def lint_summary_line(library: Library) -> str:
    """Just the headline sentence, for a caller that wants nothing else.

    Equivalent to ``build_health_summary(library).lint_message`` without
    building the rest of the summary; kept as a separate export because most
    of the plan's mentions of "the health line" (Sec.4 start view) only need
    this one sentence, not the full issues list or index state.
    """

    return build_health_summary(library).lint_message
