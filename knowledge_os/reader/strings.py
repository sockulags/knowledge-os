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
# Skill view (unit 8: GET /s/{skill_name})
#
# A skill is not a record: its frontmatter contract has exactly three fields
# (name, description, tags), no lifecycle, no status, no supersession, and it
# is absent from the search index. These strings exist so the skill page
# never borrows record vocabulary ("status", "current", a title it does not
# have) for something that is not a record.
# ---------------------------------------------------------------------------

#: Eyebrow label distinguishing a skill page from a record page.
SKILL_EYEBROW = "Skill"

#: Shown when a skill has no tags at all (two of the four skills in this
#: workspace have none); a tag row must handle this rather than render empty.
SKILL_NO_TAGS = "No tags recorded."

#: Header for the secondary-material block listing a skill's plain-Markdown
#: reference files (e.g. skills/knowledge-os-documentation/references/*.md).
#: These files have no frontmatter, are outside the record contract, and are
#: reached through library.read_repo_document; the block also carries
#: strings.UNMANAGED_TIER_LABEL (acceptance criterion 11).
SKILL_REFERENCES_HEADER = "Supporting references"

#: One reference file could not be read (Sec.6 "Unreadable content"); {path}
#: is its repository-relative path, {detail} the library.LibraryError text.
SKILL_REFERENCE_UNREADABLE = "{path} could not be opened here: {detail}"

#: A requested skill name matches nothing in Library.skills or Library.issues.
SKILL_NOT_FOUND_TITLE = "No such skill"
#: {name} is the requested path segment, exactly as typed in the URL.
SKILL_NOT_FOUND_BODY = 'No skill named "{name}" exists in this workspace.'

#: A skill directory exists but its SKILL.md failed to parse (it appears in
#: Library.issues, never in Library.skills); say so rather than a 404 or a
#: silent empty page (Sec.6 "Broken record", applied to the skill contract).
SKILL_BROKEN_TITLE = "This skill could not be read"
#: {message} is the exact issue message from library.Library.issues.
SKILL_BROKEN_BODY = "skills/{name}/SKILL.md failed validation: {message}"

#: Tech-details labels (dl in the metadata rail); the raw contract vocabulary
#: (path, trust label string) belongs one click away, never in the reading
#: path itself.
SKILL_LABEL_NAME = "Name"
SKILL_LABEL_TAGS = "Tags"
SKILL_LABEL_PATH = "Path"
SKILL_LABEL_TRUST = "Trust"
