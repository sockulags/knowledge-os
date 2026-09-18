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

import datetime
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import get_library, render
from ..library import BrokenRecord, Library, Record, SkillEntry

#: trust_label() values that mean "durable record no longer in effect"
#: (superseded/deprecated/archived collapsed by the core). Never shown raw;
#: see _trust_phrase, which reads Record.status to tell them apart.
_UNUSABLE_DURABLE = "unusable durable record"

#: trust_label() values that belong to a discovery record. DISCOVERY_STATUS
#: (keyed by Record.status) gives the sharper phrasing the plan asks for;
#: trust_label() alone cannot tell proposed/rejected/promoted apart.
_DISCOVERY_TRUST_LABELS = (
    "discovery observation; not default context",
    "reviewed observation; not established knowledge",
)

_VERIFIED_DURABLE = "verified durable"

#: Non-decision trust labels -> accent token (reader.css .badge--*). Decisions
#: are handled separately in _record_accent: an accepted (active) decision is
#: currently governing and stays neutral, unlike an ordinary active-but-
#: unconfirmed record, so trust_label alone is not enough for those.
_ACCENT_BY_TRUST_LABEL: dict[str, str] = {
    "raw source; not established knowledge": "raw",
    "draft durable; not verified": "unverified",
    "active durable; not verified": "unverified",
    _UNUSABLE_DURABLE: "retired",
}


@dataclass(frozen=True)
class _Entry:
    """One row in the flat catalog: a Record plus its display-ready label."""

    record: Record
    type_label: str
    trust_phrase: str
    accent: str | None
    badge_word: str | None


def _pretty_date(value: str | None) -> str | None:
    """"2026-08-30T00:00:00Z" -> "30 August"; None if unparseable or absent.

    Matches the exact rendering the plan and the reader design record give
    for an accepted decision ("accepted 30 August"); a missing or malformed
    date degrades to None rather than raising, so a display path can always
    fall back to a dateless phrase.
    """

    if not value:
        return None
    try:
        parsed = datetime.date.fromisoformat(value[:10])
    except ValueError:
        return None
    return f"{parsed.day} {parsed.strftime('%B')}"


def _decision_phrase(record: Record, library: Library) -> str | None:
    """The plan's decision-specific language (Sec.5), when it applies.

    Returns None when the record is not a decision, or when the decision
    status has no confident phrasing available (e.g. "active" with no
    resolvable acceptance date) — the caller then falls through to the
    generic trust-label phrasing rather than guessing.
    """

    if not record.is_decision:
        return None
    if record.status == "draft":
        return strings.DECISION_STATUS["draft"]
    if record.status == "active":
        date = _pretty_date(record.accepted_at)
        return strings.DECISION_STATUS["active"].format(date=date) if date else None
    if record.status == "superseded":
        replacement = next(
            (relation for relation in record.inbound if relation.field == "supersedes" and relation.resolved),
            None,
        )
        if replacement is None:
            return None
        target = library.records_by_id.get(replacement.record_id)
        date = _pretty_date(target.accepted_at) if target else None
        if date is None and target is not None:
            date = _pretty_date(target.updated)
        if date is None:
            return None
        return strings.DECISION_STATUS["superseded"].format(title=replacement.title, date=date)
    return None


def _trust_phrase(record: Record, library: Library) -> str:
    """The reader-facing sentence for one record's epistemic state.

    Never returns a raw trust_label string. Decisions get the plan's
    decision-specific phrasing when it resolves cleanly; every other record
    (and a decision whose phrasing did not resolve) falls back to
    TRUST_LABELS, refined by Record.status where a trust label collapses
    several distinct statuses into one (the "unusable durable record" and
    discovery cases).
    """

    decision_phrase = _decision_phrase(record, library)
    if decision_phrase is not None:
        return decision_phrase

    label = record.trust_label
    if label == _UNUSABLE_DURABLE:
        if record.status == "deprecated":
            return strings.LIFECYCLE_STATUS["deprecated"]
        if record.status == "archived":
            return strings.LIFECYCLE_STATUS["archived"]
        return strings.EVERYTHING_REPLACED_FALLBACK
    if label in _DISCOVERY_TRUST_LABELS:
        return strings.DISCOVERY_STATUS.get(record.status, strings.TRUST_LABELS[label])
    if label == _VERIFIED_DURABLE:
        date = _pretty_date(record.verified)
        return strings.TRUST_LABELS[label].format(date=date) if date else strings.TRUST_LABELS[label]
    return strings.TRUST_LABELS[label]


def _record_accent(record: Record) -> str | None:
    """Which of the four colour-carrying states (Sec.5) this record is in,
    or None for neutral. An accepted decision is currently governing and
    stays neutral even though it has no ``verified`` date (a decision is
    confirmed by acceptance, not by that field); an ordinary durable record
    with no ``verified`` date has no equivalent confirmation, so it keeps
    the "unverified" accent whether draft or active.
    """

    if record.is_decision:
        if record.status == "draft":
            return "proposed"
        if record.status == "superseded":
            return "retired"
        return None
    if record.trust_label == _DISCOVERY_TRUST_LABELS[0] and record.status == "proposed":
        return "raw"
    return _ACCENT_BY_TRUST_LABEL.get(record.trust_label)


def _type_label(record: Record) -> str:
    return strings.EVERYTHING_TYPE_LABELS.get(record.type, record.type.capitalize())


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
