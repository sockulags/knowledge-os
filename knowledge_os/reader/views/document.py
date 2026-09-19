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

import re

from starlette.requests import Request
from starlette.responses import Response

from .. import language, markdown, strings
from ..app import get_library, render
from ..library import Library, Record, Relation, content_sha256, path_index

#: How many provenance entries the rail shows before collapsing the rest
#: behind a <details> (Sec.4: "the rail must handle a long provenance list
#: without dominating"; see the module docstring).
_PROVENANCE_VISIBLE = 3

#: A leading level-1 heading only, on the first non-blank line of the body
#: (see the module docstring for why it is stripped).
_LEADING_H1 = re.compile(r"^#\s+\S.*$")

#: Thin wrapper kept for this module's own test surface
#: (``tests/test_reader_document.py``'s ``FormatDateTests`` calls
#: ``document._format_date`` directly); the implementation now lives in
#: ``language.py`` so every view shares one date-formatting rule.
_format_date = language.format_date


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

#: Thin wrappers over ``language.py``'s consolidated translation rules
#: (task 3: one contract-to-language module, shared by every view), kept
#: under these names so this module's own unit tests
#: (``tests/test_reader_document.py``) keep calling ``document._status_
#: sentence(lib, record)`` etc. directly, unchanged.
_status_sentence = language.status_sentence
_trust_sentence = language.trust_sentence
_scope_sentence = language.scope_sentence
_provenance_sentence = language.provenance_sentence


def _relation_view(relation: Relation) -> dict[str, str | None]:
    if not relation.resolved:
        return {"href": None, "title": strings.BROKEN_RELATION.format(record_id=relation.record_id)}
    # A decision that supersedes another decision, or has been superseded by
    # one, links to the side-by-side comparison rather than straight to the
    # other record: "supersedes" is the one relation field where "what
    # changed between these two" is the more useful destination than "read
    # the other record" (the third central flow, Sec.4: "decision to
    # supersedes or superseded-by with a side-by-side comparison").
    if relation.field == "supersedes":
        return {"href": f"/r/{relation.record_id}/compare", "title": relation.title}
    return {"href": f"/r/{relation.record_id}", "title": relation.title}


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
    # Rewrite a relative record-to-record link (e.g. "../decisions/x.md")
    # into a /r/<id> permalink when it resolves against the corpus; see
    # markdown.render's own docstring. The lookup is built fresh from this
    # request's Library, matching load_library's no-caching contract.
    body_html = markdown.render(body, source_path=record.path, resolve_link=path_index(library).get)

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
