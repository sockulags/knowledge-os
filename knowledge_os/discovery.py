"""Discovery review and promotion workflows.

Discoveries are canonical observations, not canonical knowledge.  This module
keeps their lifecycle explicit and stages every mutation before replacing live
Markdown or generated indexes.
"""

from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Iterable

import yaml

from .index import rebuild_indexes, search_index_terms, validate_index
from .model import (
    DISCOVERY_DECISION_TO_STATUS,
    DISCOVERY_STATUSES,
    DISCOVERY_TRANSITIONS,
    ID_PATTERN,
    RELATION_FIELDS,
    STANDARD_STATUSES,
    Document,
    MetadataError,
    parse_document,
    parse_document_text,
)
from .workspace import MANAGED_DIRS, Workspace, atomic_write, validate_workspace


DISCOVERY_DIRECTORY = "discoveries"
RELATED_TYPES = ("knowledge", "project", "memory", "synthesis")
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


class DiscoveryError(ValueError):
    """A user-actionable discovery workflow error."""


class _ExclusiveCreateCleanupError(DiscoveryError):
    """An exclusive create failed and its partial path could not be safely removed."""


@contextmanager
def _workspace_mutation_lock(workspace: Workspace) -> Iterable[None]:
    identity = str(workspace.root).casefold() if os.name == "nt" else str(workspace.root)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    lock_path = Path(tempfile.gettempdir()) / f"knowledge-os-discovery-{digest}.lock"
    handle = lock_path.open("a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            raise DiscoveryError(f"could not acquire discovery mutation lock for {workspace.root}: {exc}") from exc
        locked = True
        yield
    finally:
        if locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


@dataclass
class RelatedRecord:
    document: Document
    matched_terms: list[str]
    reasons: list[str]
    fts_rank: int | None


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _json_block(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, indent=2, sort_keys=True)


def _frontmatter(metadata: dict[str, Any], body: str) -> bytes:
    rendered = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{rendered}\n---\n\n{body}".encode("utf-8")


def _today_for(metadata: dict[str, Any]) -> str:
    current = metadata["updated"]
    if isinstance(current, datetime):
        current_date = current.date()
    elif isinstance(current, date):
        current_date = current
    else:
        current_date = date.fromisoformat(str(current))
    today = datetime.now(timezone.utc).date()
    return max(today, current_date).isoformat()


def _details(issues: list[Any]) -> str:
    return "\n".join(f"{issue.path}: {issue.message}" for issue in issues)


def _validated_documents(workspace: Workspace, operation: str) -> list[Document]:
    documents, issues = validate_workspace(workspace)
    if issues:
        raise DiscoveryError(f"cannot {operation} with an invalid corpus:\n{_details(issues)}")
    return documents


def _find_discovery(documents: Iterable[Document], record_id: str) -> Document:
    document = next((item for item in documents if item.metadata["id"] == record_id), None)
    if document is None:
        raise DiscoveryError(f"discovery not found: {record_id}")
    if document.metadata["type"] != "discovery":
        raise DiscoveryError(f"record {record_id!r} is not a discovery")
    return document


def _validate_reviewer(reviewer: str | None) -> str | None:
    if reviewer is None:
        return None
    if not reviewer.strip():
        raise DiscoveryError("--reviewer must not be empty")
    return reviewer.strip()


def _validate_reason(reason: str | None, *, required: bool = False) -> str | None:
    if reason is None:
        if required:
            raise DiscoveryError("--reason is required")
        return None
    if not reason.strip():
        raise DiscoveryError("--reason must not be empty")
    return reason.strip()


def _validate_scope(scope: str) -> str:
    if not isinstance(scope, str) or not scope.strip():
        raise DiscoveryError("--scope must be general or project:<lowercase-kebab>")
    scope = scope.strip()
    if scope != "general" and not re.fullmatch(r"project:[a-z0-9]+(?:-[a-z0-9]+)*", scope):
        raise DiscoveryError("--scope must be general or project:<lowercase-kebab>")
    return scope


def _load_input(path: Path) -> Document:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise DiscoveryError(f"input path is not a file: {path}")
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise DiscoveryError("discovery add accepts only .md and .markdown structured input")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise DiscoveryError("discovery input must be UTF-8 text") from exc
    try:
        return parse_document_text(path, text, check_filename=False)
    except MetadataError as exc:
        raise DiscoveryError(f"invalid discovery input {path}: {exc}") from exc


def _ensure_candidate(document: Document) -> None:
    metadata = document.metadata
    if metadata["type"] != "discovery":
        raise DiscoveryError("discovery add requires type: discovery")
    if metadata["status"] != "proposed":
        raise DiscoveryError("discovery add requires status: proposed")
    if metadata.get("reviews"):
        raise DiscoveryError("discovery add requires no review events")


def _stage_workspace(workspace: Workspace) -> tuple[tempfile.TemporaryDirectory[str], Workspace]:
    temporary = tempfile.TemporaryDirectory(prefix="kos-discovery-", dir=workspace.root.parent)
    stage_root = Path(temporary.name)
    marker = workspace.root / "knowledge-os.toml"
    (stage_root / marker.name).write_bytes(marker.read_bytes())
    for directory in MANAGED_DIRS:
        source = workspace.root / directory
        destination = stage_root / directory
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            destination.mkdir(parents=True)
    return temporary, Workspace(stage_root)


def _stage_and_verify(stage: Workspace) -> tuple[list[Document], int]:
    count = rebuild_indexes(stage)
    documents, issues = validate_workspace(stage)
    if issues:
        raise DiscoveryError(f"resulting corpus is invalid:\n{_details(issues)}")
    validate_index(stage, documents)
    return documents, count


def _snapshot_live_paths(workspace: Workspace, relative_paths: Iterable[str]) -> dict[str, bytes | None]:
    snapshot: dict[str, bytes | None] = {}
    for relative in dict.fromkeys(relative_paths):
        path = workspace.root / relative
        if path.is_file():
            snapshot[relative] = path.read_bytes()
        elif path.exists():
            raise DiscoveryError(f"mutation path {workspace.relative(path)} is not a file")
        else:
            snapshot[relative] = None
    return snapshot


def _verify_live_snapshot(workspace: Workspace, snapshot: dict[str, bytes | None]) -> None:
    for relative, expected in snapshot.items():
        path = workspace.root / relative
        if expected is None:
            if path.exists():
                raise DiscoveryError(f"concurrent change detected: expected {relative} to remain absent")
        elif not path.is_file() or path.read_bytes() != expected:
            raise DiscoveryError(f"concurrent change detected in {relative}")


def _exclusive_create(
    path: Path,
    content: bytes,
    relative: str,
    written: dict[str, bytes],
    created: set[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("xb")
    opened_stat = os.fstat(handle.fileno())
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        try:
            if not handle.closed:
                handle.close()
            try:
                current_stat = path.lstat()
            except FileNotFoundError:
                current_stat = None
            if current_stat is not None:
                if not stat.S_ISREG(current_stat.st_mode) or not os.path.samestat(opened_stat, current_stat):
                    raise DiscoveryError(
                        f"exclusive create failed for {relative}; refusing to remove a concurrently replaced path"
                    )
                path.unlink()
        except Exception as cleanup_error:
            raise _ExclusiveCreateCleanupError(
                f"exclusive create failed for {relative} and its partial path could not be safely removed: "
                f"{cleanup_error}"
            ) from exc
        raise
    written[relative] = content
    created.add(relative)


def _rollback_written(
    workspace: Workspace,
    snapshot: dict[str, bytes | None],
    written: dict[str, bytes],
    created: set[str],
) -> None:
    for relative in reversed(tuple(written)):
        path = workspace.root / relative
        if relative in created:
            if path.exists():
                if not path.is_file() or path.read_bytes() != written[relative]:
                    raise DiscoveryError(
                        f"cannot safely roll back concurrently changed path {relative}"
                    )
                path.unlink()
            continue
        content = written[relative]
        if not path.is_file() or path.read_bytes() != content:
            raise DiscoveryError(f"cannot safely roll back concurrently changed path {relative}")
        original = snapshot[relative]
        if original is None:
            path.unlink()
        else:
            atomic_write(path, original)


def _commit_staged(
    workspace: Workspace,
    stage: Workspace,
    snapshot: dict[str, bytes | None],
    *,
    exclusive_paths: Iterable[str] = (),
) -> None:
    relative_paths = tuple(snapshot)
    exclusive_paths = frozenset(exclusive_paths)
    live_paths = {relative: workspace.root / relative for relative in relative_paths}
    stage_paths = {relative: stage.root / relative for relative in relative_paths}
    if any(not path.is_file() for path in stage_paths.values()):
        missing = [relative for relative, path in stage_paths.items() if not path.is_file()]
        raise DiscoveryError(f"staged mutation is missing file(s): {', '.join(missing)}")
    written: dict[str, bytes] = {}
    created: set[str] = set()
    try:
        _verify_live_snapshot(workspace, snapshot)
        for relative in relative_paths:
            content = stage_paths[relative].read_bytes()
            if relative in exclusive_paths:
                _exclusive_create(live_paths[relative], content, relative, written, created)
            else:
                try:
                    atomic_write(live_paths[relative], content)
                except Exception:
                    if live_paths[relative].is_file() and live_paths[relative].read_bytes() == content:
                        written[relative] = content
                    raise
                written[relative] = content
        documents, issues = validate_workspace(workspace)
        if issues:
            raise DiscoveryError(f"live corpus failed post-commit validation:\n{_details(issues)}")
        validate_index(workspace, documents)
    except Exception as exc:
        try:
            _rollback_written(workspace, snapshot, written, created)
        except Exception as rollback_error:
            raise DiscoveryError(
                f"mutation failed and rollback failed: {exc}; {rollback_error}"
            ) from exc
        if isinstance(exc, _ExclusiveCreateCleanupError):
            raise
        raise DiscoveryError(f"mutation failed; canonical corpus and indexes were restored: {exc}") from exc


def _transition(document: Document, target_status: str) -> None:
    current_status = document.metadata["status"]
    if target_status not in DISCOVERY_STATUSES:
        raise DiscoveryError(f"invalid discovery target status {target_status!r}")
    if target_status not in DISCOVERY_TRANSITIONS[current_status]:
        raise DiscoveryError(f"invalid discovery transition {current_status} -> {target_status}")


def _review_event(
    decision: str,
    review_date: str,
    reviewer: str | None,
    reason: str | None,
    target: str | None = None,
) -> dict[str, str]:
    event: dict[str, str] = {"decision": decision, "date": review_date}
    if reviewer is not None:
        event["reviewer"] = reviewer
    if reason is not None:
        event["reason"] = reason
    if target is not None:
        event["target"] = target
    return event


def _updated_discovery_metadata(
    document: Document,
    *,
    decision: str,
    reviewer: str | None,
    reason: str | None,
    target: str | None = None,
    related_target: str | None = None,
) -> dict[str, Any]:
    status = DISCOVERY_DECISION_TO_STATUS[decision]
    _transition(document, status)
    metadata = deepcopy(document.metadata)
    mutation_date = _today_for(metadata)
    reviews = list(metadata.get("reviews", []))
    reviews.append(_review_event(decision, mutation_date, reviewer, reason, target))
    metadata["reviews"] = reviews
    metadata["status"] = status
    metadata["updated"] = mutation_date
    if related_target is not None:
        related = list(metadata.get("related", []))
        if related_target not in related:
            related.append(related_target)
        metadata["related"] = related
    return metadata


def add_discovery(workspace: Workspace, input_path: Path) -> tuple[str, bool, int]:
    """Add a proposed discovery after staging and validating the resulting corpus."""

    with _workspace_mutation_lock(workspace):
        return _add_discovery_locked(workspace, input_path)


def _add_discovery_locked(workspace: Workspace, input_path: Path) -> tuple[str, bool, int]:
    documents = _validated_documents(workspace, "add a discovery")
    candidate = _load_input(input_path)
    _ensure_candidate(candidate)
    record_id = candidate.metadata["id"]
    canonical = _frontmatter(candidate.metadata, candidate.body)
    by_id = {document.metadata["id"]: document for document in documents}
    destination = workspace.root / DISCOVERY_DIRECTORY / f"{record_id}.md"
    existing = by_id.get(record_id)
    if existing is not None and existing.path != destination:
        raise DiscoveryError(
            f"duplicate discovery id {record_id!r}; already defined at {workspace.relative(existing.path)}"
        )
    if destination.exists() and not destination.is_file():
        raise DiscoveryError(f"destination {workspace.relative(destination)} is not a file; refusing overwrite")
    created = existing is None
    if existing is not None and destination.read_bytes() != canonical:
        raise DiscoveryError(
            f"existing destination {workspace.relative(destination)} has divergent content; refusing overwrite"
        )

    relative_paths = ["indexes/catalog.md", "indexes/catalog.sqlite3"]
    relative_record = f"{DISCOVERY_DIRECTORY}/{record_id}.md"
    if created:
        relative_paths.insert(0, relative_record)
    snapshot = _snapshot_live_paths(workspace, relative_paths)
    temporary, stage = _stage_workspace(workspace)
    try:
        stage_destination = stage.root / DISCOVERY_DIRECTORY / f"{record_id}.md"
        if created:
            atomic_write(stage_destination, canonical)
        else:
            parse_document(stage_destination)
        _, count = _stage_and_verify(stage)
        _commit_staged(
            workspace,
            stage,
            snapshot,
            exclusive_paths=((relative_record,) if created else ()),
        )
        return record_id, created, count
    finally:
        temporary.cleanup()


def _change_status(
    workspace: Workspace,
    record_id: str,
    *,
    decision: str,
    reviewer: str | None,
    reason: str | None,
) -> tuple[str, int]:
    with _workspace_mutation_lock(workspace):
        return _change_status_locked(
            workspace,
            record_id,
            decision=decision,
            reviewer=reviewer,
            reason=reason,
        )


def _change_status_locked(
    workspace: Workspace,
    record_id: str,
    *,
    decision: str,
    reviewer: str | None,
    reason: str | None,
) -> tuple[str, int]:
    documents = _validated_documents(workspace, f"{decision} discovery")
    discovery = _find_discovery(documents, record_id)
    if decision == "retain" and discovery.metadata["scope"] == "general":
        raise DiscoveryError("retained discoveries require project scope")
    reviewer = _validate_reviewer(reviewer)
    reason = _validate_reason(reason)
    metadata = _updated_discovery_metadata(
        discovery,
        decision=decision,
        reviewer=reviewer,
        reason=reason,
    )
    content = _frontmatter(metadata, discovery.body)

    relative_record = f"{DISCOVERY_DIRECTORY}/{record_id}.md"
    relative_paths = (relative_record, "indexes/catalog.md", "indexes/catalog.sqlite3")
    snapshot = _snapshot_live_paths(workspace, relative_paths)
    temporary, stage = _stage_workspace(workspace)
    try:
        atomic_write(stage.root / relative_record, content)
        _, count = _stage_and_verify(stage)
        _commit_staged(workspace, stage, snapshot)
        return metadata["status"], count
    finally:
        temporary.cleanup()


def retain_discovery(
    workspace: Workspace,
    record_id: str,
    *,
    reviewer: str | None = None,
    reason: str | None = None,
) -> tuple[str, int]:
    return _change_status(workspace, record_id, decision="retain", reviewer=reviewer, reason=reason)


def reject_discovery(
    workspace: Workspace,
    record_id: str,
    *,
    reason: str,
    reviewer: str | None = None,
) -> tuple[str, int]:
    reason = _validate_reason(reason, required=True)
    return _change_status(workspace, record_id, decision="reject", reviewer=reviewer, reason=reason)


def _discovery_terms(document: Document) -> list[str]:
    values = [document.metadata["title"], document.body, *document.metadata.get("tags", [])]
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in TOKEN_PATTERN.findall(value.casefold()):
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms or [document.metadata["id"]]


def _related_scopes(discovery: Document) -> tuple[str, ...]:
    if discovery.metadata["scope"] == "general":
        return ("general",)
    return ("general", discovery.metadata["scope"])


def _related_allowed(document: Document, scopes: tuple[str, ...]) -> bool:
    metadata = document.metadata
    return metadata["type"] in RELATED_TYPES and metadata["scope"] in scopes


def _add_related(
    related: dict[str, RelatedRecord],
    document: Document,
    *,
    matched_terms: Iterable[str] = (),
    reason: str,
    fts_rank: int | None = None,
) -> None:
    record_id = document.metadata["id"]
    if record_id not in related:
        related[record_id] = RelatedRecord(document, [], [], fts_rank)
    item = related[record_id]
    for term in matched_terms:
        if term not in item.matched_terms:
            item.matched_terms.append(term)
    if reason not in item.reasons:
        item.reasons.append(reason)
    if item.fts_rank is None and fts_rank is not None:
        item.fts_rank = fts_rank


def find_related_records(
    workspace: Workspace,
    documents: list[Document],
    discovery: Document,
) -> list[RelatedRecord]:
    """Find deterministic lexical and explicit-link candidates for human review."""

    by_id = {document.metadata["id"]: document for document in documents}
    scopes = _related_scopes(discovery)
    related: dict[str, RelatedRecord] = {}
    rows = search_index_terms(
        workspace,
        _discovery_terms(discovery),
        scopes,
        STANDARD_STATUSES,
        types=RELATED_TYPES,
    )
    for row in rows:
        document = by_id.get(row["id"])
        if document is None or not _related_allowed(document, scopes):
            continue
        _add_related(
            related,
            document,
            matched_terms=row["matched_terms"],
            reason=f"FTS matched terms: {', '.join(row['matched_terms'])}",
            fts_rank=row["fts_rank"],
        )

    for field in RELATION_FIELDS:
        for target_id in discovery.metadata.get(field, []):
            target = by_id.get(target_id)
            if target is not None and _related_allowed(target, scopes):
                _add_related(related, target, reason=f"relationship from discovery via {field}")
        for source in documents:
            if discovery.metadata["id"] in source.metadata.get(field, []):
                if _related_allowed(source, scopes):
                    _add_related(related, source, reason=f"relationship from {source.metadata['id']} via {field}")

    return sorted(
        related.values(),
        key=lambda item: (
            -len(item.matched_terms),
            item.fts_rank if item.fts_rank is not None else 10**9,
            item.document.metadata["id"],
            workspace.relative(item.document.path),
        ),
    )


def _related_markdown(workspace: Workspace, related: list[RelatedRecord]) -> list[str]:
    if not related:
        return ["No potential overlaps or conflicts were found by the deterministic lexical and relationship checks.", ""]
    lines = [
        "These are potential overlaps or conflicts requiring human review. They are not semantic contradiction detection.",
        "",
    ]
    for item in related:
        metadata = item.document.metadata
        matched = ", ".join(item.matched_terms) if item.matched_terms else "none"
        lines.extend(
            [
                f"- **{metadata['id']}** — {metadata['title']}",
                f"  - Matched terms: {matched}",
                f"  - Reason: {'; '.join(item.reasons)}",
                f"  - Path: {workspace.relative(item.document.path)}",
                f"  - Status: {metadata['status']} | Scope: {metadata['scope']}",
            ]
        )
    lines.append("")
    return lines


def render_review_packet(workspace: Workspace, discovery: Document, related: list[RelatedRecord]) -> str:
    """Render a deterministic, non-canonical review packet without timestamps."""

    metadata = discovery.metadata
    relationships = {field: metadata.get(field, []) for field in RELATION_FIELDS}
    lines = [
        "# Discovery review packet",
        "",
        "**Generated, non-canonical output.** This packet proposes review; it does not change the corpus or decide whether the observation is true.",
        "",
        "## Discovery",
        "",
        f"- **ID:** {metadata['id']}",
        f"- **Title:** {metadata['title']}",
        f"- **Status:** {metadata['status']}",
        f"- **Scope:** {metadata['scope']}",
        "",
        "### Statement / observation",
        "",
        discovery.body.rstrip(),
        "",
        "### Origin",
        "",
        "```json",
        _json_block(metadata.get("origin")),
        "```",
        "",
        "### Evidence",
        "",
        "```json",
        _json_block(metadata["evidence"]),
        "```",
        "",
        "### Provenance",
        "",
        "```json",
        _json_block(metadata["provenance"]),
        "```",
        "",
        "### Relationships",
        "",
        "```json",
        _json_block(relationships),
        "```",
        "",
        "### Review history",
        "",
        "```json",
        _json_block(metadata.get("reviews", [])),
        "```",
        "",
        "## Potential overlaps and conflicts",
        "",
    ]
    lines.extend(_related_markdown(workspace, related))
    lines.extend(
        [
            "## Possible outcomes",
            "",
            "- **Retain:** move a proposed project-scoped observation to `retained`; retained observations are eligible only for that project's context and remain explicitly unestablished.",
            "- **Reject:** move a proposed or retained observation to terminal `rejected` with a reason.",
            "- **Promote new:** create a new draft knowledge/project record from this body, link provenance directly to this discovery, and move the discovery to terminal `promoted`. This never merges, overwrites, or supersedes an existing record.",
            "",
            "## Promotion flags",
            "",
            "- `--acknowledge-related` is required when candidates are listed; it acknowledges inspection only and does not merge or overwrite them.",
            "- `--allow-scope-broadening` is required when a project-scoped discovery is promoted to `general`.",
            "- A project-scoped discovery can promote only to its same project; cross-project promotion is not supported.",
            "- Promotion creates a `draft`; it is not verification or fact checking.",
            "",
        ]
    )
    return "\n".join(lines)


def review_packet(workspace: Workspace, record_id: str) -> str:
    documents = _validated_documents(workspace, "review a discovery")
    validate_index(workspace, documents)
    discovery = _find_discovery(documents, record_id)
    return render_review_packet(workspace, discovery, find_related_records(workspace, documents, discovery))


def inspect_discovery(workspace: Workspace, record_id: str) -> str:
    documents = _validated_documents(workspace, "inspect a discovery")
    discovery = _find_discovery(documents, record_id)
    metadata = discovery.metadata
    result = {
        "id": metadata["id"],
        "title": metadata["title"],
        "type": metadata["type"],
        "status": metadata["status"],
        "scope": metadata["scope"],
        "created": metadata["created"],
        "updated": metadata["updated"],
        "path": workspace.relative(discovery.path),
        "origin": metadata.get("origin"),
        "evidence": metadata["evidence"],
        "provenance": metadata["provenance"],
        "reviews": metadata.get("reviews", []),
        "relationships": {field: metadata.get(field, []) for field in RELATION_FIELDS},
        "body": discovery.body,
        "excerpt": " ".join(discovery.body.strip().split())[:600],
    }
    if "confidence" in metadata:
        result["confidence"] = metadata["confidence"]
    if "tags" in metadata:
        result["tags"] = metadata["tags"]
    return json.dumps(_json_value(result), ensure_ascii=False, indent=2)


def promote_discovery(
    workspace: Workspace,
    record_id: str,
    *,
    target_id: str,
    title: str,
    scope: str,
    reviewer: str | None = None,
    reason: str | None = None,
    acknowledge_related: bool = False,
    allow_scope_broadening: bool = False,
) -> tuple[str, int, list[str]]:
    with _workspace_mutation_lock(workspace):
        return _promote_discovery_locked(
            workspace,
            record_id,
            target_id=target_id,
            title=title,
            scope=scope,
            reviewer=reviewer,
            reason=reason,
            acknowledge_related=acknowledge_related,
            allow_scope_broadening=allow_scope_broadening,
        )


def _promote_discovery_locked(
    workspace: Workspace,
    record_id: str,
    *,
    target_id: str,
    title: str,
    scope: str,
    reviewer: str | None = None,
    reason: str | None = None,
    acknowledge_related: bool = False,
    allow_scope_broadening: bool = False,
) -> tuple[str, int, list[str]]:
    documents = _validated_documents(workspace, "promote a discovery")
    validate_index(workspace, documents)
    discovery = _find_discovery(documents, record_id)
    reviewer = _validate_reviewer(reviewer)
    reason = _validate_reason(reason)
    if not isinstance(target_id, str) or not ID_PATTERN.fullmatch(target_id):
        raise DiscoveryError("--target-id must be a lowercase kebab-case ID")
    if target_id == record_id:
        raise DiscoveryError("--target-id must differ from the discovery ID")
    if not isinstance(title, str) or not title.strip():
        raise DiscoveryError("--title must not be empty")
    title = title.strip()
    scope = _validate_scope(scope)
    discovery_scope = discovery.metadata["scope"]
    if discovery_scope.startswith("project:"):
        if scope == "general" and not allow_scope_broadening:
            raise DiscoveryError(
                "promotion from project scope to general requires --allow-scope-broadening"
            )
        if scope.startswith("project:") and scope != discovery_scope:
            raise DiscoveryError("cross-project promotion is not supported")

    related = find_related_records(workspace, documents, discovery)
    related_ids = [item.document.metadata["id"] for item in related]
    if related_ids and not acknowledge_related:
        raise DiscoveryError(
            "related records require --acknowledge-related: " + ", ".join(related_ids)
        )
    by_id = {document.metadata["id"]: document for document in documents}
    if target_id in by_id:
        raise DiscoveryError(f"target ID {target_id!r} already exists; promotion never overwrites records")

    target_type = "knowledge" if scope == "general" else "project"
    destination_directory = "knowledge" if scope == "general" else "projects"
    target_path = workspace.root / destination_directory / f"{target_id}.md"
    if target_path.exists():
        raise DiscoveryError(
            f"target path {workspace.relative(target_path)} already exists; promotion never overwrites records"
        )
    mutation_date = _today_for(discovery.metadata)
    target_metadata: dict[str, Any] = {
        "id": target_id,
        "title": title,
        "type": target_type,
        "status": "draft",
        "scope": scope,
        "created": mutation_date,
        "updated": mutation_date,
        "provenance": [{"kind": "discovery", "reference": record_id}],
        "sources": [record_id],
    }
    discovery_metadata = _updated_discovery_metadata(
        discovery,
        decision="promote",
        reviewer=reviewer,
        reason=reason,
        target=target_id,
        related_target=target_id,
    )
    target_content = _frontmatter(target_metadata, discovery.body)
    discovery_content = _frontmatter(discovery_metadata, discovery.body)

    discovery_relative = f"{DISCOVERY_DIRECTORY}/{record_id}.md"
    target_relative = f"{destination_directory}/{target_id}.md"
    relative_paths = (
        target_relative,
        discovery_relative,
        "indexes/catalog.md",
        "indexes/catalog.sqlite3",
    )
    snapshot = _snapshot_live_paths(workspace, relative_paths)
    temporary, stage = _stage_workspace(workspace)
    try:
        atomic_write(stage.root / discovery_relative, discovery_content)
        atomic_write(stage.root / target_relative, target_content)
        _, count = _stage_and_verify(stage)
        _commit_staged(
            workspace,
            stage,
            snapshot,
            exclusive_paths=(target_relative,),
        )
        return target_id, count, related_ids
    finally:
        temporary.cleanup()
