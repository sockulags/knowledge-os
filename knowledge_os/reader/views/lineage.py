"""``GET /r/{record_id}/compare`` — a decision side by side with the prior
decision it supersedes, or the one that superseded it.

This is the third of the specification's four central flows (``docs/plans/
reader-v1.md`` Sec.4): "decision to supersedes or superseded-by with a
side-by-side comparison". A person must be able to see what a decision
replaced, what replaced it, and what actually changed between the two.

The corpus invariant this view relies on (``workspace._validate_decision_
supersession``, read but never imported) is: a decision supersedes exactly
one prior decision of the same scope, a draft replacement targets an active
decision, an active/superseded replacement targets an already-superseded
decision, and a superseded decision has exactly one effective replacement.
In a *valid* corpus the chain is therefore 1:1. This view does not assume
that invariant holds: a corpus that fails ``kos lint`` is still served, so a
missing supersession target, a target that is not itself a decision, or a
subject record with no lineage at all each render a clear explaining page
here rather than crash.

``trust_label`` collapses ``superseded``/``deprecated``/``archived`` into one
label, so status text here always reads ``Record.status`` directly (plus the
reversed ``supersedes`` edge on ``Record.inbound``) rather than the trust
label, per the unit contract's warning.

Keeps this module's public name ``view`` and its ``(request) -> Response``
signature so ``app.py`` never needs to change.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import Response

from .. import language, markdown, strings
from ..app import get_library, render
from ..library import Library, Record, Relation

_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Side:
    """One column of a comparison: a resolved decision and its status prose."""

    record: Record
    status_text: str


@dataclass(frozen=True)
class DiffBlock:
    """One paragraph-sized unit of the comparison.

    ``kind`` is one of "equal", "added", "removed", "changed". Exactly one of
    ``left_html``/``right_html`` is ``None`` for "added"/"removed"; both are
    set for "equal" and "changed". HTML is pre-rendered through
    ``markdown.render`` per paragraph so headings, lists, and code inside a
    single changed paragraph still render properly rather than as escaped
    unified-diff text.
    """

    kind: str
    left_html: str | None
    right_html: str | None


@dataclass(frozen=True)
class Comparison:
    """One supersession edge from the page's subject record, resolved (or
    not) to a renderable side-by-side comparison."""

    heading: str
    state: str  # "ok" | "missing" | "not_decision"
    detail: str | None
    left: Side | None
    right: Side | None
    blocks: tuple[DiffBlock, ...]
    summary: str | None


#: Thin wrapper over ``language.py``'s consolidated translation rules (task
#: 3), kept under this name so this module's own unit tests
#: (``tests/test_reader_lineage.py``) keep calling
#: ``lineage._status_text(record, lib)`` directly, unchanged. The
#: comparison heads (``Side.status_text``) read ``Record.status`` through
#: the same ``language.status_sentence`` every other view now uses, rather
#: than a lineage-specific copy: it already resolves a superseded record's
#: replacement and dates the same way (``language.successor_of``), and
#: reads ``Record.status`` (never the collapsed ``Record.trust_label``) for
#: exactly the reason this module's own comment used to give.
def _status_text(record: Record, library: Library) -> str:
    sentence, _accent = language.status_sentence(library, record)
    return sentence


def _paragraphs(body: str) -> list[str]:
    """Split a record body into paragraph-sized units for a readable diff.

    Splits on blank lines, but a blank line inside a fenced code block does
    not start a new unit, so a fenced example is compared (and rendered) as
    one block rather than being torn apart.
    """

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


def _diff_blocks(old_body: str, new_body: str) -> tuple[tuple[DiffBlock, ...], dict[str, int]]:
    """Compare two record bodies paragraph by paragraph.

    Uses ``difflib.SequenceMatcher`` over paragraphs (not a line-based
    unified diff) so what a person sees is "this paragraph was added/removed/
    reworded", each rendered through ``markdown.render``, rather than a raw
    diff dump of source lines.
    """

    old_paragraphs = _paragraphs(old_body)
    new_paragraphs = _paragraphs(new_body)
    matcher = difflib.SequenceMatcher(None, old_paragraphs, new_paragraphs, autojunk=False)
    blocks: list[DiffBlock] = []
    counts = {"added": 0, "removed": 0, "changed": 0}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                html = markdown.render(old_paragraphs[i1 + offset])
                blocks.append(DiffBlock("equal", html, html))
        elif tag == "delete":
            for index in range(i1, i2):
                blocks.append(DiffBlock("removed", markdown.render(old_paragraphs[index]), None))
                counts["removed"] += 1
        elif tag == "insert":
            for index in range(j1, j2):
                blocks.append(DiffBlock("added", None, markdown.render(new_paragraphs[index])))
                counts["added"] += 1
        elif tag == "replace":
            left_count = i2 - i1
            right_count = j2 - j1
            for offset in range(max(left_count, right_count)):
                left_text = old_paragraphs[i1 + offset] if offset < left_count else None
                right_text = new_paragraphs[j1 + offset] if offset < right_count else None
                blocks.append(
                    DiffBlock(
                        "changed",
                        markdown.render(left_text) if left_text is not None else None,
                        markdown.render(right_text) if right_text is not None else None,
                    )
                )
                counts["changed"] += 1
    return tuple(blocks), counts


def _summarize(counts: dict[str, int]) -> str:
    if not any(counts.values()):
        return strings.LINEAGE_SUMMARY_UNCHANGED
    return strings.LINEAGE_SUMMARY.format(added=counts["added"], removed=counts["removed"], changed=counts["changed"])


def _unresolved_comparison(heading: str, relation: Relation) -> Comparison:
    detail = strings.LINEAGE_MISSING_TARGET.format(record_id=relation.record_id)
    return Comparison(heading, "missing", detail, None, None, (), None)


def _non_decision_comparison(heading: str, target: Record | None, relation: Relation) -> Comparison:
    title = target.title if target is not None else relation.record_id
    detail = strings.LINEAGE_TARGET_NOT_DECISION.format(title=title)
    return Comparison(heading, "not_decision", detail, None, None, (), None)


def _resolved_comparison(heading: str, older: Record, newer: Record, library: Library) -> Comparison:
    blocks, counts = _diff_blocks(older.body, newer.body)
    return Comparison(
        heading=heading,
        state="ok",
        detail=None,
        left=Side(older, _status_text(older, library)),
        right=Side(newer, _status_text(newer, library)),
        blocks=blocks,
        summary=_summarize(counts),
    )


def _comparison_for_outbound(record: Record, relation: Relation, library: Library) -> Comparison:
    """``record`` supersedes ``relation``'s target: older on the left, the
    subject record (newer) on the right."""

    heading = strings.LINEAGE_SUPERSEDES
    if not relation.resolved:
        return _unresolved_comparison(heading, relation)
    target = library.records_by_id.get(relation.record_id)
    if target is None or not target.is_decision:
        return _non_decision_comparison(heading, target, relation)
    return _resolved_comparison(heading, older=target, newer=record, library=library)


def _comparison_for_inbound(record: Record, relation: Relation, library: Library) -> Comparison:
    """``relation``'s source supersedes the subject record: the subject
    (older) on the left, its replacement (newer) on the right.

    ``library.py`` builds every inbound relation from an already-parsed
    document, so ``relation.resolved`` is always true here; the check is
    kept anyway so a future change to that guarantee degrades instead of
    raising a ``KeyError``.
    """

    heading = strings.LINEAGE_SUPERSEDED_BY
    if not relation.resolved:
        return _unresolved_comparison(heading, relation)
    newer = library.records_by_id.get(relation.record_id)
    if newer is None or not newer.is_decision:
        return _non_decision_comparison(heading, newer, relation)
    return _resolved_comparison(heading, older=record, newer=newer, library=library)


def _build_comparisons(record: Record, library: Library) -> tuple[Comparison, ...]:
    if not record.is_decision:
        return ()
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
    return tuple(comparisons)


async def view(request: Request) -> Response:
    library = get_library(request)
    record_id = request.path_params["record_id"]
    record = library.records_by_id.get(record_id)

    if record is None:
        return render(
            request,
            "compare.html",
            page_title=strings.PAGE_TITLES["lineage"],
            library=library,
            record=None,
            record_id=record_id,
            status_text=None,
            comparisons=(),
            not_found_message=strings.LINEAGE_NOT_FOUND.format(record_id=record_id),
            status_code=404,
        )

    return render(
        request,
        "compare.html",
        page_title=record.title,
        library=library,
        record=record,
        record_id=record_id,
        status_text=_status_text(record, library),
        comparisons=_build_comparisons(record, library),
        not_found_message=None,
    )
