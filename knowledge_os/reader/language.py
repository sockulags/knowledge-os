"""Contract-to-language translation: the one place a record's raw ``status``,
``trust_label``, ``scope``, and provenance ``kind`` become the plain
sentences ``docs/plans/reader-v1.md`` Sec.5 asks for.

Every view that read a record's meaning used to compose these sentences
itself (``views/document.py``'s ``_status_sentence``/``_trust_sentence``/
``_scope_sentence``/``_provenance_sentence``, ``views/everything.py``'s
``_trust_phrase``/``_decision_phrase``/``_record_accent``,
``views/project.py``'s ``_status_text``/``_observation_text``/
``_raw_material_text``/``_badge_class``, and ``views/lineage.py``'s
``_status_text``), built in isolation by eleven parallel units. Because they
never saw each other, they drifted: three different rules for the accent a
retained/rejected/promoted discovery gets, two different fallback sentences
for "superseded, but the replacement could not be found", and one view
whose accepted-decision date silently dropped the year. This module is the
single source of truth those views now call into instead.

Pure and stateless: imports only ``strings`` (the string table) and the
frozen dataclasses in ``library`` (for type hints and to read already-loaded
data). No I/O, no ``knowledge_os.*`` import — the same rule ``grouping.py``
follows, for the same reason: a translation rule should be directly unit
testable without a server or a workspace on disk.
"""

from __future__ import annotations

import datetime

from . import strings
from .library import Library, ProvenanceEntry, Record

__all__ = [
    "format_date",
    "successor_of",
    "status_sentence",
    "trust_sentence",
    "scope_sentence",
    "provenance_sentence",
    "record_accent",
    "catalog_phrase",
    "type_label",
]

#: trust_label() collapses superseded/deprecated/archived into this one
#: string -- see catalog_phrase, which reads Record.status instead so the
#: three read as distinct sentences rather than one flat "no longer in
#: effect".
_UNUSABLE_DURABLE = "unusable durable record"

#: trust_label() values that belong to a discovery record, collapsing
#: proposed/rejected (and retained, separately) into one string each;
#: catalog_phrase reads DISCOVERY_STATUS by Record.status instead, for the
#: sharper per-status phrasing the plan's language table asks for.
_DISCOVERY_TRUST_LABELS = (
    "discovery observation; not default context",
    "reviewed observation; not established knowledge",
)

_VERIFIED_DURABLE = "verified durable"

#: context_policy.trust_label() values that change what the reader should
#: believe (Sec.5: "colour only where it changes what the reader should
#: believe: proposed, unverified, retired, raw"), mapped to the four accent
#: modifiers reader.css defines. Any trust label not listed here (verified
#: durable, operational guidance) stays neutral on purpose.
_TRUST_ACCENT: dict[str, str] = {
    "draft durable; not verified": "unverified",
    "active durable; not verified": "unverified",
    "unusable durable record": "retired",
    "raw source; not established knowledge": "raw",
    "reviewed observation; not established knowledge": "raw",
    "discovery observation; not default context": "raw",
}

#: Non-decision lifecycle statuses that read as retired (--accent-retired is
#: documented as "superseded / deprecated / archived"). "draft"/"active"
#: stay neutral here: for an ordinary record (not a decision) that colour
#: would restate the Trust row, not add information.
_LIFECYCLE_ACCENT: dict[str, str] = {
    "deprecated": "retired",
    "archived": "retired",
    "superseded": "retired",
}

#: The one discovery status that carries the "raw" accent: unreviewed
#: material nobody has taken a position on yet. Once a discovery has been
#: reviewed -- retained, rejected, or promoted -- its own status sentence
#: (DISCOVERY_STATUS) already says so, and Sec.5 restricts colour to a
#: state that "changes what the reader should believe", not to every
#: distinct status a record can carry; a reviewed disposition is a settled
#: fact, not a live warning. The reader shipped with three disagreeing
#: rules for this (document.py: proposed+retained=raw, rejected+promoted=
#: retired; everything.py: only proposed=raw; project.py: everything but
#: retained=raw); this is everything.py's rule, the only one of the three
#: pinned by a passing test.
_DISCOVERY_RAW_STATUS = "proposed"


def format_date(value: str | None) -> str | None:
    """Render an ISO date or timestamp as "30 August 2026".

    ``None`` (or empty) in, ``None`` out, so a caller can decide how to
    degrade when a record has no date to show. A value that does not parse
    as either shape falls back to the raw text unchanged, since a
    reader-composed sentence should never crash the page over a date it
    cannot format -- this is the one behaviour the three original copies
    already agreed on.
    """

    if not value:
        return None
    text = value.strip()
    try:
        if "T" in text:
            parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        else:
            parsed = datetime.date.fromisoformat(text)
    except ValueError:
        return text
    return f"{parsed.day} {parsed.strftime('%B')} {parsed.year}"


def successor_of(library: Library, record: Record) -> Record | None:
    """The record that effectively superseded ``record``, if one resolves.

    ``supersedes`` is directed from the successor to the record it replaces,
    so "what replaced this" is an inbound relation on ``record`` (Sec.3: "the
    reader builds an in-memory inbound map ... per request"). In a *valid*
    corpus exactly one inbound ``supersedes`` edge resolves
    (``workspace._validate_decision_supersession``); a corpus that fails
    ``kos lint`` may have none or several, so among several resolved
    candidates the one whose own status is "active" or "superseded" (the two
    statuses the supersession invariant treats as *effective*) wins, falling
    back to any resolved candidate rather than reporting nothing.
    """

    candidates = [
        library.records_by_id[relation.record_id]
        for relation in record.inbound
        if relation.field == "supersedes" and relation.record_id in library.records_by_id
    ]
    for candidate in candidates:
        if candidate.status in ("active", "superseded"):
            return candidate
    return candidates[0] if candidates else None


def _decision_status_sentence(library: Library, record: Record) -> tuple[str, str | None]:
    if record.status == "draft":
        return strings.DECISION_STATUS["draft"], "proposed"
    if record.status == "active":
        date = format_date(record.accepted_at)
        if date is None:
            return strings.LINEAGE_ACCEPTED_UNKNOWN, None
        return strings.DECISION_STATUS["active"].format(date=date), None
    if record.status == "superseded":
        successor = successor_of(library, record)
        if successor is None:
            return strings.DOCUMENT_SUPERSEDED_UNKNOWN, "retired"
        date = format_date(successor.accepted_at) or format_date(successor.updated)
        sentence = strings.DECISION_STATUS["superseded"].format(title=successor.title, date=date)
        return sentence, "retired"
    # A decision with no other recognised status (an invalid corpus, since
    # decisions are restricted to draft/active/superseded); degrade to the
    # ordinary lifecycle table rather than raising.
    return strings.LIFECYCLE_STATUS.get(record.status, record.status), _LIFECYCLE_ACCENT.get(record.status)


def _lifecycle_status_sentence(library: Library, record: Record) -> tuple[str, str | None]:
    if record.status == "superseded":
        successor = successor_of(library, record)
        if successor is None:
            return strings.DOCUMENT_SUPERSEDED_UNKNOWN, "retired"
        date = format_date(successor.accepted_at) or format_date(successor.updated)
        sentence = strings.LIFECYCLE_STATUS["superseded"].format(title=successor.title, date=date)
        return sentence, "retired"
    sentence = strings.LIFECYCLE_STATUS.get(record.status, record.status)
    return sentence, _LIFECYCLE_ACCENT.get(record.status)


def status_sentence(library: Library, record: Record) -> tuple[str, str | None]:
    """The plain-language sentence for a record's lifecycle meaning, and its
    accent modifier (one of "proposed"/"unverified"/"retired"/"raw", or
    ``None`` for a neutral state).

    Covers all three shapes the plan's language table gives sentences for: a
    decision (draft/active/superseded), a discovery (proposed/retained/
    rejected/promoted), and an ordinary durable record (active/draft/
    deprecated/archived/superseded). This is the document view's rail
    "Status" row, the project view's per-card meaning text, the everything
    view's decision-specific phrasing, and the lineage view's comparison
    side labels -- one function instead of four.
    """

    if record.is_decision:
        return _decision_status_sentence(library, record)
    if record.type == "discovery":
        sentence = strings.DISCOVERY_STATUS.get(record.status, record.status)
        accent = "raw" if record.status == _DISCOVERY_RAW_STATUS else None
        return sentence, accent
    return _lifecycle_status_sentence(library, record)


def trust_sentence(record: Record) -> tuple[str, str | None]:
    """The plain-language sentence for a record's epistemic trust, and its
    accent modifier. Distinct from ``status_sentence``: a governing
    (accepted) decision is "In force" (status) yet still only "Confirmed" or
    "Not confirmed" (trust) depending on ``verified`` -- the two rows answer
    different questions and are never collapsed into one.
    """

    label = strings.TRUST_LABELS.get(record.trust_label, record.trust_label)
    if record.trust_label == "verified durable" and record.verified:
        label = label.format(date=format_date(record.verified))
    return label, _TRUST_ACCENT.get(record.trust_label)


def scope_sentence(library: Library, record: Record) -> str:
    """"Applies everywhere", or the scoped project's own title."""

    if record.scope == "general":
        return strings.SCOPE_GENERAL
    project_id = record.scope.split(":", 1)[1]
    project = library.records_by_id.get(project_id)
    return project.title if project is not None else project_id


def provenance_sentence(library: Library, record: Record, entry: ProvenanceEntry) -> str:
    """The plain-language sentence for one provenance entry."""

    template = strings.PROVENANCE_KIND.get(entry.kind)
    if template is None:
        return strings.PROVENANCE_KIND_FALLBACK.format(kind=entry.kind, reference=entry.reference)
    if entry.kind == "user-approved-conversation":
        # No fixture in the corpus omits `captured`, but the record's own
        # `created` date is the correct fallback if one ever does: it is the
        # date the record (and so the approval it rests on) came to exist.
        date = entry.captured or record.created
        return template.format(date=format_date(date))
    if entry.kind == "decision-acceptance":
        return template.format(reference=entry.reference)
    if entry.kind == "discovery":
        target = library.records_by_id.get(entry.reference)
        title = target.title if target is not None else entry.reference
        return template.format(title=title)
    return template


def record_accent(record: Record) -> str | None:
    """Which of the four colour-carrying states (Sec.5) applies to one
    record as a whole, or ``None`` for neutral -- the single badge a flat
    listing (the everything and project views' record cards) shows next to
    a title, as opposed to ``status_sentence``/``trust_sentence``'s two
    separate rail rows.

    A decision is judged on its own status alone (its trust label is not
    meaningful for an accepted decision -- see ``trust_sentence``'s
    docstring); a discovery only while still unreviewed (``proposed``);
    everything else on its trust label.
    """

    if record.is_decision:
        if record.status == "draft":
            return "proposed"
        if record.status == "superseded":
            return "retired"
        return None
    if record.type == "discovery":
        return "raw" if record.status == _DISCOVERY_RAW_STATUS else None
    return _TRUST_ACCENT.get(record.trust_label)


def catalog_phrase(library: Library, record: Record) -> str:
    """The single combined phrase a flat listing (the everything view's
    record cards) shows next to a title, with no separate Status/Trust rail
    rows to split the answer across.

    Decision-specific phrasing for a decision; ``DISCOVERY_STATUS`` for a
    discovery; for an ordinary durable record, status-derived phrasing (with
    a resolved successor, exactly like ``status_sentence``) once it is
    deprecated, archived, or superseded, since the generic "no longer in
    effect" trust label is less informative than naming what happened; its
    trust label otherwise, since "Draft, not confirmed" or "In use, but
    never confirmed" tells a reader more in a catalog with no rail than the
    neutral "Draft"/"Current" status would.
    """

    if record.is_decision:
        sentence, _accent = _decision_status_sentence(library, record)
        return sentence
    label = record.trust_label
    if label == _UNUSABLE_DURABLE:
        sentence, _accent = _lifecycle_status_sentence(library, record)
        return sentence
    if label in _DISCOVERY_TRUST_LABELS:
        return strings.DISCOVERY_STATUS.get(record.status, strings.TRUST_LABELS[label])
    if label == _VERIFIED_DURABLE:
        date = format_date(record.verified)
        return strings.TRUST_LABELS[label].format(date=date) if date else strings.TRUST_LABELS[label]
    return strings.TRUST_LABELS[label]


def type_label(record: Record) -> str:
    """Record.type -> reader-facing noun (falls back to a capitalized raw
    type for one this table does not name)."""

    return strings.EVERYTHING_TYPE_LABELS.get(record.type, record.type.capitalize())
