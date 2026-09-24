"""The one module in this package permitted to import ``knowledge_os.*``.

Views consume only the frozen dataclasses and functions defined here. This
module never parses YAML itself and never reimplements validation, trust
classification, or lifecycle rules: it calls ``validate_workspace``,
``trust_label``, ``validate_index``, and ``content_sha256`` and reshapes
their output into plain data.

Reads never write to the workspace. The only writes are ``create_record``,
``edit_record``, ``accept_record``, ``withdraw_record``, and
``supersede_record``, plus the structure changes ``create_project``,
``create_folder``, ``rename_page``, ``move_page``, and ``move_folder``, at the
end of this module, which hand the request to the core's own ``capture``,
``update``, ``decision accept``, ``decision withdraw``, ``supersede``, and
``structure`` mutations (shared lock, staged validation,
SHA-256 guard, index refresh) and translate the core's errors into one
``WriteError`` with a stable ``kind``. After a successful write they commit
the touched files to the workspace's own Git repository through
``knowledge_os.gitsync``; the Git sync functions at the very end hand the
sync endpoints to the same module.

``load_library`` runs the full corpus scan and must be called fresh per
request (see ``app.py``); nothing here caches across calls, so a record
edited while the server is running is visible on the next request
(acceptance criterion 8).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Mapping

from knowledge_os.capture import (
    CAPTURE_DIRECTORIES,
    CaptureError,
    CaptureIndexError,
    DuplicateRecordError,
    capture_record_text,
)
from knowledge_os import gitsync
from knowledge_os.agent_identity import AGENT_PROVENANCE_KIND, AgentIdentity, parse_agent_reference
from knowledge_os.context_policy import trust_label
from knowledge_os.gitsync import CommitOutcome, ConflictFile, GitSyncError, ResolveOutcome, SyncOutcome, SyncStatus
from knowledge_os.index import validate_index
from knowledge_os.model import (
    SHA256_PATTERN,
    Document,
    MetadataError,
    content_sha256,
    parse_document,
    parse_document_text,
    render_document,
)
from knowledge_os.mutations import (
    MutationError,
    MutationIndexError,
    RecordNotFoundError,
    StaleRevisionError,
    SupersedeIndexError,
    accept_decision,
    supersede_decision,
    update_record_text,
    withdraw_decision,
)
from knowledge_os.skills import Skill, load_skills
from knowledge_os.structure import (
    ChangedFile,
    StructureIndexError,
    StructureResult,
    clean_folder,
    create_folder as core_create_folder,
    create_project as core_create_project,
    move_folder as core_move_folder,
    move_record as core_move_record,
    rename_record as core_rename_record,
)
from knowledge_os.workspace import CorpusValidationError, Issue, Workspace, WorkspaceError, validate_workspace

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
    "WriteError",
    "WriteResult",
    "create_record",
    "edit_record",
    "EditableSource",
    "editable_source",
    "DecisionActions",
    "decision_actions",
    "SupersedeWriteResult",
    "accept_record",
    "withdraw_record",
    "supersede_record",
    "CommitOutcome",
    "ConflictFile",
    "GitSyncError",
    "ResolveOutcome",
    "SyncOutcome",
    "SyncStatus",
    "sync_status",
    "run_sync",
    "sync_conflicts",
    "resolve_sync_conflict",
    "abort_sync",
    # Structure editing (issue #52): projects, folders, moves, and renames.
    "ChangedFile",
    "StructureWriteResult",
    "create_project",
    "create_folder",
    "move_page",
    "rename_page",
    "move_folder",
    # Agent writes (the MCP server, issue #59): the identity the write API
    # accepts and the parser the reader uses to name the agent.
    "AgentIdentity",
    "parse_agent_reference",
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


# ---------------------------------------------------------------------------
# Writes: create and edit through the core's capture and update mutations
# ---------------------------------------------------------------------------


class WriteError(LibraryError):
    """A refused write, with a ``kind`` the API maps to one HTTP status.

    ``kind`` is one of ``bad_request``, ``not_found``, ``conflict`` (stale
    SHA-256), ``duplicate`` (ID or destination already exists), or
    ``validation`` (the core rejected the candidate or the resulting corpus).
    ``issues`` holds ``(path, message)`` lint findings when the core reported
    them; ``current_sha256`` is set on a conflict.
    """

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        issues: tuple[tuple[str, str], ...] = (),
        current_sha256: str | None = None,
    ):
        super().__init__(detail)
        self.kind = kind
        self.detail = detail
        self.issues = issues
        self.current_sha256 = current_sha256


@dataclass(frozen=True)
class WriteResult:
    id: str
    status: str
    path: str  # workspace-relative POSIX
    content_sha256: str
    index_refreshed: bool
    index_count: int | None
    index_error: str | None  # set when the canonical write succeeded but reindexing failed
    commit: CommitOutcome | None = None  # the local Git commit made for this write, or why none was made


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _write_error(exc: Exception) -> WriteError:
    """Translate one core exception into a WriteError. The core's own message
    is kept verbatim: it is the same text ``kos`` prints for the same rule."""

    if isinstance(exc, WriteError):
        return exc
    if isinstance(exc, DuplicateRecordError):
        return WriteError("duplicate", str(exc))
    if isinstance(exc, RecordNotFoundError):
        return WriteError("not_found", str(exc))
    if isinstance(exc, StaleRevisionError):
        return WriteError("conflict", str(exc), current_sha256=exc.actual)
    if isinstance(exc, CorpusValidationError):
        return WriteError("validation", str(exc), issues=exc.issues)
    return WriteError("validation", str(exc))


def create_record(
    workspace: Workspace,
    *,
    metadata: dict[str, Any],
    body: str,
    project_path: str | None = None,
    agent: AgentIdentity | None = None,
) -> WriteResult:
    """Create one knowledge, project, or memory record with ``kos capture``'s
    rules: create-only, draft or active (decisions draft only), and for a
    project record an optional ``project_path`` relative to
    ``projects/<project-id>/``. ``created`` and ``updated`` default to today
    (UTC); every other field, including provenance, comes from the caller.

    ``agent`` marks an agent write: its ``agent-authored`` entry goes first in
    the provenance (so the Decide inbox names the agent as the proposer) and
    the commit message starts with the agent's name."""

    candidate = dict(metadata)
    candidate.setdefault("created", _today())
    candidate.setdefault("updated", candidate["created"])
    if agent is not None:
        given = candidate.get("provenance")
        candidate["provenance"] = [agent.provenance_entry(), *(given if isinstance(given, list) else [])]
    text = render_document(candidate, body).decode("utf-8")
    try:
        result = capture_record_text(
            workspace,
            text,
            project_path=Path(project_path) if project_path is not None else None,
        )
    except CaptureIndexError as exc:
        written = exc.result
        outcome = WriteResult(written.id, written.status, written.path, written.sha256, False, None, str(exc))
    except (CaptureError, MetadataError, WorkspaceError) as exc:
        raise _write_error(exc) from exc
    else:
        outcome = WriteResult(result.id, result.status, result.path, result.sha256, True, result.index_count, None)
    return _with_commit(workspace, outcome, "Create", agent)


def edit_record(
    workspace: Workspace,
    record_id: str,
    *,
    expected_sha256: str,
    changes: Mapping[str, Any],
    body: str | None = None,
    confirm_non_material: bool = False,
    change_reference: str | None = None,
    agent: AgentIdentity | None = None,
) -> WriteResult:
    """Edit one record's body and metadata with ``kos update``'s rules.

    ``changes`` replaces top-level metadata fields (``None`` removes one) on
    top of the exact revision the caller read, identified by
    ``expected_sha256``; ``body`` of ``None`` keeps the current body. When
    ``changes`` does not set ``updated``, it becomes today (UTC) or stays at
    its current value if that is later. The core then refuses changes to
    identity, lifecycle, supersession, or system provenance, re-checks the
    SHA-256 under the workspace lock, and validates the staged corpus.

    ``agent`` marks an agent edit: its ``agent-authored`` entry is appended
    to the provenance unless an entry with the same reference is already
    there, and the commit message starts with the agent's name.
    """

    if not SHA256_PATTERN.fullmatch(expected_sha256):
        raise WriteError("bad_request", "expected_sha256 must be 64 lowercase hex characters")
    if "id" in changes and changes["id"] != record_id:
        raise WriteError("validation", "update must not change id; create a new record instead")

    documents, _issues = validate_workspace(workspace)
    current = next((document for document in documents if document.metadata["id"] == record_id), None)
    if current is None:
        raise WriteError("not_found", f"record not found: {record_id}")
    if current.metadata["type"] not in CAPTURE_DIRECTORIES:
        # Sources and syntheses keep their ingest provenance and discoveries
        # their review workflow; the interface edits only what it can create.
        raise WriteError(
            "validation",
            f"record {record_id!r} has type {current.metadata['type']!r}; the interface edits only "
            f"{', '.join(sorted(CAPTURE_DIRECTORIES))} records",
        )

    # Merge onto the exact bytes the caller read, never onto a newer revision.
    raw = current.path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256:
        raise WriteError(
            "conflict",
            f"conflict for {current.path.name}: expected sha256 {expected_sha256}, found {actual}; "
            "the record changed after it was read, so nothing was written",
            current_sha256=actual,
        )
    try:
        base = parse_document_text(current.path, raw.decode("utf-8"))
    except (MetadataError, UnicodeDecodeError) as exc:
        raise WriteError("validation", f"current record cannot be parsed: {exc}") from exc

    metadata = dict(base.metadata)
    for field, value in changes.items():
        if value is None:
            metadata.pop(field, None)
        else:
            metadata[field] = value
    if "updated" not in changes:
        previous = metadata.get("updated")
        previous_date = previous if isinstance(previous, date) else date.fromisoformat(str(previous))
        metadata["updated"] = max(previous_date, datetime.now(UTC).date()).isoformat()
    if agent is not None:
        provenance = list(metadata.get("provenance") or [])
        if not any(
            isinstance(item, dict) and item.get("kind") == AGENT_PROVENANCE_KIND and item.get("reference") == agent.reference
            for item in provenance
        ):
            metadata["provenance"] = [*provenance, agent.provenance_entry()]
    text = render_document(metadata, base.body if body is None else body).decode("utf-8")

    try:
        result = update_record_text(
            workspace,
            text,
            expected_sha256=expected_sha256,
            confirm_non_material=confirm_non_material,
            change_reference=change_reference,
        )
    except MutationIndexError as exc:
        written = exc.result
        outcome = WriteResult(written.id, written.status, written.path, written.sha256, False, None, str(exc))
    except (MutationError, MetadataError, WorkspaceError) as exc:
        raise _write_error(exc) from exc
    else:
        outcome = WriteResult(result.id, result.status, result.path, result.sha256, True, result.index_count, None)
    return _with_commit(workspace, outcome, "Edit", agent)


# ---------------------------------------------------------------------------
# Local Git commits after a write
# ---------------------------------------------------------------------------


def _title_at(workspace: Workspace, rel_path: str, fallback: str) -> str:
    try:
        # README.md root records are not named after their ID.
        document = parse_document(workspace.root / rel_path, check_filename=False)
        return str(document.metadata.get("title") or fallback)
    except (MetadataError, OSError, UnicodeDecodeError):
        return fallback


def _with_commit(workspace: Workspace, result: WriteResult, verb: str, agent: AgentIdentity | None = None) -> WriteResult:
    """Commit the one file a write touched, e.g. ``Edit <title>``, or
    ``Claude Code: Edit <title>`` for an agent write."""

    message = f"{verb} {_title_at(workspace, result.path, result.id)}"
    if agent is not None:
        message = f"{agent.display_name}: {message}"
    return replace(result, commit=gitsync.auto_commit(workspace, [result.path], message))


# ---------------------------------------------------------------------------
# Editing reads: the exact revision an editor starts from
# ---------------------------------------------------------------------------

#: The metadata fields the interface's editor offers. ``kos update`` allows
#: more (it refuses only identity, lifecycle, supersession, and system
#: provenance changes); these are the ones a person edits by hand.
EDITABLE_FIELDS = ("title", "tags", "related", "sources")


@dataclass(frozen=True)
class EditableSource:
    raw_body: str
    metadata: dict[str, Any]  # EDITABLE_FIELDS only; absent lists are []
    content_sha256: str
    editable: bool  # the interface edits only the types it can create
    body_change_needs_confirmation: bool  # accepted decision: non-material edits only


def editable_source(record: Record) -> EditableSource:
    """Read the record's body and editable fields from one read of its bytes,
    so the hash an editor later sends as ``expected_sha256`` describes exactly
    the text it was given, even if the file changed after ``load_library``."""

    raw = record.abs_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    try:
        document = parse_document_text(record.abs_path, raw.decode("utf-8"))
    except (MetadataError, UnicodeDecodeError) as exc:
        raise LibraryError(f"record {record.id!r} cannot be parsed for editing: {exc}") from exc
    metadata = document.metadata
    fields: dict[str, Any] = {"title": metadata["title"]}
    for field in EDITABLE_FIELDS[1:]:
        fields[field] = list(metadata.get(field, ()))
    return EditableSource(
        raw_body=document.body,
        metadata=fields,
        content_sha256=digest,
        editable=metadata["type"] in CAPTURE_DIRECTORIES,
        body_change_needs_confirmation=(
            metadata.get("record_kind") == "decision" and metadata["status"] in {"active", "superseded"}
        ),
    )


# ---------------------------------------------------------------------------
# Decision lifecycle: accept, withdraw, supersede
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionActions:
    """Which lifecycle actions the interface offers on one decision.

    A hint for which buttons to show, following the core's preconditions;
    the core checks them again under the workspace lock and refuses anything
    that no longer holds.
    """

    accept: bool
    withdraw: bool
    replaces: Record | None  # the active decision a draft replacement would supersede
    propose_replacement: bool


def decision_actions(library: Library, record: Record) -> DecisionActions | None:
    if not record.is_decision:
        return None
    supersedes = [relation.record_id for relation in record.outbound if relation.field == "supersedes"]
    draft = record.status == "draft"
    replaces: Record | None = None
    if draft and len(supersedes) == 1:
        target = library.records_by_id.get(supersedes[0])
        if target is not None and target.is_decision and target.status == "active" and target.scope == record.scope:
            replaces = target
    return DecisionActions(
        accept=draft and not supersedes,
        withdraw=draft,
        replaces=replaces,
        propose_replacement=record.status == "active",
    )


@dataclass(frozen=True)
class SupersedeWriteResult:
    replacement: WriteResult  # the draft that became active
    replaced: WriteResult  # the active decision that became superseded


def interface_reference(action: str) -> str:
    """A provenance reference for an action taken in the interface, e.g.
    ``interface:2026-09-22T21:02:52Z:accept``."""

    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"interface:{stamp}:{action}"


def _require_sha(value: str, name: str) -> None:
    if not SHA256_PATTERN.fullmatch(value):
        raise WriteError("bad_request", f"{name} must be 64 lowercase hex characters")


def _mutation_result(result: Any, *, refreshed: bool, error: str | None) -> WriteResult:
    return WriteResult(
        result.id, result.status, result.path, result.sha256, refreshed, result.index_count if refreshed else None, error
    )


def _decision_write(call: Any) -> WriteResult:
    try:
        result = call()
    except MutationIndexError as exc:
        return _mutation_result(exc.result, refreshed=False, error=str(exc))
    except (MutationError, MetadataError, WorkspaceError) as exc:
        raise _write_error(exc) from exc
    return _mutation_result(result, refreshed=True, error=None)


def accept_record(workspace: Workspace, record_id: str, *, expected_sha256: str) -> WriteResult:
    """``kos decision accept`` with an ``interface:<timestamp>:accept`` reference."""

    _require_sha(expected_sha256, "expected_sha256")
    result = _decision_write(
        lambda: accept_decision(
            workspace,
            record_id,
            expected_sha256=expected_sha256,
            acceptance_reference=interface_reference("accept"),
        )
    )
    return _with_commit(workspace, result, "Accept decision")


def withdraw_record(workspace: Workspace, record_id: str, *, expected_sha256: str, reason: str) -> WriteResult:
    """``kos decision withdraw``; ``reason`` becomes the withdrawal provenance reference."""

    _require_sha(expected_sha256, "expected_sha256")
    if not reason.strip():
        raise WriteError("bad_request", "reason must be a non-empty string")
    result = _decision_write(
        lambda: withdraw_decision(workspace, record_id, expected_sha256=expected_sha256, reason=reason)
    )
    return _with_commit(workspace, result, "Withdraw decision")


def supersede_record(
    workspace: Workspace,
    new_id: str,
    *,
    expected_sha256: str,
    old_id: str,
    old_expected_sha256: str,
) -> SupersedeWriteResult:
    """``kos supersede OLD NEW``: activate draft ``new_id`` as the replacement
    for active ``old_id`` with an ``interface:<timestamp>:supersede``
    acceptance reference, checking both exact revisions."""

    _require_sha(expected_sha256, "expected_sha256")
    _require_sha(old_expected_sha256, "old_expected_sha256")
    refreshed, error = True, None
    try:
        result = supersede_decision(
            workspace,
            old_id,
            new_id,
            expected_old_sha256=old_expected_sha256,
            expected_new_sha256=expected_sha256,
            acceptance_reference=interface_reference("supersede"),
        )
    except SupersedeIndexError as exc:
        result, refreshed, error = exc.result, False, str(exc)
    except (MutationError, MetadataError, WorkspaceError) as exc:
        raise _write_error(exc) from exc
    count = result.index_count if refreshed else None
    # Supersession rewrites both files in place, so their paths are unchanged.
    documents, _issues = validate_workspace(workspace)
    paths = {document.metadata["id"]: _relative_or_absolute(workspace, document.path) for document in documents}
    replacement = WriteResult(
        new_id, result.new_status, paths.get(new_id, ""), result.new_sha256, refreshed, count, error
    )
    replaced = WriteResult(old_id, result.old_status, paths.get(old_id, ""), result.old_sha256, refreshed, count, error)
    message = (
        f"Supersede decision {_title_at(workspace, replaced.path, old_id)} "
        f"with {_title_at(workspace, replacement.path, new_id)}"
    )
    commit = gitsync.auto_commit(workspace, [replacement.path, replaced.path], message)
    return SupersedeWriteResult(replacement=replace(replacement, commit=commit), replaced=replaced)


# ---------------------------------------------------------------------------
# Structure: create projects and folders, move and rename pages and folders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StructureWriteResult:
    """A structure change as written: the main record (or the folder, when a
    moved folder has no page of its own), every file created, moved, or
    rewritten in ``changed``, and the one commit that recorded all of them."""

    id: str | None
    title: str | None
    status: str | None
    path: str
    content_sha256: str | None
    project: str
    folder: str
    scope_changed: bool
    changed: tuple[ChangedFile, ...]
    index_refreshed: bool
    index_count: int | None
    index_error: str | None
    commit: CommitOutcome | None = None


def _interface_provenance(action: str) -> list[dict[str, str]]:
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return [{"kind": "interface-authored", "reference": f"interface:{stamp}:{action}", "captured": stamp}]


def _folder_label(workspace: Workspace, project_id: str, folder: str) -> str:
    """How a commit message names a place: the folder page's title, else the
    folder name, and the project overview's title for the top level."""

    if not folder:
        return _title_at(workspace, f"projects/{project_id}/README.md", project_id)
    return _title_at(workspace, f"projects/{project_id}/{folder}/README.md", folder.rsplit("/", 1)[-1])


def _structure_write(workspace: Workspace, call: Any, message: Any) -> StructureWriteResult:
    """Run one core structure change, then commit every path it touched as
    one commit with ``message(result)``."""

    refreshed, error = True, None
    try:
        result: StructureResult = call()
    except StructureIndexError as exc:
        result, refreshed, error = exc.result, False, str(exc)
    except (MutationError, CaptureError, MetadataError, WorkspaceError) as exc:
        raise _write_error(exc) from exc
    commit = gitsync.auto_commit(workspace, result.touched, message(result))
    return StructureWriteResult(
        id=result.id,
        title=result.title,
        status=result.status,
        path=result.path,
        content_sha256=result.sha256,
        project=result.project,
        folder=result.folder,
        scope_changed=result.scope_changed,
        changed=result.changed,
        index_refreshed=refreshed,
        index_count=result.index_count if refreshed else None,
        index_error=error,
        commit=commit,
    )


def create_project(
    workspace: Workspace, *, project_id: str, title: str, description: str | None = None
) -> StructureWriteResult:
    """``kos project create``: the new project's overview ``projects/<id>/README.md``."""

    return _structure_write(
        workspace,
        lambda: core_create_project(
            workspace, project_id, title=title, provenance=_interface_provenance("create"), body=description
        ),
        lambda result: f"Create project {result.title}",
    )


def create_folder(
    workspace: Workspace,
    *,
    project_id: str,
    path: str,
    title: str,
    record_id: str | None = None,
    description: str | None = None,
) -> StructureWriteResult:
    """``kos folder create``: a folder in a project, written as its ``README.md`` page."""

    return _structure_write(
        workspace,
        lambda: core_create_folder(
            workspace,
            project_id,
            path,
            title=title,
            provenance=_interface_provenance("create"),
            record_id=record_id,
            body=description,
        ),
        lambda result: f"Create folder {result.title}",
    )


def _record_or_error(workspace: Workspace, record_id: str) -> Document:
    documents, _issues = validate_workspace(workspace)
    current = next((document for document in documents if document.metadata["id"] == record_id), None)
    if current is None:
        raise WriteError("not_found", f"record not found: {record_id}")
    return current


def rename_page(workspace: Workspace, record_id: str, *, expected_sha256: str, title: str) -> StructureWriteResult:
    """``kos rename``: a new title for one page; its ID and file stay the same."""

    _require_sha(expected_sha256, "expected_sha256")
    current = _record_or_error(workspace, record_id)
    if current.metadata["type"] not in CAPTURE_DIRECTORIES:
        raise WriteError(
            "validation",
            f"record {record_id!r} has type {current.metadata['type']!r}; the interface edits only "
            f"{', '.join(sorted(CAPTURE_DIRECTORIES))} records",
        )
    old_title = current.metadata["title"]
    return _structure_write(
        workspace,
        lambda: core_rename_record(workspace, record_id, expected_sha256=expected_sha256, title=title),
        lambda result: f"Rename {old_title} to {result.title}",
    )


def move_page(
    workspace: Workspace,
    record_id: str,
    *,
    expected_sha256: str,
    folder: str,
    project: str | None = None,
    allow_scope_change: bool = False,
    expected: Mapping[str, str] | None = None,
) -> StructureWriteResult:
    """``kos move``: one project page to another folder, or with
    ``allow_scope_change`` to another project. Links to it are rewritten."""

    _require_sha(expected_sha256, "expected_sha256")
    title = str(_record_or_error(workspace, record_id).metadata["title"])

    def message(result: StructureResult) -> str:
        place = _folder_label(workspace, result.project, result.folder)
        if result.scope_changed and result.folder:
            place = f"{place} in {_folder_label(workspace, result.project, '')}"
        return f"Move {title} to {place}"

    return _structure_write(
        workspace,
        lambda: core_move_record(
            workspace,
            record_id,
            expected_sha256=expected_sha256,
            folder=folder,
            project=project,
            allow_scope_change=allow_scope_change,
            expected=expected,
        ),
        message,
    )


def move_folder(
    workspace: Workspace,
    project_id: str,
    folder: str,
    *,
    to_project: str | None = None,
    to_parent: str | None = None,
    name: str | None = None,
    title: str | None = None,
    allow_scope_change: bool = False,
    expected: Mapping[str, str] | None = None,
) -> StructureWriteResult:
    """``kos folder move``/``rename``: a folder and everything in it. Links
    into it are rewritten; another project needs ``allow_scope_change``."""

    try:
        cleaned = clean_folder(folder)
    except MutationError as exc:
        raise _write_error(exc) from exc
    old_label = _folder_label(workspace, project_id, cleaned) if cleaned else project_id
    old_parent = cleaned.rsplit("/", 1)[0] if "/" in cleaned else ""

    def message(result: StructureResult) -> str:
        new_label = _folder_label(workspace, result.project, result.folder)
        new_parent = result.folder.rsplit("/", 1)[0] if "/" in result.folder else ""
        if result.project == project_id and new_parent == old_parent:
            return f"Rename folder {old_label} to {new_label}"
        place = _folder_label(workspace, result.project, new_parent)
        if result.scope_changed and new_parent:
            place = f"{place} in {_folder_label(workspace, result.project, '')}"
        return f"Move folder {old_label} to {place}"

    return _structure_write(
        workspace,
        lambda: core_move_folder(
            workspace,
            project_id,
            folder,
            to_project=to_project,
            to_parent=to_parent,
            name=name,
            title=title,
            allow_scope_change=allow_scope_change,
            expected=expected,
        ),
        message,
    )


# ---------------------------------------------------------------------------
# Git sync: status, pull-then-push, and conflict resolution
# ---------------------------------------------------------------------------


def sync_status(workspace: Workspace) -> SyncStatus:
    """Branch, upstream, ahead/behind, uncommitted changes, and last sync; never contacts the remote."""

    return gitsync.status(workspace)


def run_sync(workspace: Workspace) -> SyncOutcome:
    """Pull then push, or finish a sync whose conflicts are all resolved.

    Raises ``GitSyncError``; a pull that stops on conflicts raises kind
    ``conflict`` with the conflicted paths.
    """

    outcome = gitsync.sync(workspace)
    if outcome.state == "conflict":
        raise GitSyncError("conflict", outcome.detail or "the pull stopped on conflicts", conflicts=outcome.conflicts)
    return outcome


def sync_conflicts(workspace: Workspace) -> tuple[ConflictFile, ...]:
    return gitsync.list_conflicts(workspace)


def resolve_sync_conflict(workspace: Workspace, path: str, choice: str, content: str | None) -> ResolveOutcome:
    try:
        return gitsync.resolve_conflict(workspace, path, choice, content)
    except WorkspaceError as exc:
        raise GitSyncError("failed", str(exc)) from exc


def abort_sync(workspace: Workspace) -> None:
    gitsync.abort_merge(workspace)
