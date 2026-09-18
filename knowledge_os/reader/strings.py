"""Every user-facing string the reader shows, in one module.

The interface is in English throughout and speaks to a person, not to the
schema: contract vocabulary (``draft``, ``scope``, ``provenance``,
``content_sha256``, trust labels, file paths) must never reach the primary
reading path. It stays exact and reachable one click away, under a collapsed
"technical details" disclosure (see ``TECHNICAL_DETAILS_LABEL`` below).

Organisation: one section per view, each a plain ``dict[str, str]`` or a
module-level constant, so eleven other agents can each append their own
section without colliding. A string containing ``{placeholder}`` is a format
template; the view fills in the named placeholder(s) with data already on
``library.Record`` (see the comment above each template for which fields).

Provenance ``kind`` is an open vocabulary with no enum in the core. Only the
kinds with prose given in ``docs/plans/reader-v1.md`` Sec.5 get bespoke
phrasing in ``PROVENANCE_KIND`` below; every other kind (including the other
kinds already on disk today: ``project-definition``, ``repository-
documentation``, ``repository-file``, ``user-request``, ``local-file``,
``editorial-update``, ``fixture``) falls back to ``PROVENANCE_KIND_FALLBACK``,
which shows the raw kind and reference rather than guessing at prose.

Where the plan's language table (Sec.5) or state table (Sec.6) gives exact
quoted copy, it is transcribed verbatim and marked "(verbatim)" in a comment.
Everything else here is a reasonable extrapolation in the same voice, added
because a real workspace can reach these states (an ordinary draft record, a
promoted discovery, an unreadable file) and the one-module rule means that
copy belongs here rather than hand-written inline in a view. Stage-B units
are free to adjust wording or add keys; they should not need to add a new
module to do it.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Shared vocabulary: trust, lifecycle, and scope (used from the metadata
# rail, the "technical details" disclosure, and any grouped listing)
# ---------------------------------------------------------------------------

#: Label for the collapsed disclosure that holds exact contract vocabulary
#: (status, scope, provenance kind, trust label, path, content_sha256).
TECHNICAL_DETAILS_LABEL = "Technical details"
TECHNICAL_DETAILS_HINT = "The exact record data, for someone who wants it."

#: "outside the record contract" (verbatim, Sec.5). Shown on every page where
#: the unmanaged repo-document tier appears (acceptance criterion 11).
UNMANAGED_TIER_LABEL = "Lives in the repository, not in the library. Agents never read these."

#: Maps every string ``context_policy.trust_label()`` can return (there are
#: exactly seven) plus the reader's own ``"operational guidance"`` label for
#: skills (that eighth label is never returned by ``trust_label()`` itself;
#: ``library.py`` assigns it directly) to a human sentence. ``"verified
#: durable"`` is a template: fill ``{date}`` from ``Record.verified``.
TRUST_LABELS: dict[str, str] = {
    # "raw source; not established knowledge" (verbatim key from context_policy)
    "raw source; not established knowledge": "Raw material. Nobody has checked it.",
    # (verbatim, Sec.5, as "retained discovery")
    "reviewed observation; not established knowledge": "Observation — reviewed, but not knowledge",
    # Covers proposed/rejected/promoted discoveries alike; DISCOVERY_STATUS
    # below gives the sharper per-status phrasing the plan actually asks for.
    "discovery observation; not default context": "Observation, not reviewed as knowledge",
    "draft durable; not verified": "Draft, not confirmed",
    "active durable; not verified": "In use, but never confirmed",
    "verified durable": "Confirmed {date}",
    # Collapses superseded/deprecated/archived; DECISION_STATUS and
    # LIFECYCLE_STATUS below give the sharper per-status phrasing.
    "unusable durable record": "No longer in effect",
    "operational guidance": "Operational guidance for agents, not a record of knowledge.",
}

#: Decision status -> sentence. "active" needs ``{date}`` (Record.accepted_at,
#: formatted by the view); "superseded" needs ``{title}`` and ``{date}`` of
#: the replacement (resolve via the outbound/inbound "supersedes" relation).
DECISION_STATUS: dict[str, str] = {
    "draft": "Proposal — nobody has taken a position yet",  # verbatim, Sec.5
    "active": "In force — accepted {date}",  # verbatim pattern, Sec.5 ("accepted 30 August")
    "superseded": "Replaced by {title} on {date}",  # verbatim pattern, Sec.5
}

#: Status label for non-decision durable records (ordinary knowledge/project,
#: memory, synthesis). "superseded" is rare outside decisions but the schema
#: allows it, so a template is provided for completeness.
LIFECYCLE_STATUS: dict[str, str] = {
    "active": "Current",  # verbatim, Sec.5 ("ordinary active")
    "draft": "Draft",  # extrapolation: no non-decision draft row is quoted
    "deprecated": "Discouraged",  # verbatim, Sec.5
    "archived": "Archived",  # verbatim, Sec.5
    "superseded": "Replaced by {title} on {date}",  # extrapolation, mirrors DECISION_STATUS
}

#: Discovery status -> sentence. trust_label() cannot distinguish these three
#: non-retained statuses from each other (they all collapse to "discovery
#: observation; not default context"), so read status directly instead.
DISCOVERY_STATUS: dict[str, str] = {
    "proposed": "Unconfirmed observation",  # verbatim, Sec.5
    "retained": "Observation — reviewed, but not knowledge",  # verbatim, Sec.5
    "rejected": "Dismissed observation",  # verbatim, Sec.5
    "promoted": "Promoted — folded into a new draft record",  # extrapolation
}

#: "scope: general" (verbatim, Sec.5). "scope: project:<slug>" has no static
#: string; the reader shows that project's own title instead (Record.title
#: of the record whose id equals the scope's slug).
SCOPE_GENERAL = "Applies everywhere"

#: Provenance kind -> sentence, for the three kinds the plan gives exact
#: prose for. ``{date}`` comes from the provenance entry's ``captured``;
#: ``{reference}`` from its ``reference``; ``{title}`` from resolving that
#: reference against ``Library.records_by_id`` (only meaningful for
#: "discovery", whose reference is a record id).
PROVENANCE_KIND: dict[str, str] = {
    "user-approved-conversation": "A conversation you approved on {date}",  # verbatim, Sec.5
    "decision-acceptance": "Accepted in {reference}",  # verbatim, Sec.5
    "discovery": "Came from the observation {title}",  # verbatim, Sec.5
}

#: Fallback for every other provenance kind, known or not (see module
#: docstring): show the raw kind and reference rather than guess at prose.
PROVENANCE_KIND_FALLBACK = "{kind}: {reference}"

# ---------------------------------------------------------------------------
# Index health (library.IndexHealth.message; see Sec.6 "Stale index" /
# "Missing index")
# ---------------------------------------------------------------------------

INDEX_HEALTH: dict[str, str] = {
    # verbatim, Sec.5 / Sec.6 "stale index"
    "stale": "Search may be missing recent changes. Run `kos index` to refresh.",
    # Sec.6 "Missing index": "reported as 'search unavailable'"
    "absent": "Search is unavailable. Run `kos index` to build it.",
    "unreadable": "Search is unavailable. The search index could not be read ({detail}). Run `kos index` to rebuild it.",
}

# ---------------------------------------------------------------------------
# Broken records and relations (Sec.6 "Broken record" / "Broken relation" /
# "Unreadable content")
# ---------------------------------------------------------------------------

BROKEN_RECORD_LABEL = "Broken record"
#: {message} is the exact lint message from BrokenRecord.message.
BROKEN_RECORD_DETAIL = "This file could not be read as a record: {message}"

#: "points at unknown id X" (verbatim pattern, Sec.6 "Broken relation").
#: {record_id} is Relation.record_id when Relation.resolved is False.
BROKEN_RELATION = "points at unknown id {record_id}"

#: Repo-document (unmanaged tier) read failures. {path} is the requested
#: repo-relative path; {detail} is the underlying error for the "unsafe path"
#: case, which already carries enough context to be shown as-is.
REPO_DOCUMENT_NOT_FOUND = "{path} could not be read: the file no longer exists."
REPO_DOCUMENT_NOT_UTF8 = "{path} could not be read: the file is not valid UTF-8 text."
REPO_DOCUMENT_UNSAFE = "{path} could not be read: {detail}"

# ---------------------------------------------------------------------------
# Workspace health line (Sec.6 "Lint failing globally" / "Empty workspace")
# ---------------------------------------------------------------------------

LINT_OK = "All managed records pass `kos lint`."
#: {count} is len(Library.issues).
LINT_ISSUES = "{count} issue(s) found by `kos lint`."

EMPTY_WORKSPACE_TITLE = "This workspace has no durable records yet"
EMPTY_WORKSPACE_BODY = (
    "A record is a Markdown file with YAML frontmatter that Knowledge OS has "
    "validated: a decision, a piece of knowledge, a project note, or a skill. "
    "Run `kos capture` to add the first one."
)

# ---------------------------------------------------------------------------
# Shell / navigation (base.html and every view's nav block)
# ---------------------------------------------------------------------------

APP_NAME = "Knowledge OS Reader"
NAV_START = "Start"
NAV_SEARCH = "Search"
NAV_EVERYTHING = "Everything"
RAIL_TOGGLE_LABEL = "Metadata"

#: Fallback page titles, keyed by view name; a view should prefer a record's
#: own title when it has one.
PAGE_TITLES: dict[str, str] = {
    "start": "Start",
    "project": "Project",
    "document": "Record",
    "lineage": "Compare",
    "skill": "Skill",
    "repodoc": "Repository document",
    "search": "Search",
    "everything": "Everything",
}

#: Placeholder body for a view not yet implemented (unit 0 stubs only; every
#: stage-B unit replaces its own view's use of this string).
STUB_NOT_IMPLEMENTED = "This view is not implemented yet."

# ---------------------------------------------------------------------------
# Start view
# ---------------------------------------------------------------------------

START_RECENTLY_CHANGED = "Recently changed"
START_OPEN_DECISIONS = "Open decisions awaiting a position"
START_PROJECTS = "Projects"
#: {records}, {skills}, {issues} are counts from the loaded Library.
START_HEALTH_LINE = "{records} record(s) · {skills} skill(s) · {issues} issue(s)"

# ---------------------------------------------------------------------------
# Project view
# ---------------------------------------------------------------------------

#: Group header, keyed by group slug. Grouping logic (which record lands in
#: which group) belongs to views/project.py, not here.
PROJECT_GROUP_HEADERS: dict[str, str] = {
    "governing": "Governing now",
    "proposed": "Proposed",
    "historical": "Historical",
    "observations": "Observations",
    "raw_material": "Raw material",
    "related_general": "Related general knowledge, memory, and skills",
}

#: Empty-group sentence, keyed by the same group slugs (Sec.6 "Empty project
#: group": "The group header stays visible with an explaining sentence...
#: Never hidden."). "historical" and "observations" are verbatim, Sec.6.
PROJECT_GROUP_EMPTY: dict[str, str] = {
    "governing": "Nothing currently governs this project.",
    "proposed": "No proposal is waiting on a decision.",
    "historical": "No decision has been superseded yet.",  # verbatim, Sec.6
    "observations": "No agent has left an observation here.",  # verbatim, Sec.6
    "raw_material": "No raw material has been captured for this project.",
    "related_general": "No general knowledge, memory, or skill is linked here yet.",
}

# ---------------------------------------------------------------------------
# Document view
# ---------------------------------------------------------------------------

DOCUMENT_PROVENANCE_HEADER = "Provenance"
DOCUMENT_RELATED_HEADER = "Related"
DOCUMENT_INBOUND_HEADER = "Points here"
DOCUMENT_TOC_HEADER = "On this page"

# ---------------------------------------------------------------------------
# Lineage / compare view
# ---------------------------------------------------------------------------

LINEAGE_SUPERSEDES = "Supersedes"
LINEAGE_SUPERSEDED_BY = "Superseded by"
LINEAGE_NO_COMPARISON = "This record has no supersession lineage to compare."

# ---------------------------------------------------------------------------
# Search view
# ---------------------------------------------------------------------------

SEARCH_PLACEHOLDER = "Search the workspace"
SEARCH_NO_RESULTS = "No matching records."
SEARCH_EMPTY_QUERY = "Type something to search."

# ---------------------------------------------------------------------------
# Everything view
# ---------------------------------------------------------------------------

EVERYTHING_TITLE = "Everything"
EVERYTHING_EMPTY = "This workspace has no records yet."

# ---------------------------------------------------------------------------
# Skill view
# ---------------------------------------------------------------------------

SKILL_TRUST_LABEL = TRUST_LABELS["operational guidance"]

# ---------------------------------------------------------------------------
# Repository-document (unmanaged tier) view
# ---------------------------------------------------------------------------

REPODOC_LABEL = UNMANAGED_TIER_LABEL

# ---------------------------------------------------------------------------
# Markdown rendering (knowledge_os/reader/markdown.py)
# ---------------------------------------------------------------------------

#: Title/tooltip for a relative record-to-record link that render() could
#: not place (a bare directory, or a path outside the corpus). The link
#: itself degrades to plain, non-clickable text rather than a link that
#: would 404; this is the one hint of why, on hover.
MARKDOWN_LINK_UNRESOLVED = "This link could not be resolved to a record."
# Document view — unit 1 additions (docs/plans/reader-v1.md Sec.4 "Document")
#
# The status/trust/scope/relation sentences the document view itself
# composes (from DECISION_STATUS, LIFECYCLE_STATUS, DISCOVERY_STATUS,
# TRUST_LABELS, PROVENANCE_KIND and SCOPE_GENERAL above) already cover the
# reusable vocabulary; the labels below are this view's own rail section
# headers and the small set of states those tables don't reach: a decision
# resolved via a supersession relation with no known successor, an empty
# relation list, and an unknown record id.
# ---------------------------------------------------------------------------

DOCUMENT_STATUS_HEADER = "Status"
DOCUMENT_TRUST_HEADER = "Trust"
DOCUMENT_SCOPE_HEADER = "Scope"

#: {count} is the number of provenance entries held back behind the
#: <details> overflow (see views/document.py) so a record with many
#: repository-file entries does not dominate the rail.
DOCUMENT_PROVENANCE_MORE = "{count} more"

#: Fallback for LIFECYCLE_STATUS["superseded"] / DECISION_STATUS["superseded"]
#: when no inbound "supersedes" relation resolves to a successor record
#: (a possible but unusual data state: the plan does not give exact copy for
#: it, so this is an extrapolation in the same voice as the rest of Sec.5).
DOCUMENT_SUPERSEDED_UNKNOWN = "Replaced, but the replacement could not be found."

DOCUMENT_RELATED_EMPTY = "This record points at nothing else."
DOCUMENT_INBOUND_EMPTY = "No other record points here yet."

DOCUMENT_NOT_FOUND_TITLE = "Record not found"
#: {record_id} is the unmatched path segment from GET /r/{record_id}.
DOCUMENT_NOT_FOUND_BODY = 'No record with id "{record_id}" exists in this workspace.'

RAIL_TOGGLE_HIDE = "Hide metadata"
RAIL_TOGGLE_SHOW = "Show metadata"
# Unit 2 -- Project view (views/project.py, grouping.py, templates/project.html)
#
# The five meaning-group headers/empty sentences already live above
# (PROJECT_GROUP_HEADERS, PROJECT_GROUP_EMPTY); this section covers the
# project page's remaining strings: the ordinary-content directory tree
# (which is navigation, not a sixth meaning group), short status badges, and
# the technical-details field labels for a project's overview record.
# ---------------------------------------------------------------------------

#: Header and empty sentence for the project's own directory tree of
#: ordinary (non-decision) content -- distinct from PROJECT_GROUP_HEADERS
#: because this is the directory-tree navigation described in the accepted
#: project-directory-layout decision, not one of the five meaning groups.
PROJECT_TREE_HEADER = "Project documents"
PROJECT_TREE_EMPTY = "This project has no other documents yet."

#: The project root's own overview node has no directory name to show;
#: PROJECT_TREE_ROOT_LABEL stands in for it in the tree when the root itself
#: also holds plain records alongside its subdirectories.
PROJECT_TREE_ROOT_LABEL = "Project root"

#: Short pill text for the four accent badges (see static/reader.css's
#: token comment for what each accent means), used on a project's record
#: cards. The longer sentence next to the card (DECISION_STATUS,
#: LIFECYCLE_STATUS, DISCOVERY_STATUS, or TRUST_LABELS) always carries the
#: full meaning; the badge is a glance-only echo of the same signal.
PROJECT_BADGE_LABELS: dict[str, str] = {
    "proposed": "Proposed",
    "unverified": "Unconfirmed",
    "retired": "Replaced",
    "raw": "Raw",
}

#: Shown when a project id in the URL matches no project overview.
#: {project_id} is the raw path segment, already URL-decoded by the router.
PROJECT_NOT_FOUND = 'No project named "{project_id}" was found in this workspace.'

#: Defensive fallback when a record's status is not one of the values this
#: view's mapping tables expect (unreachable for a corpus that passed
#: validate_workspace, kept only so a genuinely unexpected value degrades to
#: a plain sentence rather than leaking the raw status string).
PROJECT_STATUS_UNKNOWN = "Status information is not available for this record."

#: Field labels for the project overview's "technical details" disclosure
#: (see TECHNICAL_DETAILS_LABEL above). Exact contract vocabulary values are
#: filled in by the view; these are only the field names.
PROJECT_DETAILS_STATUS = "Status"
PROJECT_DETAILS_SCOPE = "Scope"
PROJECT_DETAILS_PATH = "Path"
PROJECT_DETAILS_CONTENT_HASH = "Content hash"
PROJECT_DETAILS_TRUST = "Trust"
# Start view — additional strings (unit 3)
#
# START_RECENTLY_CHANGED, START_OPEN_DECISIONS, START_PROJECTS, and
# START_HEALTH_LINE already exist above (unit 0). These fill in the
# remaining copy views/start.py needs: per-section empty sentences (Sec.6
# "Empty project group" applies the same "never hidden, explain instead"
# rule to the start page's own groups), the skills group, the one labelled
# entry point into the unmanaged repo-document tier (acceptance criterion
# 2; the tier's own browsing surface belongs to a different unit), and the
# index-health/broken-record lines the health rail reports (Library.index
# already carries user-facing text for "stale"/"absent"/"unreadable"; only
# the healthy case and the broken-record count need copy here).
# ---------------------------------------------------------------------------

START_SKILLS = "Skills"

#: Empty-section sentences, shown instead of hiding the section (mirrors
#: PROJECT_GROUP_EMPTY's rule, kept separate because these are the start
#: page's own groups, not a project's meaning-groups).
START_NO_RECENT_CHANGES = "Nothing has changed yet."
START_NO_OPEN_DECISIONS = "No decision is waiting on a position."
START_NO_PROJECTS = "No project exists yet."
START_NO_SKILLS = "No skill is installed yet."

#: The start page's one entry point into the unmanaged repo-document tier
#: (acceptance criterion 2). UNMANAGED_TIER_LABEL is reused underneath it.
START_REPO_DOCUMENT_HEADER = "Repository documentation"

#: Shown in the health rail when Library.index.available is True and not
#: stale (Library.index.message is None in that case, unlike the
#: stale/absent/unreadable cases, which already carry their own message).
START_SEARCH_AVAILABLE = "Search is up to date."

#: {count} is len(Library.broken); shown in the health rail only when
#: non-empty, alongside whatever Library.index already says.
START_BROKEN_RECORDS = "{count} broken record(s) could not be read."
# Search view — filters and results (unit 4)
#
# The search view (views/search.py) offers filters on five dimensions:
# type, status, scope, record_kind, and trust (docs/plans/reader-v1.md
# Sec.4). Every value shown below is plain language, never the raw contract
# token: in particular the word "draft" and the word "scope" never appear on
# screen (both are named explicitly in the forbidden vocabulary list), so
# the on-screen dimension label for scope is "Applies to" rather than
# "Scope", and the status option for the raw value "draft" reads "Not yet
# decided" rather than "Draft". Filter *values* (the raw strings used as
# <option value="..."> and read back from the query string) stay exact,
# since they round-trip through library.search()'s own row fields and are
# never displayed as prose.
# ---------------------------------------------------------------------------

#: On-screen label for each filter dimension, keyed by the query-string
#: parameter name the search view reads (see views/search.py).
SEARCH_FILTER_DIMENSIONS: dict[str, str] = {
    "type": "Type",
    "status": "Status",
    "scope": "Applies to",
    "record_kind": "Kind",
    "trust": "Confidence",
}

#: "Any value" option shown first in every filter <select>.
SEARCH_FILTER_ANY_LABEL = "Any"

SEARCH_SUBMIT_LABEL = "Search"
SEARCH_CLEAR_LABEL = "Clear filters"

#: {count} is the number of results shown after filtering.
SEARCH_RESULT_COUNT = "{count} matching record(s)"

#: The type dimension: the six record types the contract allows in the FTS
#: index (skills are never indexed, so no seventh option is offered here).
SEARCH_TYPE_FILTER: dict[str, str] = {
    "source": "Source",
    "knowledge": "Knowledge",
    "project": "Project",
    "memory": "Memory",
    "synthesis": "Synthesis",
    "discovery": "Discovery",
}

#: The status dimension, covering both the five non-discovery statuses and
#: the four discovery-only statuses in one flat list (a record's own type
#: decides which of these are reachable; the filter itself does not couple
#: status to type). Deliberately reworded so the raw token never surfaces:
#: "draft" -> "Not yet decided", not "Draft".
SEARCH_STATUS_FILTER: dict[str, str] = {
    "draft": "Not yet decided",
    "active": "Currently active",
    "deprecated": "Discouraged",
    "archived": "Archived",
    "superseded": "Replaced",
    "proposed": "Unconfirmed observation",
    "retained": "Reviewed observation",
    "rejected": "Dismissed observation",
    "promoted": "Promoted",
}

#: The record_kind dimension. "ordinary" covers every non-decision record
#: (knowledge, project, and every other type, which never carries a
#: record_kind at all); the filter still offers it as the complement of
#: "decision" so the choice reads as a binary in plain language.
SEARCH_RECORD_KIND_FILTER: dict[str, str] = {
    "ordinary": "Not a decision",
    "decision": "Decision",
}

#: The trust dimension: a short filter-option label for each of the seven
#: strings context_policy.trust_label() can return (see library.py's
#: _SKILL_TRUST_LABEL comment — skills carry an eighth label but are never
#: in search results, so it is not offered here). Shorter than TRUST_LABELS
#: above (no {date} to fill; this is a filter option, not a record's own
#: rail entry).
SEARCH_TRUST_FILTER: dict[str, str] = {
    "raw source; not established knowledge": "Raw material",
    "reviewed observation; not established knowledge": "Reviewed observation",
    "discovery observation; not default context": "Unreviewed observation",
    "draft durable; not verified": "Not yet confirmed",
    "active durable; not verified": "In use, not confirmed",
    "verified durable": "Confirmed",
    "unusable durable record": "No longer in effect",
}

#: Fallback for the "scope" filter's project options when the project's own
#: overview record cannot be resolved (a stale index pointing at a renamed
#: or deleted project). {slug} is the scope's "project:<slug>" suffix.
SEARCH_SCOPE_PROJECT_FALLBACK = "Project {slug}"

#: Heading shown in place of the search form when Library.index.available
#: is False (Sec.6 "Missing index"); the reason and the `kos index` command
#: itself come from library.IndexHealth.message (see INDEX_HEALTH above).
SEARCH_UNAVAILABLE_TITLE = "Search is unavailable"
# Everything view — unit 5 additions
#
# The flat catalog is the deliberate counterweight to the project view's
# grouping by meaning (acceptance criterion 10): every record, source, and
# discovery the workspace holds is reachable here, sorted by what it is
# (type), never by what it means (governing/proposed/historical). These
# strings extend the "Everything view" section above without touching it.
# ---------------------------------------------------------------------------

EVERYTHING_INTRO = (
    "Every record, source, and discovery the workspace holds, in one flat list. "
    "Nothing here is grouped by what it means, only by what it is and how much "
    "to trust it."
)

#: Group headers for the two lists this view renders. Deliberately not named
#: after any meaning-group in PROJECT_GROUP_HEADERS.
EVERYTHING_RECORDS_HEADER = "Records, sources, and discoveries"
EVERYTHING_SKILLS_HEADER = "Skills"

EVERYTHING_NO_SKILLS = "No skill is installed in this workspace."

#: Record.type -> reader-facing noun, for the meta line next to each entry.
#: Falls back to Record.type.capitalize() for any type not listed here.
EVERYTHING_TYPE_LABELS: dict[str, str] = {
    "project": "Project",
    "knowledge": "Knowledge",
    "memory": "Memory",
    "synthesis": "Synthesis",
    "source": "Source material",
    "discovery": "Observation",
}

#: Short pill text for the four colour-carrying states (see reader.css
#: .badge--proposed/--unverified/--retired/--raw); everything else renders
#: with no badge at all (Sec.5: colour only on these four states).
EVERYTHING_ACCENT_BADGE: dict[str, str] = {
    "proposed": "Proposed",
    "unverified": "Unverified",
    "retired": "Retired",
    "raw": "Raw",
}

#: Fallback for a superseded record (decision or ordinary) whose replacement
#: cannot be resolved to a title and date (DECISION_STATUS["superseded"] and
#: LIFECYCLE_STATUS["superseded"] both need both placeholders filled, and a
#: flat catalog entry should never show a literal unfilled "{title}"). Still
#: distinguishes "replaced" from "archived"/"discouraged", per the unit
#: brief's instruction to read Record.status rather than print the raw
#: "unusable durable record" trust label.
EVERYTHING_REPLACED_FALLBACK = "Replaced by a newer record."
# Unit 7 additions — repo-document tier route (`GET /f/{path:path}`,
# `knowledge_os/reader/repodocs.py` and `views/repodoc.py`)
# ---------------------------------------------------------------------------

#: Shown when the requested path is not one of the fixed
#: ``repodocs.REPO_DOCUMENT_PATHS`` entries. Every path-traversal attempt
#: (``../../etc/passwd``, an absolute path, an encoded variant) falls here
#: too, since none of them can equal one of the fixed entries; the message
#: deliberately does not say *why* a path was refused, only that this path
#: is not part of the tier, so it stays identical for a traversal attempt
#: and for an honest typo alike.
REPODOC_NOT_IN_TIER = "{path} is not part of the repository-document tier."
