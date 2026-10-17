"""Health states: pure helpers over ``library.Library``.

Turns ``Library`` data into the health summary the JSON API reports (the
nav payload and the search page): the ``kos lint`` headline and its issue
list, and whether search is disabled by a stale, missing, or rebuilding
index. Nothing here does I/O or imports ``knowledge_os.*``: every function
takes data already produced by ``library.load_library`` and returns a frozen
dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import strings
from .library import IndexHealth, Library

__all__ = [
    "IssueEntry",
    "HealthSummary",
    "issue_entries",
    "build_health_summary",
]


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
    index_refreshing: bool
    search_disabled: bool
    search_disabled_reason: str | None


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
    # Absent, unreadable, stale, or being rebuilt: IndexHealth.message is
    # already the matching strings.INDEX_HEALTH entry (library.py sets the
    # first three, index_refresh.py replaces it while it rebuilds the index
    # or when a rebuild did not help).
    if not index.available or index.stale:
        return index.message
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
        index_refreshing=library.index.refreshing,
        search_disabled=reason is not None,
        search_disabled_reason=reason,
    )
