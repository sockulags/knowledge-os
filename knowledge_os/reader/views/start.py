"""``GET /`` — "back in": recently changed, open decisions, entry points.

Shows, in order: decisions still waiting on a position, one entry point per
project, every record in the corpus (most recently updated first), the
installed skills, and one labelled entry point into the unmanaged
repo-document tier (``docs/plans/reader-v1.md`` Sec.4 and acceptance
criterion 2). The health rail reports exactly what ``Library.index`` and
``Library.broken`` say — no invented score or percentage.

When the workspace has no records and no skills, the page explains what a
record is and points at ``kos capture`` instead of rendering an empty shell
(Sec.6 "Empty workspace"); that copy already lives in ``strings.py``
(``EMPTY_WORKSPACE_TITLE`` / ``EMPTY_WORKSPACE_BODY``) from unit 0.

Nothing here parses YAML, reimplements validation, or writes to the
workspace: every fact comes straight off ``library.Library`` and its
``Record``/``SkillEntry`` dataclasses, and the one filesystem check this
module does (``Path.is_file()`` for the repo-document candidates) never
reads or writes record content itself.
"""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response

from .. import language, states, strings
from ..app import get_library, render
from ..library import Library, LibraryError, Record, read_repo_document

#: Checked in order; the first one that exists on disk becomes the start
#: page's one labelled entry point into the unmanaged tier (unit 7 owns
#: browsing the tier itself, so this stays a single link, not a listing).
_REPO_DOCUMENT_CANDIDATES = ("docs/architecture.md", "SYSTEM.md", "README.md")

#: Thin wrapper over language.py's consolidated date formatting (task 3),
#: kept under this name for this module's own call sites.
_format_date = language.format_date


def _project_entries(library: Library) -> list[tuple[str, str]]:
    """One (project_id, title) pair per project referenced by any record's
    scope, titled from that project's own overview record when present.

    A project's overview record satisfies ``record.id == project_id`` and
    is never itself a decision (workspace._validate_project_overviews, run
    inside validate_workspace, is what guarantees exactly one such record
    per project); falling back to the raw slug keeps this from crashing if
    that invariant is somehow violated.
    """

    slugs = {
        record.scope.removeprefix("project:") for record in library.records if record.scope.startswith("project:")
    }
    titles = {
        record.id: record.title for record in library.records if record.id in slugs and not record.is_decision
    }
    entries = [(slug, titles.get(slug, slug)) for slug in slugs]
    entries.sort(key=lambda entry: entry[1].lower())
    return entries


def _open_decisions(library: Library) -> list[Record]:
    """Decisions with no position taken yet: ``status == "draft"``.

    An active decision has a decision-acceptance entry; a superseded one is
    historical. Only "draft" is still waiting (Sec.4 "open decisions
    awaiting a position").
    """

    decisions = [record for record in library.records if record.is_decision and record.status == "draft"]
    decisions.sort(key=lambda record: record.title.lower())
    return decisions


def _recently_changed(library: Library) -> list[Record]:
    """Every record, most recently updated first (stable on a tie by title).

    Acceptance criterion 2 requires the start page to list every record in
    the corpus; sorting rather than truncating satisfies that without
    inventing a cutoff.
    """

    records = sorted(library.records, key=lambda record: record.title.lower())
    records.sort(key=lambda record: record.updated, reverse=True)
    return records


def _repo_document_entry(request: Request, library: Library) -> dict[str, str] | None:
    workspace = request.app.state.workspace
    for candidate in _REPO_DOCUMENT_CANDIDATES:
        if not (library.workspace_root / Path(candidate)).is_file():
            continue
        try:
            title, _ = read_repo_document(workspace, candidate)
        except LibraryError:
            continue
        return {"path": candidate, "title": title}
    return None


async def view(request: Request) -> Response:
    library = get_library(request)
    is_empty = not library.records and not library.skills

    context: dict[str, object] = {
        "page_title": strings.PAGE_TITLES["start"],
        "library": library,
        "is_empty": is_empty,
        # The rail's health line now renders through partials/health.html
        # (unit 9), replacing this view's own ad hoc index-message and
        # broken-record-count lines (Sec.6 "Lint failing globally" /
        # "Stale index" / "Missing index").
        "health": states.build_health_summary(library),
    }

    if not is_empty:
        recently_changed = _recently_changed(library)
        skills = sorted(library.skills, key=lambda skill: skill.name.lower())
        context.update(
            {
                "open_decisions": _open_decisions(library),
                "project_entries": _project_entries(library),
                "recently_changed": recently_changed,
                "updated_display": {record.id: _format_date(record.updated) for record in recently_changed},
                "skills": skills,
                "repo_document": _repo_document_entry(request, library),
            }
        )

    return render(request, "start.html", **context)
