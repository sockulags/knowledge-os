"""Pure grouping logic for the project view (``views/project.py``).

Takes the ``Record``/``BrokenRecord``/``SkillEntry`` dataclasses already
built by ``library.py`` and reshapes them into the meaning-based buckets the
project page renders. No I/O, no ``knowledge_os.*`` import, nothing here
touches the filesystem: everything is a pure function over data already in
memory, which is what makes it directly unit-testable without a server.

Grouping rules (see ``docs/plans/reader-v1.md`` Sec.4-6 and the unit brief):

- A record belongs to a project because ``Record.scope`` equals
  ``f"project:{project_id}"`` -- never because of where its file happens to
  live. Directory location only drives the *navigation tree* built here
  (``build_project_tree``), never project membership.
- A decision (``Record.record_kind == "decision"``) is bucketed on
  ``Record.accepted_at`` and ``Record.status`` alone, never on directory and
  never on the word "approved": no acceptance provenance (equivalently,
  ``status == "draft"`` in a valid corpus) means "proposed"; an accepted
  decision that has not been superseded is "governing"; an accepted decision
  whose ``status`` is exactly ``"superseded"`` is "historical". A decision
  that is merely ``deprecated``/``archived`` (not superseded) still counts as
  governing here: those statuses collapse together only in
  ``trust_label``'s epistemic classification, not in this meaning grouping,
  and the plan defines "replaced" as supersession specifically.
- ``discovery``-typed and ``source``-typed project records are never
  decisions (``record_kind`` is ``None`` for those types); they form the
  "observations" and "raw material" groups respectively, at every review
  state, so a proposed/rejected/promoted discovery or an unverified source
  stays reachable rather than disappearing.
- Everything else project-scoped (ordinary knowledge/project records, minus
  the project's own overview) is "ordinary" project content, surfaced only
  through the directory tree, never duplicated into a meaning group: the
  five meaning groups exist to answer "what governs, what is proposed, what
  is retired", not to be a second copy of the whole project.
- "General knowledge, memory, and skills" is a side group precisely because
  it does not belong to the project: general-scoped durable records
  (``scope == "general"``) apply everywhere by contract (see
  ``strings.SCOPE_GENERAL``), and skills are operational guidance for every
  project alike, so both are shown, clearly separated, rather than folded
  into the project's own groups.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Sequence

from .library import BrokenRecord, Record

__all__ = [
    "ProjectGroups",
    "ProjectTreeNode",
    "group_project_records",
    "related_general_records",
    "build_project_tree",
]

#: Durable, non-raw, non-observation types eligible for the "general
#: knowledge, memory, and skills" side group. Mirrors
#: ``context_policy.CONTEXT_DURABLE_TYPES`` in spirit (general knowledge that
#: "applies everywhere"); duplicated as a literal for the same reason
#: library.py duplicates ``RELATION_FIELDS`` -- the reader may not import
#: ``knowledge_os.context_policy`` from this module.
_GENERAL_DURABLE_TYPES = ("knowledge", "project", "memory", "synthesis")

#: Decision statuses that mean "retired" once distinguished from "replaced"
#: (see the module docstring: only an exact "superseded" status is
#: "historical" here; a merely deprecated/archived decision is not treated
#: as superseded because nothing points at it through the reversed
#: ``supersedes`` edge).
_SUPERSEDED_STATUS = "superseded"


@dataclass(frozen=True)
class ProjectGroups:
    """The project page's meaning-based buckets, plus its ordinary content.

    ``overview`` is the project's own root record (``id == project_id``),
    excluded from every other bucket. ``ordinary`` holds every other
    project-scoped record that is not a decision, discovery, or source --
    it is not itself one of the five meaning groups; the view renders it
    through ``build_project_tree`` instead.
    """

    overview: Record | None
    governing: tuple[Record, ...]
    proposed: tuple[Record, ...]
    historical: tuple[Record, ...]
    observations: tuple[Record, ...]
    raw_material: tuple[Record, ...]
    ordinary: tuple[Record, ...]


@dataclass(frozen=True)
class ProjectTreeNode:
    """One directory in the project's tree, per the accepted
    ``project-directory-layout`` decision: "any directory may contain its
    own metadata-bearing README.md root record."

    ``name`` is the directory's own segment name (empty string for the
    project root). ``overview`` is that directory's own README record, when
    one exists. ``records`` are the other ordinary records filed directly in
    this directory (not in a subdirectory). ``broken`` are broken files
    (``Library.broken``) filed directly in this directory, rendered in place
    per Sec.6 "Broken record" rather than silently dropped. ``children`` are
    subdirectories, sorted by name.

    Decisions are deliberately absent from this tree even when their file
    lives inside the project directory: they are already surfaced by the
    meaning groups above, and repeating them here would show the same
    record twice under two different organizing principles.
    """

    name: str
    overview: Record | None
    records: tuple[Record, ...]
    broken: tuple[BrokenRecord, ...]
    children: tuple["ProjectTreeNode", ...]

    def is_empty(self) -> bool:
        return (
            self.overview is None
            and not self.records
            and not self.broken
            and not self.children
        )


def _decision_bucket(record: Record) -> str:
    """"governing" | "proposed" | "historical" for one decision record."""

    if record.accepted_at is None:
        return "proposed"
    if record.status == _SUPERSEDED_STATUS:
        return "historical"
    return "governing"


def _sorted_by_title(records: Sequence[Record]) -> tuple[Record, ...]:
    return tuple(sorted(records, key=lambda record: record.title.casefold()))


def group_project_records(records: Sequence[Record], project_id: str) -> ProjectGroups:
    """Bucket every record scoped to ``project_id`` by meaning.

    ``records`` is normally ``Library.records`` in full; only records whose
    ``scope`` matches this project are considered, so passing the whole
    corpus is safe and expected (see the module docstring on why scope,
    never directory, decides membership).
    """

    scope = f"project:{project_id}"
    governing: list[Record] = []
    proposed: list[Record] = []
    historical: list[Record] = []
    observations: list[Record] = []
    raw_material: list[Record] = []
    ordinary: list[Record] = []
    overview: Record | None = None

    for record in records:
        if record.scope != scope:
            continue
        if record.type == "project" and record.id == project_id:
            overview = record
            continue
        if record.record_kind == "decision":
            bucket = _decision_bucket(record)
            {"governing": governing, "proposed": proposed, "historical": historical}[bucket].append(record)
        elif record.type == "discovery":
            observations.append(record)
        elif record.type == "source":
            raw_material.append(record)
        else:
            ordinary.append(record)

    return ProjectGroups(
        overview=overview,
        governing=_sorted_by_title(governing),
        proposed=_sorted_by_title(proposed),
        historical=_sorted_by_title(historical),
        observations=_sorted_by_title(observations),
        raw_material=_sorted_by_title(raw_material),
        ordinary=_sorted_by_title(ordinary),
    )


def related_general_records(records: Sequence[Record]) -> tuple[Record, ...]:
    """General-scoped durable records: general knowledge "applies
    everywhere" by contract (``strings.SCOPE_GENERAL``), so every project's
    side group offers the same set rather than a project-specific filter."""

    return _sorted_by_title(
        record for record in records if record.scope == "general" and record.type in _GENERAL_DURABLE_TYPES
    )


def _strip_project_prefix(path: str, project_id: str) -> tuple[str, ...]:
    """Split a workspace-relative path into directory segments, relative to
    ``projects/<project_id>/``. Falls back to the path's own directory
    segments (project root) when it does not carry that prefix -- a
    defensive fallback only, since a valid corpus keeps every project
    record's path under its own project directory."""

    prefix = f"projects/{project_id}/"
    relative = path[len(prefix):] if path.startswith(prefix) else path
    parts = PurePosixPath(relative).parts
    return parts[:-1]  # drop the filename, keep directory segments


@dataclass
class _MutableNode:
    name: str
    overview: Record | None = None
    records: list[Record] = field(default_factory=list)
    broken: list[BrokenRecord] = field(default_factory=list)
    children: dict[str, "_MutableNode"] = field(default_factory=dict)

    def child(self, name: str) -> "_MutableNode":
        return self.children.setdefault(name, _MutableNode(name=name))

    def freeze(self) -> ProjectTreeNode:
        return ProjectTreeNode(
            name=self.name,
            overview=self.overview,
            records=_sorted_by_title(self.records),
            broken=tuple(sorted(self.broken, key=lambda item: item.path)),
            children=tuple(
                child.freeze()
                for _, child in sorted(self.children.items(), key=lambda item: item[0].casefold())
            ),
        )


def build_project_tree(
    project_id: str,
    ordinary: Sequence[Record],
    broken: Sequence[BrokenRecord] = (),
) -> ProjectTreeNode:
    """Build the project's directory tree from its ordinary (non-decision,
    non-overview) records, per the accepted ``project-directory-layout``
    decision. A file's directory is a root README when its path's filename
    is exactly ``README.md``; everything else is filed as a plain record of
    its containing directory.

    ``broken`` (normally ``Library.broken``) is filtered to this project's
    own directory and rendered in place, one node per containing directory,
    so a corrupted sibling file does not vanish from the tree it lives in
    (Sec.6 "Broken record": "neighbours stay readable").
    """

    root = _MutableNode(name="")
    project_prefix = f"projects/{project_id}/"

    for record in ordinary:
        parts = _strip_project_prefix(record.path, project_id)
        node = root
        for part in parts:
            node = node.child(part)
        if PurePosixPath(record.path).name == "README.md":
            node.overview = record
        else:
            node.records.append(record)

    for item in broken:
        if not item.path.startswith(project_prefix):
            continue
        parts = _strip_project_prefix(item.path, project_id)
        node = root
        for part in parts:
            node = node.child(part)
        node.broken.append(item)

    return root.freeze()
