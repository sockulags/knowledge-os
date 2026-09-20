"""``GET /api/records/{record_id}`` and ``GET /api/records/{record_id}/compare``
— read one record, and compare it against what it supersedes or was
superseded by.

Design decisions this module makes, carried over from the original HTML
document view (``views/document.py``), still hold: a leading body H1 that
only duplicates the frontmatter title is stripped (the title is already
shown once, in the page's own heading), and a supersession relation links
to the compare page rather than straight to the other record.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from .. import language, markdown, strings
from ..app import get_library, json_response, not_found
from ..library import Library, Record, Relation, content_sha256, path_index
from .common import (
    breadcrumb_for_record,
    lineage_callouts,
    properties_block,
    record_summary,
    record_summary_with_sentence,
    relation_view,
    strip_leading_h1,
    technical_details,
)
from .mdtext import escape_html, strip_markdown_syntax

_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


async def view(request: Request) -> Response:
    library = get_library(request)
    record_id = request.path_params["record_id"]
    record = library.records_by_id.get(record_id)

    if record is None:
        return not_found(strings.DOCUMENT_NOT_FOUND_BODY.format(record_id=record_id))

    body = strip_leading_h1(record.body)
    headings = [h for h in markdown.headings(body) if h[0] <= 3]
    body_html = markdown.render(body, source_path=record.path, resolve_link=path_index(library).get)

    return json_response(
        {
            "id": record.id,
            "title": record.title,
            "type": record.type,
            "record_kind": record.record_kind,
            "is_decision": record.is_decision,
            "breadcrumb": breadcrumb_for_record(library, record),
            "properties": properties_block(library, record),
            "technical_details": technical_details(record, content_sha256(record.abs_path)),
            "lineage": lineage_callouts(library, record),
            "body_html": body_html,
            "headings": headings,
            "inbound": [relation_view(relation) for relation in record.inbound],
            "outbound": [relation_view(relation) for relation in record.outbound],
        }
    )


# ---------------------------------------------------------------------------
# Compare (GET /api/records/{record_id}/compare)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _DiffBlock:
    kind: str
    left_html: str | None
    right_html: str | None


def _paragraphs(body: str) -> list[str]:
    lines = body.replace("\r\n", "\n").split("\n")
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_PATTERN.match(line):
            in_fence = not in_fence
        if line.strip() == "" and not in_fence:
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [paragraph for paragraph in paragraphs if paragraph]


def _word_diff_html(old_text: str, new_text: str) -> tuple[str, str]:
    """Word-level highlight for one "changed" paragraph pair, so a reader
    sees exactly which words moved instead of two whole paragraphs sharing
    one flat "something changed here" tint (coordinator review of the
    compare page against a real supersession: a paragraph-length "changed"
    block gave no way to tell a one-word edit from a full rewrite).

    Renders as escaped plain text with the differing words wrapped in
    ``<mark>``, not as Markdown: diffing at the word level over Markdown
    syntax risks splitting a multi-word ``**bold**``/``[link](url)`` span
    across a match/no-match boundary, which would leave one side's markers
    unpaired. Losing rich formatting on just the words that differ is a
    small trade for never rendering broken markup; every paragraph that is
    unchanged, added, or removed outright still gets full Markdown
    rendering in ``_diff_blocks`` below."""

    old_words = strip_markdown_syntax(old_text).split()
    new_words = strip_markdown_syntax(new_text).split()
    matcher = difflib.SequenceMatcher(None, old_words, new_words, autojunk=False)
    left_parts: list[str] = []
    right_parts: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            text = escape_html(" ".join(old_words[i1:i2]))
            left_parts.append(text)
            right_parts.append(text)
            continue
        if i1 != i2:
            left_parts.append(f"<mark>{escape_html(' '.join(old_words[i1:i2]))}</mark>")
        if j1 != j2:
            right_parts.append(f"<mark>{escape_html(' '.join(new_words[j1:j2]))}</mark>")
    return f"<p>{' '.join(left_parts)}</p>", f"<p>{' '.join(right_parts)}</p>"


def _diff_blocks(old_body: str, new_body: str) -> tuple[list[_DiffBlock], dict[str, int]]:
    old_paragraphs = _paragraphs(old_body)
    new_paragraphs = _paragraphs(new_body)
    matcher = difflib.SequenceMatcher(None, old_paragraphs, new_paragraphs, autojunk=False)
    blocks: list[_DiffBlock] = []
    counts = {"added": 0, "removed": 0, "changed": 0}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                html = markdown.render(old_paragraphs[i1 + offset])
                blocks.append(_DiffBlock("equal", html, html))
        elif tag == "delete":
            for index in range(i1, i2):
                blocks.append(_DiffBlock("removed", markdown.render(old_paragraphs[index]), None))
                counts["removed"] += 1
        elif tag == "insert":
            for index in range(j1, j2):
                blocks.append(_DiffBlock("added", None, markdown.render(new_paragraphs[index])))
                counts["added"] += 1
        elif tag == "replace":
            left_count = i2 - i1
            right_count = j2 - j1
            for offset in range(max(left_count, right_count)):
                left_text = old_paragraphs[i1 + offset] if offset < left_count else None
                right_text = new_paragraphs[j1 + offset] if offset < right_count else None
                if left_text is not None and right_text is not None:
                    # A clean one-for-one pairing within the replace group:
                    # highlight the words that actually differ instead of
                    # tinting both whole paragraphs alike.
                    left_html, right_html = _word_diff_html(left_text, right_text)
                else:
                    # An uneven replace group (more paragraphs on one side
                    # than the other) has no natural word-for-word pairing;
                    # fall back to rendering the lone side's paragraph whole.
                    left_html = markdown.render(left_text) if left_text is not None else None
                    right_html = markdown.render(right_text) if right_text is not None else None
                blocks.append(_DiffBlock("changed", left_html, right_html))
                counts["changed"] += 1
    return blocks, counts


def _summarize(counts: dict[str, int]) -> str:
    if not any(counts.values()):
        return strings.LINEAGE_SUMMARY_UNCHANGED
    noun = "section" if counts["added"] == 1 else "sections"
    return strings.LINEAGE_SUMMARY.format(
        noun=noun, added=counts["added"], removed=counts["removed"], changed=counts["changed"]
    )


def _side_json(library: Library, record: Record) -> dict[str, object]:
    entry = record_summary_with_sentence(library, record)
    return entry


def _comparison_json(
    heading: str,
    state: str,
    detail: str | None,
    left: Record | None,
    right: Record | None,
    blocks: list[_DiffBlock],
    summary: str | None,
    library: Library,
) -> dict[str, object]:
    return {
        "heading": heading,
        "state": state,
        "detail": detail,
        "left": _side_json(library, left) if left is not None else None,
        "right": _side_json(library, right) if right is not None else None,
        "blocks": [{"kind": b.kind, "left_html": b.left_html, "right_html": b.right_html} for b in blocks],
        "summary": summary,
    }


def _resolved(heading: str, older: Record, newer: Record, library: Library) -> dict[str, object]:
    blocks, counts = _diff_blocks(older.body, newer.body)
    return _comparison_json(heading, "ok", None, older, newer, blocks, _summarize(counts), library)


def _unresolved(heading: str, relation: Relation, library: Library) -> dict[str, object]:
    detail = strings.LINEAGE_MISSING_TARGET.format(record_id=relation.record_id)
    return _comparison_json(heading, "missing", detail, None, None, [], None, library)


def _not_decision(heading: str, target: Record | None, relation: Relation, library: Library) -> dict[str, object]:
    title = target.title if target is not None else relation.record_id
    detail = strings.LINEAGE_TARGET_NOT_DECISION.format(title=title)
    return _comparison_json(heading, "not_decision", detail, None, None, [], None, library)


def _comparison_for_outbound(record: Record, relation: Relation, library: Library) -> dict[str, object]:
    heading = strings.LINEAGE_SUPERSEDES
    if not relation.resolved:
        return _unresolved(heading, relation, library)
    target = library.records_by_id.get(relation.record_id)
    if target is None or not target.is_decision:
        return _not_decision(heading, target, relation, library)
    return _resolved(heading, older=target, newer=record, library=library)


def _comparison_for_inbound(record: Record, relation: Relation, library: Library) -> dict[str, object]:
    heading = strings.LINEAGE_SUPERSEDED_BY
    if not relation.resolved:
        return _unresolved(heading, relation, library)
    newer = library.records_by_id.get(relation.record_id)
    if newer is None or not newer.is_decision:
        return _not_decision(heading, newer, relation, library)
    return _resolved(heading, older=record, newer=newer, library=library)


def _build_comparisons(record: Record, library: Library) -> list[dict[str, object]]:
    if not record.is_decision:
        return []
    comparisons = [
        _comparison_for_outbound(record, relation, library)
        for relation in record.outbound
        if relation.field == "supersedes"
    ]
    comparisons.extend(
        _comparison_for_inbound(record, relation, library)
        for relation in record.inbound
        if relation.field == "supersedes"
    )
    return comparisons


async def compare_view(request: Request) -> Response:
    library = get_library(request)
    record_id = request.path_params["record_id"]
    record = library.records_by_id.get(record_id)

    if record is None:
        return not_found(strings.LINEAGE_NOT_FOUND.format(record_id=record_id))

    sentence, _accent = language.status_sentence(library, record)
    return json_response(
        {
            "record": record_summary(record),
            "status_text": sentence,
            "comparisons": _build_comparisons(record, library),
            "no_comparison_text": strings.LINEAGE_NO_COMPARISON,
        }
    )
