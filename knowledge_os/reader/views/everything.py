"""``GET /everything`` — flat catalog of the whole corpus, including raw
sources and rejected discoveries, each carrying its trust label.

This is the deliberate counterweight to the project view's grouping by
meaning (docs/plans/reader-v1.md Sec.4): every record the adapter loaded is
listed once, sorted by what it *is* (its type), never by what it *means*
(governing/proposed/historical/...). Acceptance criterion 10 is owned here:
sources and rejected discoveries must be reachable, must carry their trust
label, and must never appear inside a governing group — there is no such
group on this page at all.

Skills have no id, type, status, or scope (a different shape from records
entirely), so they render as their own labelled group rather than as
record cards. A broken record (Library.broken; failed to parse, so it is
not in Library.records) is still listed, in place, with its lint message
(Sec.6 "Broken record") — it has no id, so it renders without a link.
"""

from __future__ import annotations

from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from .. import language, strings
from ..app import get_library, render
from ..library import BrokenRecord, Library, Record, SkillEntry

#: Thin wrappers over ``language.py``'s consolidated translation rules
#: (task 3), kept under these names so this module's own unit tests
#: (``tests/test_reader_everything.py``) keep calling
#: ``everything._trust_phrase(record, lib)`` / ``everything._record_accent
#: (record)`` directly, unchanged. Note the argument order this module
#: already used (record, library) -- opposite of document.py's (library,
#: record) -- is preserved here rather than forced to match.
def _trust_phrase(record: Record, library: Library) -> str:
    return language.catalog_phrase(library, record)


_record_accent = language.record_accent
_type_label = language.type_label


@dataclass(frozen=True)
class _Entry:
    """One row in the flat catalog: a Record plus its display-ready label."""

    record: Record
    type_label: str
    trust_phrase: str
    accent: str | None
    badge_word: str | None


def _build_entry(record: Record, library: Library) -> _Entry:
    accent = _record_accent(record)
    return _Entry(
        record=record,
        type_label=_type_label(record),
        trust_phrase=_trust_phrase(record, library),
        accent=accent,
        badge_word=strings.EVERYTHING_ACCENT_BADGE.get(accent) if accent else None,
    )


def _sort_records(records: tuple[Record, ...]) -> list[Record]:
    return sorted(records, key=lambda record: (record.type, record.title.casefold(), record.id))


def _sort_broken(broken: tuple[BrokenRecord, ...]) -> list[BrokenRecord]:
    return sorted(broken, key=lambda item: item.path)


def _sort_skills(skills: tuple[SkillEntry, ...]) -> list[SkillEntry]:
    return sorted(skills, key=lambda skill: skill.name)


async def view(request: Request) -> Response:
    library = get_library(request)
    entries = [_build_entry(record, library) for record in _sort_records(library.records)]
    broken = _sort_broken(library.broken)
    skills = _sort_skills(library.skills)
    return render(
        request,
        "everything.html",
        page_title=strings.PAGE_TITLES["everything"],
        library=library,
        entries=entries,
        broken=broken,
        skills=skills,
    )
