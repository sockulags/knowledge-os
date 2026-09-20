"""``GET /api/home`` — "back in": decisions waiting on you, decisions in
force, what changed recently, and the project grid. No invented metrics:
every number here is a plain count of records already in the library.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language, strings
from ..app import get_library, json_response
from ..library import Library, Record
from .common import project_title, record_summary_with_sentence, relative_date

#: How many "recently changed" rows the home page shows. Not a contract
#: number, just a sane cap so a large workspace does not render an
#: unbounded list on its landing page.
_RECENT_LIMIT = 12


def _decisions(library: Library, status: str) -> list[Record]:
    matches = [r for r in library.records if r.is_decision and r.status == status]
    matches.sort(key=lambda r: r.title.lower())
    return matches


def _subtitle(in_force_count: int) -> str:
    if in_force_count == 0:
        return strings.HOME_SUBTITLE_NONE
    if in_force_count == 1:
        return strings.HOME_SUBTITLE_SINGULAR
    return strings.HOME_SUBTITLE_PLURAL.format(count=in_force_count)


def _project_ids(library: Library) -> list[str]:
    slugs = {
        record.scope.removeprefix("project:") for record in library.records if record.scope.startswith("project:")
    }
    return sorted(slugs, key=lambda slug: project_title(library, slug).lower())


async def view(request: Request) -> Response:
    library = get_library(request)

    in_force = _decisions(library, "active")
    waiting = _decisions(library, "draft")

    in_force_json = []
    for record in in_force:
        entry = record_summary_with_sentence(library, record)
        entry["accepted_display"] = language.format_date(record.accepted_at)
        in_force_json.append(entry)

    waiting_json = [record_summary_with_sentence(library, record) for record in waiting]

    recently_changed = sorted(library.records, key=lambda r: r.title.lower())
    recently_changed.sort(key=lambda r: r.updated, reverse=True)
    recent_json = []
    for record in recently_changed[:_RECENT_LIMIT]:
        entry = record_summary_with_sentence(library, record)
        entry["updated_display"] = relative_date(record.updated)
        entry["updated_exact"] = language.format_date(record.updated)
        recent_json.append(entry)

    projects = [{"id": pid, "title": project_title(library, pid)} for pid in _project_ids(library)]

    return json_response(
        {
            "title": strings.HOME_TITLE,
            "subtitle": _subtitle(len(in_force)),
            "waiting_on_you": waiting_json,
            "in_force": in_force_json,
            "recently_changed": recent_json,
            "projects": projects,
        }
    )
