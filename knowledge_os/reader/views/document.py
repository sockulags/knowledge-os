"""``GET /r/{record_id}`` — read one record: reading column, provenance and
relations in the metadata rail, collapsible for deep reading; a table of
contents for long documents.

Design decisions this view makes, recorded here since the plan leaves them
open:

* The reading column (``.reading``) holds only the title and the body prose.
  Every other field the plan assigns to the rail (Sec.4: "status, trust,
  provenance, scope, relations in both directions, path, content_sha256")
  stays out of it, matching Sec.5's principle that provenance (and, by the
  same logic, the rest of the metadata) is "never inside the reading column".
* Ten of the thirteen real records have no body H1; the other three open with
  one that duplicates or diverges from the frontmatter title (for example
  ``knowledge-os-record-model``'s body opens with "# Record model" while its
  title is "Knowledge OS record model"). Since the page already renders the
  frontmatter title as the single ``<h1>`` (titles are shown, never
  filenames, and never duplicated), a leading level-1 heading is stripped
  from the body before rendering. Only the very first heading is affected;
  everything else in the body renders unchanged.
* All three relation fields (``related``, ``sources``, ``supersedes``) are
  shown together under two headers, "Related" (outbound) and "Points here"
  (inbound) — the field name itself is contract vocabulary the plan does not
  give reader prose for, and the two existing headers already cover both
  directions without it.
* A long provenance list (three records carry ten ``repository-file``
  entries each) shows its first three entries plainly and holds the rest
  behind a native ``<details>`` inside the rail, so it stays reachable in one
  click without dominating the rail on an ordinary record.
"""

from __future__ import annotations

import datetime
import re

from starlette.requests import Request
from starlette.responses import Response

from .. import markdown, strings
from ..app import get_library, render
from ..library import Library, ProvenanceEntry, Record, Relation, content_sha256

#: How many provenance entries the rail shows before collapsing the rest
#: behind a <details> (Sec.4: "the rail must handle a long provenance list
#: without dominating"; see the module docstring).
_PROVENANCE_VISIBLE = 3

#: A leading level-1 heading only, on the first non-blank line of the body
#: (see the module docstring for why it is stripped).
_LEADING_H1 = re.compile(r"^#\s+\S.*$")

#: context_policy.trust_label() values that change what the reader should
#: believe (Sec.5: "colour only where it changes what the reader should
#: believe: proposed, unverified, retired, raw"), mapped to the four accent
#: modifiers reader.css already defines. Any trust label not listed here
#: (verified durable, operational guidance) stays neutral on purpose.
_TRUST_ACCENT: dict[str, str] = {
    "draft durable; not verified": "unverified",
    "active durable; not verified": "unverified",
    "unusable durable record": "retired",
    "raw source; not established knowledge": "raw",
    "reviewed observation; not established knowledge": "raw",
    "discovery observation; not default context": "raw",
}

#: Non-decision lifecycle statuses that read as retired (Sec.5's
#: --accent-retired is documented as "superseded / deprecated / archived").
#: "draft"/"active" stay neutral here: for an ordinary record (not a
#: decision) that colour would restate the Trust row, not add information.
_LIFECYCLE_ACCENT: dict[str, str] = {
    "deprecated": "retired",
    "archived": "retired",
    "superseded": "retired",
}

#: Discovery statuses that read as raw (unreviewed or reviewed-but-not-
#: knowledge) versus retired (a terminal outcome that is no longer live).
_DISCOVERY_ACCENT: dict[str, str] = {
    "proposed": "raw",
    "retained": "raw",
    "rejected": "retired",
    "promoted": "retired",
}


def _format_date(value: str) -> str:
    """Render an ISO date or timestamp as "30 August 2026".

    Falls back to the raw value unchanged if it does not parse as either
    shape; a reader-composed sentence should never crash the page over a
    date it cannot format.
    """

    text = value.strip()
    try:
        if "T" in text:
            parsed = datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        else:
            parsed = datetime.date.fromisoformat(text)
    except ValueError:
        return text
    return f"{parsed.day} {parsed.strftime('%B')} {parsed.year}"


def _strip_leading_h1(body: str) -> str:
    """Drop a body's leading level-1 heading, if it has one (see docstring)."""

    lines = body.splitlines(keepends=True)
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines) or not _LEADING_H1.match(lines[index].strip()):
        return body
    index += 1
    while index < len(lines) and not lines[index].strip():
        index += 1
    return "".join(lines[index:])


_HEADING_TAG = re.compile(r"<h([1-6])((?:\s[^>]*)?)>")


def _successor(library: Library, record: Record) -> Record | None:
    """The record that supersedes ``record``, if one resolves.

    ``supersedes`` is directed from the successor to the record it replaces,
    so "what replaced this" is an inbound relation on ``record`` (Sec.3:
    "the reader builds an in-memory inbound map ... per request").
    """

    for relation in record.inbound:
        if relation.field == "supersedes":
            return library.records_by_id.get(relation.record_id)
    return None


def _status_sentence(library: Library, record: Record) -> tuple[str, str | None]:
    """The plain-language sentence for the Status rail row, and its accent
    modifier (one of "proposed"/"unverified"/"retired"/"raw", or ``None``
    for a neutral state)."""

    if record.is_decision:
        if record.status == "draft":
            return strings.DECISION_STATUS["draft"], "proposed"
        if record.status == "active":
            date = _format_date(record.accepted_at) if record.accepted_at else ""
            return strings.DECISION_STATUS["active"].format(date=date), None
        if record.status == "superseded":
            successor = _successor(library, record)
            if successor is None:
                return strings.DOCUMENT_SUPERSEDED_UNKNOWN, "retired"
            date = successor.accepted_at or successor.updated
            sentence = strings.DECISION_STATUS["superseded"].format(
                title=successor.title, date=_format_date(date)
            )
            return sentence, "retired"

    if record.type == "discovery":
        sentence = strings.DISCOVERY_STATUS.get(record.status, record.status)
        return sentence, _DISCOVERY_ACCENT.get(record.status)

    if record.status == "superseded":
        successor = _successor(library, record)
        if successor is None:
            return strings.DOCUMENT_SUPERSEDED_UNKNOWN, "retired"
        date = successor.accepted_at or successor.updated
        sentence = strings.LIFECYCLE_STATUS["superseded"].format(
            title=successor.title, date=_format_date(date)
        )
        return sentence, "retired"

    sentence = strings.LIFECYCLE_STATUS.get(record.status, record.status)
    return sentence, _LIFECYCLE_ACCENT.get(record.status)


def _trust_sentence(record: Record) -> tuple[str, str | None]:
    label = strings.TRUST_LABELS.get(record.trust_label, record.trust_label)
    if record.trust_label == "verified durable" and record.verified:
        label = label.format(date=_format_date(record.verified))
    return label, _TRUST_ACCENT.get(record.trust_label)


def _scope_sentence(library: Library, record: Record) -> str:
    if record.scope == "general":
        return strings.SCOPE_GENERAL
    project_id = record.scope.split(":", 1)[1]
    project = library.records_by_id.get(project_id)
    return project.title if project is not None else project_id


def _provenance_sentence(library: Library, record: Record, entry: ProvenanceEntry) -> str:
    template = strings.PROVENANCE_KIND.get(entry.kind)
    if template is None:
        return strings.PROVENANCE_KIND_FALLBACK.format(kind=entry.kind, reference=entry.reference)
    if entry.kind == "user-approved-conversation":
        # No fixture in the corpus omits `captured`, but the record's own
        # `created` date is the correct fallback if one ever does: it is the
        # date the record (and so the approval it rests on) came to exist.
        date = entry.captured or record.created
        return template.format(date=_format_date(date))
    if entry.kind == "decision-acceptance":
        return template.format(reference=entry.reference)
    if entry.kind == "discovery":
        target = library.records_by_id.get(entry.reference)
        title = target.title if target is not None else entry.reference
        return template.format(title=title)
    return template


def _relation_view(relation: Relation) -> dict[str, str | None]:
    if relation.resolved:
        return {"href": f"/r/{relation.record_id}", "title": relation.title}
    return {"href": None, "title": strings.BROKEN_RELATION.format(record_id=relation.record_id)}


def _build_context(library: Library, record: Record) -> dict[str, object]:
    """Everything ``templates/document.html`` and its partials need, fully
    resolved to plain strings and HTML. Kept separate from ``view()`` so it
    can be unit tested without a Starlette ``Request``."""

    status_sentence, status_accent = _status_sentence(library, record)
    trust_sentence, trust_accent = _trust_sentence(record)

    provenance_sentences = [_provenance_sentence(library, record, entry) for entry in record.provenance]
    provenance_shown = provenance_sentences[:_PROVENANCE_VISIBLE]
    provenance_rest = provenance_sentences[_PROVENANCE_VISIBLE:]

    body = _strip_leading_h1(record.body)
    headings = [h for h in markdown.headings(body) if h[0] <= 3]
    body_html = markdown.render(body)

    return {
        "record": record,
        "body_html": body_html,
        "toc": headings,
        "status_sentence": status_sentence,
        "status_accent": status_accent,
        "trust_sentence": trust_sentence,
        "trust_accent": trust_accent,
        "scope_sentence": _scope_sentence(library, record),
        "provenance_shown": provenance_shown,
        "provenance_rest": provenance_rest,
        "outbound": [_relation_view(relation) for relation in record.outbound],
        "inbound": [_relation_view(relation) for relation in record.inbound],
        "content_sha256_value": content_sha256(record.abs_path),
    }


async def view(request: Request) -> Response:
    library = get_library(request)
    record_id = request.path_params["record_id"]
    record = library.records_by_id.get(record_id)

    if record is None:
        return render(
            request,
            "document.html",
            not_found=True,
            record_id=record_id,
            page_title=strings.DOCUMENT_NOT_FOUND_TITLE,
            status_code=404,
        )

    context = _build_context(library, record)
    return render(
        request,
        "document.html",
        not_found=False,
        page_title=record.title,
        **context,
    )
