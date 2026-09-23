"""Shared JSON-shaping helpers for every ``api/*.py`` endpoint module.

Mirrors the role the old ``views/*.py`` package played: this is a
non-adapter module (no ``knowledge_os.*`` import beyond the bare
``Workspace``/``WorkspaceError`` handle, which it does not even need), pure
over the frozen dataclasses ``library.py`` already built. It never composes
a sentence itself — every sentence comes from ``language.py`` or
``strings.py`` — it only reshapes already-finished data into the small,
stable JSON shapes the React frontend renders.

A ``Pill`` is the one place colour is decided (design brief: "Colour means
something, and appears only there, as small pill badges"): a tone in
``{"green", "amber", "yellow", "grey", "violet", None}`` plus the short
label shown on the badge. ``language.record_accent`` decides only *whether*
a record carries the reader's original four rail accents (proposed /
unverified / retired / raw); ``pill_for`` below is a superset built for the
five UI states the design brief names, kept here (not in ``language.py``)
because it is a presentation choice about which of two already-true facts
(status vs. trust) gets the badge, not a new contract-to-language rule.
"""

from __future__ import annotations

import datetime
import re
from typing import TypedDict

from .. import grouping, language, strings
from ..library import Library, ProvenanceEntry, Record, Relation, content_sha256, decision_actions

__all__ = [
    "Pill",
    "pill_for",
    "record_summary",
    "record_summary_with_sentence",
    "properties_block",
    "technical_details",
    "relation_view",
    "lineage_callouts",
    "relative_date",
    "project_title",
    "record_index_entry",
    "project_tree_json",
    "breadcrumb_for_record",
    "strip_leading_h1",
    "decision_language",
    "decision_actions_json",
]

#: A leading level-1 heading only, on the first non-blank line of a
#: document's body. Both a managed record's own body and an unmanaged
#: repo document's body use the frontmatter title / first-heading text as
#: the page's single <h1> already (Library.read_repo_document falls back to
#: the first heading precisely because it *is* the title there), so
#: repeating it as the first line of rendered prose would just show the
#: same words twice.
_LEADING_H1 = re.compile(r"^#\s+\S.*$")


def strip_leading_h1(body: str) -> str:
    """Drop a body's leading level-1 heading, if it has one (see module
    comment above). Only the very first heading is affected; everything
    else in the body renders unchanged."""

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


class Pill(TypedDict, total=False):
    label: str
    tone: str | None


#: Non-decision trust labels that read as "unconfirmed" per the design
#: brief ("a draft or never-confirmed record, or an unconfirmed
#: observation"): a durable record nobody has verified yet.
_UNCONFIRMED_TRUST_LABELS = ("draft durable; not verified", "active durable; not verified")

#: Record.status -> strings.PILL_LABELS key, for the two non-decision
#: lifecycle statuses that carry the grey "replaced" tone (design brief:
#: "Replaced, discouraged or archived: grey"). Not a direct
#: ``PILL_LABELS.get(record.status, ...)`` lookup: the status literal is
#: "deprecated", but its pill word is "Discouraged" -- the two spellings
#: differ on purpose (contract vocabulary vs. reader prose), so this map is
#: the one place that difference is bridged.
_LIFECYCLE_PILL_KEY = {"deprecated": "discouraged", "archived": "archived"}


def pill_for(record: Record) -> Pill | None:
    """The one colour badge a record carries, or ``None`` for neutral.

    Judged on ``status``/``type`` first (what the reader should *believe*),
    falling back to ``trust_label`` only for an ordinary durable record,
    exactly mirroring ``language.record_accent``'s precedence but mapped
    onto the five states the design brief names instead of the original
    four rail accents.
    """

    if record.is_decision:
        if record.status == "draft":
            return {"label": strings.PILL_LABELS["proposed"], "tone": "amber"}
        if record.status == "active":
            return {"label": strings.PILL_LABELS["in_force"], "tone": "green"}
        if record.status == "superseded":
            return {"label": strings.PILL_LABELS["replaced"], "tone": "grey"}
        if record.status == "archived":
            return {"label": strings.PILL_LABELS["withdrawn"], "tone": "grey"}
        if record.status in _LIFECYCLE_PILL_KEY:
            label = strings.PILL_LABELS[_LIFECYCLE_PILL_KEY[record.status]]
            return {"label": label, "tone": "grey"}
        return None
    if record.type == "discovery":
        if record.status == "proposed":
            return {"label": strings.PILL_LABELS["unconfirmed"], "tone": "yellow"}
        if record.status == "rejected":
            return {"label": strings.PILL_LABELS["dismissed"], "tone": "grey"}
        return None
    if record.type == "source":
        return {"label": strings.PILL_LABELS["raw"], "tone": "violet"}
    if record.trust_label in _UNCONFIRMED_TRUST_LABELS:
        return {"label": strings.PILL_LABELS["unconfirmed"], "tone": "yellow"}
    if record.trust_label == "unusable durable record":
        pill_key = _LIFECYCLE_PILL_KEY.get(record.status, "replaced")
        return {"label": strings.PILL_LABELS[pill_key], "tone": "grey"}
    return None


def project_id_for_scope(scope: str) -> str | None:
    if scope == "general" or not scope.startswith("project:"):
        return None
    return scope.removeprefix("project:")


def project_title(library: Library, project_id: str) -> str:
    """The project's short display name, everywhere it is used to *name*
    the project (the sidebar, a breadcrumb, a catalog's Project column) --
    never the raw overview-record title, which reads "<Name> project
    overview" for every project in the real corpus. The overview page's
    own ``<h1>`` shows ``Record.title`` directly instead of calling this."""

    project = library.records_by_id.get(project_id)
    if project is None:
        return project_id
    return language.display_project_title(project.title)


def record_summary(record: Record) -> dict[str, object]:
    """The compact shape used everywhere a record appears in a list: the
    quick-find/record index, a project tree node, a search or catalog row."""

    return {
        "id": record.id,
        "title": record.title,
        "type": record.type,
        "record_kind": record.record_kind,
        "is_decision": record.is_decision,
        "status_pill": pill_for(record),
        "project": project_id_for_scope(record.scope),
        "updated": record.updated,
    }


def record_summary_with_sentence(library: Library, record: Record) -> dict[str, object]:
    """``record_summary`` plus the one-line meaning sentence a card shows
    next to a record (e.g. a project's "In force now" row, or the home
    page's "Waiting on you" list)."""

    sentence, _accent = language.status_sentence(library, record)
    summary = record_summary(record)
    summary["sentence"] = sentence
    return summary


def record_index_entry(kind: str, *, id: str, title: str, pill: Pill | None, project: str | None) -> dict[str, object]:
    """One row of the quick-find index (workspace nav): a record, a skill,
    or a repository document, all in the same flat shape so client-side
    title search never has to special-case which kind of page it found."""

    return {"id": id, "title": title, "kind": kind, "status_pill": pill, "project": project}


def properties_block(library: Library, record: Record) -> dict[str, object]:
    """The Notion-style two-column properties block under a document's
    title: Status, Trust, Applies to, Updated, Source. Every value is a
    finished sentence from ``language.py``; nothing here inspects a raw
    contract token."""

    status_sentence, _status_accent = language.status_sentence(library, record)
    trust_sentence, _trust_accent = language.trust_sentence(record)
    provenance_sentences = [language.provenance_sentence(library, record, entry) for entry in record.provenance]
    # The one pill a record carries (pill_for) goes on whichever row it
    # actually describes: a decision's pill is a lifecycle state (in force
    # / waiting on you / replaced), so it belongs on Status; every other
    # record's pill (unconfirmed / raw material / dismissed) is an
    # epistemic judgment, so it belongs on Trust. Putting it on Status for
    # a non-decision would read as a contradiction next to that row's own
    # "Current" sentence -- "Unconfirmed" next to "Current" looks like the
    # page disagrees with itself, when the pill was only ever about trust.
    pill = pill_for(record)
    status_pill = pill if record.is_decision else None
    trust_pill = None if record.is_decision else pill
    return {
        "status": {"label": strings.DOCUMENT_STATUS_HEADER, "value": status_sentence, "pill": status_pill},
        "trust": {"label": strings.DOCUMENT_TRUST_HEADER, "value": trust_sentence, "pill": trust_pill},
        "applies_to": {"label": "Applies to", "value": language.scope_sentence(library, record)},
        "updated": {
            "label": "Updated",
            "value": language.format_date(record.updated),
            "raw": record.updated,
        },
        "source": {"label": "Source", "value": provenance_sentences},
    }


def _provenance_json(entry: ProvenanceEntry) -> dict[str, object]:
    return {"kind": entry.kind, "reference": entry.reference, "captured": entry.captured, "sha256": entry.sha256}


def technical_details(record: Record, content_sha256_value: str) -> dict[str, object]:
    """The collapsed "Technical details" toggle: the exact contract values,
    never shown outside this one block (design brief, "Document")."""

    return {
        "status": record.status,
        "trust_label": record.trust_label,
        "scope": record.scope,
        "record_kind": record.record_kind,
        "path": record.path,
        "content_sha256": content_sha256_value,
        "provenance": [_provenance_json(entry) for entry in record.provenance],
    }


def relation_view(relation: Relation) -> dict[str, object]:
    """One relation row (inbound or outbound), with the same broken-relation
    treatment ``states.relation_label`` gives the old HTML rail, plus an
    ``href`` the frontend can navigate to directly (a ``supersedes`` edge
    points at the compare page, matching ``views/document.py``'s original
    rule)."""

    if not relation.resolved:
        return {
            "field": relation.field,
            "record_id": relation.record_id,
            "title": None,
            "resolved": False,
            "href": None,
            "label": strings.BROKEN_RELATION.format(record_id=relation.record_id),
        }
    href = (
        f"/r/{relation.record_id}/compare" if relation.field == "supersedes" else f"/r/{relation.record_id}"
    )
    return {
        "field": relation.field,
        "record_id": relation.record_id,
        "title": relation.title,
        "resolved": True,
        "href": href,
        "label": relation.title or relation.record_id,
    }


def lineage_callouts(library: Library, record: Record) -> list[dict[str, object]]:
    """The lineage callout(s) at the top of a document page: "Replaced by X
    on <date>" when this record was superseded, and/or "Supersedes Y" when
    this record itself replaces another. Both can apply at once (a decision
    that replaced one proposal and was later itself replaced)."""

    callouts: list[dict[str, object]] = []
    if record.is_decision and record.status == "superseded":
        successor = language.successor_of(library, record)
        if successor is not None:
            date = language.format_date(successor.accepted_at) or language.format_date(successor.updated)
            callouts.append(
                {
                    "kind": "superseded_by",
                    "text": strings.LINEAGE_CALLOUT_SUPERSEDED_BY.format(title=successor.title, date=date),
                    "compare_href": f"/r/{record.id}/compare",
                }
            )
        else:
            callouts.append(
                {"kind": "superseded_by", "text": strings.DOCUMENT_SUPERSEDED_UNKNOWN, "compare_href": f"/r/{record.id}/compare"}
            )
    for relation in record.outbound:
        if relation.field != "supersedes":
            continue
        title = relation.title or relation.record_id
        template = strings.LINEAGE_CALLOUT_WOULD_REPLACE if record.status == "draft" else strings.LINEAGE_CALLOUT_SUPERSEDES
        callouts.append(
            {
                "kind": "supersedes",
                "text": template.format(title=title),
                "compare_href": f"/r/{record.id}/compare",
            }
        )
    return callouts


def _parse_date(value: str) -> datetime.date | None:
    text = value.strip()
    try:
        if "T" in text:
            return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        return datetime.date.fromisoformat(text)
    except ValueError:
        return None


def relative_date(value: str | None, *, today: datetime.date | None = None) -> str | None:
    """"6 days ago" for the home page's recently-changed list; the caller
    also has ``language.format_date`` available for the exact date shown on
    hover (design brief: "a compact list with relative dates ..., and the
    exact date on hover"). Falls back to the exact formatted date for
    anything that does not parse or is far enough in the past that a
    relative phrase stops being useful."""

    if not value:
        return None
    parsed = _parse_date(value)
    if parsed is None:
        return language.format_date(value)
    reference = today or datetime.datetime.now(datetime.timezone.utc).date()
    delta = (reference - parsed).days
    if delta < 0:
        return language.format_date(value)
    if delta == 0:
        return "today"
    if delta == 1:
        return "yesterday"
    if delta < 30:
        return f"{delta} days ago"
    if delta < 365:
        months = max(delta // 30, 1)
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = max(delta // 365, 1)
    return f"{years} year{'s' if years != 1 else ''} ago"


def _tree_node_json(node: grouping.ProjectTreeNode) -> dict[str, object]:
    return {
        "name": node.name,
        "overview": record_summary(node.overview) if node.overview is not None else None,
        "records": [record_summary(record) for record in node.records],
        "broken": [{"path": item.path, "message": item.message} for item in node.broken],
        "children": [_tree_node_json(child) for child in node.children],
    }


def project_tree_json(project_id: str, records: list[Record], broken: list) -> dict[str, object]:
    """The full navigation tree for one project: every record scoped to it
    (decisions included, unlike the project page's own meaning-grouped
    tree in the original HTML reader), mirroring ``projects/<id>/`` on
    disk, for the sidebar and the project page's "Pages in this project"
    list alike."""

    tree = grouping.build_project_tree(project_id, records, broken)
    return _tree_node_json(tree)


def breadcrumb_for_record(library: Library, record: Record) -> list[dict[str, str]]:
    """[{"label", "href"}, ...] not including the record's own title (the
    page's own <h1> already shows that)."""

    workspace_name = library.workspace_name or strings.APP_NAME
    crumbs = [{"label": workspace_name, "href": "/"}]
    project_id = project_id_for_scope(record.scope)
    if project_id is not None:
        crumbs.append({"label": project_title(library, project_id), "href": f"/p/{project_id}"})
    return crumbs


# ---------------------------------------------------------------------------
# Decisions: the shared vocabulary, the "How decisions work" guide, and the
# finished text of each action's confirmation dialog. Used by the record
# page and the Decide inbox alike, so both say the same thing.
# ---------------------------------------------------------------------------

#: Lifecycle status -> the key the interface uses for that state (never the
#: raw status, which stays in Technical details).
_DECISION_STATES = {"draft": "proposed", "active": "in_force", "superseded": "replaced", "archived": "withdrawn"}


def decision_language() -> dict[str, object]:
    """The decision words the interface needs that do not depend on one
    decision: button labels, and the guide with one line per state."""

    return {
        "labels": dict(strings.DECISION_ACTION_LABELS),
        "guide": {
            "title": strings.DECISION_GUIDE_TITLE,
            "intro": strings.DECISION_GUIDE_INTRO,
            "undo": strings.DECISION_GUIDE_UNDO,
            "states": [
                {"key": key, "label": strings.DECISION_STATE_LABELS[state], "text": strings.DECISION_GUIDE_STATES[state]}
                for state, key in _DECISION_STATES.items()
            ],
        },
    }


def _change(subject: str | None, before: str, after: str) -> dict[str, str | None]:
    return {"subject": subject, "from": before, "to": after}


def _dialog(action: str, changes: list[dict[str, str | None]], **fields: str) -> dict[str, object]:
    copy = strings.DECISION_DIALOGS[action]
    return {
        "title": copy["title"],
        "body": copy["body"].format(**fields),
        "confirm": copy["confirm"],
        "history": copy["history"],
        "changes": changes,
    }


def decision_actions_json(library: Library, record: Record) -> dict[str, object] | None:
    """Which lifecycle actions a decision offers, the sentence above its
    buttons, and the finished text of each confirmation dialog; ``None`` for
    a record that is not a decision. ``supersede`` names the decision in
    force a proposed replacement would retire, with its current hash."""

    actions = decision_actions(library, record)
    if actions is None:
        return None
    labels = strings.DECISION_STATE_LABELS
    project = language.scope_sentence(library, record)
    replaces = None
    dialogs: dict[str, object] = {}
    if actions.accept:
        dialogs["accept"] = _dialog(
            "accept",
            [_change(None, labels["draft"], strings.DECISION_DIALOG_ACCEPTED_TODAY)],
            title=record.title,
            project=project,
        )
    if actions.withdraw:
        dialogs["withdraw"] = _dialog(
            "withdraw", [_change(None, labels["draft"], labels["archived"])], title=record.title
        )
    if actions.replaces is not None:
        target = actions.replaces
        try:
            target_sha = content_sha256(target.abs_path)
        except OSError:
            target_sha = None
        replaces = {"id": target.id, "title": target.title, "status": target.status, "content_sha256": target_sha}
        dialogs["supersede"] = _dialog(
            "supersede",
            [
                _change(record.title, labels["draft"], strings.DECISION_DIALOG_ACCEPTED_TODAY),
                _change(target.title, labels["active"], strings.DECISION_DIALOG_REPLACED_BY.format(title=record.title)),
            ],
            title=record.title,
            old=target.title,
        )

    if record.status == "draft":
        if replaces is not None:
            summary = strings.DECISION_SUMMARY["proposed_replacement"].format(title=replaces["title"])
        elif not actions.accept:
            summary = strings.DECISION_SUMMARY["proposed_blocked"]
        else:
            summary = strings.DECISION_SUMMARY["proposed"]
    elif record.status == "active":
        summary = strings.DECISION_SUMMARY["in_force"]
    else:
        summary = None

    return {
        "accept": actions.accept,
        "withdraw": actions.withdraw,
        "supersede": replaces,
        "propose_replacement": actions.propose_replacement,
        "summary": summary,
        "dialogs": dialogs,
    }
