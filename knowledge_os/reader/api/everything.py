"""``GET /api/everything`` — flat catalog of the whole corpus, including raw
sources and rejected discoveries, each carrying its trust label. Never
grouped by meaning: acceptance criterion 10 is owned here, so nothing in
this response is a "governing" group at all.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language
from ..app import get_library, json_response
from ..library import Library, Record
from .common import project_title, record_summary


def _sort_records(records: tuple[Record, ...]) -> list[Record]:
    return sorted(records, key=lambda record: (record.type, record.title.casefold(), record.id))


def _entry(record: Record, library: Library) -> dict[str, object]:
    summary = record_summary(record)
    summary["type_label"] = language.type_label(record)
    summary["trust_phrase"] = language.catalog_phrase(library, record)
    project_id = summary.get("project")
    summary["project_title"] = project_title(library, project_id) if project_id else None
    return summary


async def view(request: Request) -> Response:
    library = get_library(request)
    entries = [_entry(record, library) for record in _sort_records(library.records)]
    broken = [
        {"path": item.path, "message": item.message}
        for item in sorted(library.broken, key=lambda b: b.path)
    ]
    skills = [
        {"name": skill.name, "description": skill.description}
        for skill in sorted(library.skills, key=lambda s: s.name)
    ]
    return json_response({"entries": entries, "broken": broken, "skills": skills})
