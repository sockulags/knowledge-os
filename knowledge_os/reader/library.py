"""The one module in this package permitted to import ``knowledge_os.*``.

Views consume only the frozen dataclasses and functions defined here. This
module never parses YAML itself, never reimplements validation, trust
classification, or lifecycle rules, and never writes to the workspace: it
calls ``validate_workspace``, ``trust_label``, ``validate_index``, and
``content_sha256`` and reshapes their output into plain data.

``load_library`` runs the full corpus scan and must be called fresh per
request (see ``app.py``); nothing here caches across calls, so a record
edited while the server is running is visible on the next request
(acceptance criterion 8).
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from knowledge_os.context_policy import trust_label
from knowledge_os.index import validate_index
from knowledge_os.model import Document, MetadataError, content_sha256, parse_document
from knowledge_os.skills import Skill, load_skills
from knowledge_os.workspace import Issue, Workspace, WorkspaceError, validate_workspace

from . import strings

__all__ = [
    "ProvenanceEntry",
    "Relation",
    "Record",
    "BrokenRecord",
    "SkillEntry",
    "IndexHealth",
    "Library",
    "LibraryError",
    "load_library",
    "search",
    "read_repo_document",
    "path_index",
    # Record has no content_sha256 field (not part of the frozen contract);
    # a view that needs one for its technical-details disclosure (acceptance
    # criterion 4) computes it on demand via this re-export, since views may
    # not import knowledge_os.model directly.
    "content_sha256",
]

#: The record contract's three directed relationship fields. Not imported
#: from knowledge_os.model (only Document/MetadataError/parse_document/
#: content_sha256 are permitted from that module); this is the same tuple
#: model.RELATION_FIELDS holds, duplicated here as a literal because the
#: contract fixes these three names, not because it might change.
_RELATION_FIELDS = ("related", "sources", "supersedes")

#: context_policy.trust_label() never returns this; the reader assigns it to
#: every skill directly (see the "Skills" note in the unit-0 contract).
_SKILL_TRUST_LABEL = "operational guidance"

_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


class LibraryError(ValueError):
    """A user-actionable error raised by this adapter (never a bare crash)."""


@dataclass(frozen=True)
class ProvenanceEntry:
    kind: str
    reference: str
    captured: str | None
    sha256: str | None


@dataclass(frozen=True)
class Relation:
    field: str  # "related" | "sources" | "supersedes"
    record_id: str
    title: str | None  # None when the id does not resolve
    resolved: bool


@dataclass(frozen=True)
class Record:
    id: str
    title: str
    type: str
    record_kind: str | None  # "ordinary" | "decision" | None for non knowledge/project
    status: str
    scope: str
    created: str
    updated: str
    verified: str | None
    tags: tuple[str, ...]
    provenance: tuple[ProvenanceEntry, ...]
    outbound: tuple[Relation, ...]
    inbound: tuple[Relation, ...]  # `field` is the field on the POINTING record
    body: str
    path: str  # workspace-relative POSIX
    abs_path: Path
    trust_label: str
    accepted_at: str | None  # `captured` of the decision-acceptance entry
    is_decision: bool


@dataclass(frozen=True)
class BrokenRecord:
    path: str
    message: str


@dataclass(frozen=True)
class SkillEntry:
    name: str
    description: str
    tags: tuple[str, ...]
    body: str
    path: str


@dataclass(frozen=True)
class IndexHealth:
    available: bool
    stale: bool
    message: str | None  # already user-facing


@dataclass(frozen=True)
class Library:
    records: tuple[Record, ...]
    records_by_id: Mapping[str, Record]
    broken: tuple[BrokenRecord, ...]
    skills: tuple[SkillEntry, ...]
    issues: tuple[BrokenRecord, ...]
    index: IndexHealth
    workspace_root: Path
    workspace_name: str | None


def _relative_or_absolute(workspace: Workspace, path: Path) -> str:
    """workspace.relative() raises for a path outside the root (a possible
    symlink issue); fall back to the absolute string rather than crash."""

    try:
        return workspace.relative(path)
    except WorkspaceError:
        return str(path)


def _normalize_scalar(value: object) -> str:
    """Dates (and provenance timestamps) parse as ``str`` or a date/datetime
    object depending on YAML quoting; validate_metadata validates but never
    writes the parsed value back, so normalize once, here."""

    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def _normalize_optional(value: object | None) -> str | None:
    return None if value is None else _normalize_scalar(value)


def _normalize_record_kind(metadata: dict[str, object]) -> str | None:
    """The only implementation of this lives private in index.py, and three
    call sites disagree on the empty value (``""``, ``"ordinary"``, ``None``).
    This is the one normalizer the reader uses: "ordinary"/"decision" for
    knowledge and project records, None (never "") otherwise."""

    if metadata["type"] not in {"knowledge", "project"}:
        return None
    return metadata.get("record_kind", "ordinary")


def _build_provenance(item: dict[str, object]) -> ProvenanceEntry:
    return ProvenanceEntry(
        kind=item["kind"],
        reference=item["reference"],
        captured=_normalize_optional(item.get("captured")),
        sha256=item.get("sha256"),
    )


def _accepted_at(metadata: dict[str, object], record_kind: str | None) -> str | None:
    if record_kind != "decision":
        return None
    for item in metadata["provenance"]:
        if item.get("kind") == "decision-acceptance":
            return _normalize_optional(item.get("captured"))
    return None


def _build_outbound(metadata: dict[str, object], documents_by_id: dict[str, Document]) -> tuple[Relation, ...]:
    relations: list[Relation] = []
    for field in _RELATION_FIELDS:
        for target_id in metadata.get(field, ()):
            target = documents_by_id.get(target_id)
            relations.append(
                Relation(
                    field=field,
                    record_id=target_id,
                    title=target.metadata["title"] if target is not None else None,
                    resolved=target is not None,
                )
            )
    return tuple(relations)


def _build_inbound_map(documents: list[Document]) -> dict[str, list[Relation]]:
    """Invert related/sources/supersedes in memory. The contract deliberately
    excludes a backlink subsystem, so this runs fresh on every load.

    Every entry built here comes from a successfully parsed document, so the
    "pointing" record it describes always resolves (resolved=True); a broken
    file's own outbound links cannot be recovered since its frontmatter never
    parsed, and a link that merely targets an unknown id is not an inbound
    relation for anyone.
    """

    inbound: dict[str, list[Relation]] = {}
    for document in documents:
        metadata = document.metadata
        source_id = metadata["id"]
        source_title = metadata["title"]
        for field in _RELATION_FIELDS:
            for target_id in metadata.get(field, ()):
                inbound.setdefault(target_id, []).append(
                    Relation(field=field, record_id=source_id, title=source_title, resolved=True)
                )
    return inbound


def _build_record(
    workspace: Workspace,
    document: Document,
    documents_by_id: dict[str, Document],
    inbound_map: dict[str, list[Relation]],
) -> Record:
    metadata = document.metadata
    record_id = metadata["id"]
    record_kind = _normalize_record_kind(metadata)
    inbound = tuple(
        sorted(inbound_map.get(record_id, ()), key=lambda relation: (relation.field, relation.record_id))
    )
    return Record(
        id=record_id,
        title=metadata["title"],
        type=metadata["type"],
        record_kind=record_kind,
        status=metadata["status"],
        scope=metadata["scope"],
        created=_normalize_scalar(metadata["created"]),
        updated=_normalize_scalar(metadata["updated"]),
        verified=_normalize_optional(metadata.get("verified")),
        tags=tuple(metadata.get("tags", ())),
        provenance=tuple(_build_provenance(item) for item in metadata["provenance"]),
        outbound=_build_outbound(metadata, documents_by_id),
        inbound=inbound,
        body=document.body,
        path=_relative_or_absolute(workspace, document.path),
        abs_path=document.path,
        trust_label=trust_label(document),
        accepted_at=_accepted_at(metadata, record_kind),
        is_decision=record_kind == "decision",
    )


def _broken_records(
    workspace: Workspace,
    documents: list[Document],
    issues: list[Issue],
    skill_issue_paths: set[Path],
) -> tuple[BrokenRecord, ...]:
    """Every Issue whose path never produced a parsed Document is a broken
    record (a file that fails parse_document lands ONLY in the Issue list;
    it never reaches validate_workspace's document list). Skill issues are
    excluded here because they are normalized separately from the Skill
    loader's own issue list (re-parsing a SKILL.md as a managed record would
    produce a nonsensical message); they still appear in Library.issues.

    A path can fail before parse_document is ever attempted (an unsafe or
    symlinked path caught by the workspace scan itself), so re-parsing is a
    best-effort refinement, not the only source of the message: if it does
    not reproduce the same MetadataError, the original issue message (always
    correct, since it is exactly what `kos lint` prints) is used instead.
    """

    parsed_paths = {document.path for document in documents}
    broken: dict[Path, BrokenRecord] = {}
    for issue in issues:
        if issue.path in parsed_paths or issue.path in skill_issue_paths or issue.path in broken:
            continue
        message = issue.message
        try:
            parse_document(issue.path)
        except MetadataError as exc:
            message = str(exc)
        except OSError:
            pass
        broken[issue.path] = BrokenRecord(path=_relative_or_absolute(workspace, issue.path), message=message)
    return tuple(broken.values())


def _index_health(workspace: Workspace, documents: list[Document]) -> IndexHealth:
    """validate_index does a full corpus body comparison; call it once per
    load (here), never per page element."""

    try:
        validate_index(workspace, documents)
    except ValueError as exc:
        message = str(exc)
        if message.startswith("search index is absent"):
            return IndexHealth(available=False, stale=False, message=strings.INDEX_HEALTH["absent"])
        if message.startswith("search index is stale"):
            return IndexHealth(available=True, stale=True, message=strings.INDEX_HEALTH["stale"])
        return IndexHealth(
            available=False,
            stale=False,
            message=strings.INDEX_HEALTH["unreadable"].format(detail=message),
        )
    return IndexHealth(available=True, stale=False, message=None)


def _workspace_name(workspace: Workspace) -> str | None:
    config = workspace.config.get("workspace")
    name = config.get("name") if isinstance(config, dict) else None
    return name if isinstance(name, str) else None


def load_library(workspace: Workspace) -> Library:
    """Load the whole corpus fresh. Never cache across requests: acceptance
    criterion 8 requires detecting a record edited while the server runs."""

    documents, issues = validate_workspace(workspace)
    documents_by_id = {document.metadata["id"]: document for document in documents}
    inbound_map = _build_inbound_map(documents)
    records = tuple(
        _build_record(workspace, document, documents_by_id, inbound_map) for document in documents
    )

    skill_list: list[Skill]
    skill_list, skill_issues = load_skills(workspace.root)
    skills = tuple(
        SkillEntry(
            name=skill.name,
            description=skill.description,
            tags=skill.tags,
            body=skill.body,
            path=_relative_or_absolute(workspace, skill.path),
        )
        for skill in skill_list
    )
    skill_issue_paths = {path for path, _ in skill_issues}

    return Library(
        records=records,
        records_by_id={record.id: record for record in records},
        broken=_broken_records(workspace, documents, issues, skill_issue_paths),
        skills=skills,
        issues=tuple(
            BrokenRecord(path=_relative_or_absolute(workspace, issue.path), message=issue.message)
            for issue in issues
        ),
        index=_index_health(workspace, documents),
        workspace_root=workspace.root,
        workspace_name=_workspace_name(workspace),
    )


def path_index(library: Library) -> Mapping[str, str]:
    """Workspace-relative POSIX path -> record id, built fresh from
    ``Library.records``.

    The one shared lookup ``markdown.render``'s ``resolve_link`` needs to
    rewrite a relative record-to-record link into a ``/r/<id>`` permalink
    (see that function's docstring): a link's target, once resolved against
    its source document's own directory, is compared against every record's
    ``path`` here. Never cached beyond one request, matching
    ``load_library``'s own contract of a fresh scan per request.
    """

    return {record.path: record.id for record in library.records}


def search(workspace: Workspace, query: str, limit: int = 50) -> list[dict[str, str]]:
    """Search the read-only SQLite catalog.

    Deliberately does not call index.search_index: that function opens the
    database read-write (a bare sqlite3.connect), which risks touching the
    db file, and acceptance criterion 1 requires the workspace to be
    byte-identical after serving. This issues the same query read-only via a
    ``file:...?mode=ro`` URI instead.

    A blank query, a missing or unopenable database, and an unparseable FTS
    expression all return a clean empty list rather than raise: a view can
    always show "no results" safely, and Library.index (from load_library)
    is the dedicated signal for *why* search might be unavailable.
    """

    trimmed = query.strip()
    if not trimmed:
        return []
    database = workspace.root / "indexes" / "catalog.sqlite3"
    try:
        workspace.assert_safe_path(database)
    except WorkspaceError:
        return []
    if not database.is_file():
        return []
    escaped = trimmed.replace('"', '""')
    try:
        connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return []
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, title, type, record_kind, status, scope, path,
                   snippet(documents_fts, 8, '[', ']', '...', 18) AS snippet
            FROM documents_fts
            WHERE documents_fts MATCH ?
            ORDER BY bm25(documents_fts), id
            LIMIT ?
            """,
            (f'"{escaped}"', max(limit, 0)),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()
    results = []
    for row in rows:
        result = dict(row)
        result["snippet"] = " ".join(result["snippet"].split())
        results.append(result)
    return results


def _first_heading(text: str) -> str | None:
    for line in text.splitlines():
        match = _HEADING_PATTERN.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def read_repo_document(workspace: Workspace, rel_path: str) -> tuple[str, str]:
    """Read one file from the unmanaged tier (outside the record contract).

    Every path is gated through Workspace.assert_safe_path, which rejects
    symlinks, reparse points, and escapes from the workspace root. Non-UTF-8
    content and a missing file raise LibraryError rather than crash, so a
    view can show why the entry cannot be read instead of a 500.
    """

    candidate = workspace.root / rel_path
    try:
        workspace.assert_safe_path(candidate)
    except WorkspaceError as exc:
        raise LibraryError(strings.REPO_DOCUMENT_UNSAFE.format(path=rel_path, detail=str(exc))) from exc
    resolved = candidate.resolve(strict=False)
    if not resolved.is_file():
        raise LibraryError(strings.REPO_DOCUMENT_NOT_FOUND.format(path=rel_path))
    try:
        text = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise LibraryError(strings.REPO_DOCUMENT_NOT_UTF8.format(path=rel_path)) from exc
    except OSError as exc:
        raise LibraryError(strings.REPO_DOCUMENT_UNSAFE.format(path=rel_path, detail=str(exc))) from exc
    title = _first_heading(text) or Path(rel_path).name
    return title, text
