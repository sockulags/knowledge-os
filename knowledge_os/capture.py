"""Create approved durable records without replacing canonical content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .model import Document, MetadataError, parse_document_text, render_document
from .workspace import (
    Workspace,
    WorkspaceError,
    atomic_write,
    exclusive_write,
    default_project_record_path,
    project_directory,
    refresh_derived_indexes,
    stage_workspace,
    staged_documents,
    validate_workspace,
    workspace_mutation_lock,
)


CAPTURE_DIRECTORIES = {
    "knowledge": "knowledge",
    "project": "projects",
    "memory": "memory",
}
CAPTURE_STATUSES = {"draft", "active"}


class CaptureError(ValueError):
    """A user-actionable approved-record capture error."""


@dataclass(frozen=True)
class CaptureResult:
    id: str
    type: str
    scope: str
    path: str
    status: str
    index_count: int


def _load_candidate(input_path: Path) -> Document:
    path = input_path.expanduser().resolve()
    if not path.is_file():
        raise CaptureError(f"capture input path is not a file: {path}")
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise CaptureError("capture accepts only .md and .markdown structured input")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CaptureError("capture input must be UTF-8 text") from exc
    try:
        return parse_document_text(path, text, check_filename=False)
    except MetadataError as exc:
        raise CaptureError(f"invalid capture candidate {path}: {exc}") from exc


def _ensure_candidate(candidate: Document) -> None:
    metadata = candidate.metadata
    record_type = metadata["type"]
    if record_type not in CAPTURE_DIRECTORIES:
        raise CaptureError("capture accepts only type: knowledge, project, or memory")
    if metadata["status"] not in CAPTURE_STATUSES:
        raise CaptureError("capture requires status: draft or active")
    if metadata.get("record_kind") == "decision" and metadata["status"] != "draft":
        raise CaptureError("capture creates decision records as draft; use 'kos decision accept' to activate")
    if "verified" in metadata:
        raise CaptureError("capture candidates must not include verified")
    if not candidate.body.strip():
        raise CaptureError("capture candidate body must be non-empty")


def _details(issues: list[Any]) -> str:
    return "\n".join(f"{issue.path}: {issue.message}" for issue in issues)


def _project_relative_path(metadata: dict[str, Any], requested: Path | None) -> Path:
    default = default_project_record_path(metadata["id"], metadata["scope"])
    if requested is None:
        return default
    if requested.is_absolute() or not requested.parts or any(part in {"", ".", ".."} for part in requested.parts):
        raise CaptureError("--project-path must be a safe relative path inside the project directory")
    if requested.suffix.lower() not in {".md", ".markdown"}:
        raise CaptureError("--project-path must end in .md or .markdown")
    if requested.name != "README.md" and requested.stem != metadata["id"]:
        raise CaptureError("--project-path filename must be README.md or have a stem equal to the record ID")
    return project_directory(metadata["scope"]) / requested


def capture_record(
    workspace: Workspace,
    input_path: Path,
    *,
    project_path: Path | None = None,
) -> CaptureResult:
    """Create one approved durable record under the shared mutation contract."""

    with workspace_mutation_lock(workspace):
        documents, issues = validate_workspace(workspace)
        if issues:
            raise CaptureError(f"cannot capture into an invalid corpus:\n{_details(issues)}")

        candidate = _load_candidate(input_path)
        _ensure_candidate(candidate)
        metadata = candidate.metadata
        record_id = metadata["id"]
        record_type = metadata["type"]
        if project_path is not None and record_type != "project":
            raise CaptureError("--project-path is only valid for type: project")
        relative_path = (
            _project_relative_path(metadata, project_path)
            if record_type == "project"
            else Path(CAPTURE_DIRECTORIES[record_type]) / f"{record_id}.md"
        )
        destination = workspace.root / relative_path
        workspace.assert_safe_path(destination)

        by_id = {document.metadata["id"]: document for document in documents}
        existing = by_id.get(record_id)
        if existing is not None:
            raise CaptureError(
                f"duplicate capture id {record_id!r}; already defined at {workspace.relative(existing.path)}"
            )
        if destination.exists() or destination.is_symlink():
            if destination.is_file():
                detail = "already exists"
            else:
                detail = "is not a file"
            raise CaptureError(f"destination {workspace.relative(destination)} {detail}; refusing overwrite")

        canonical = render_document(metadata, candidate.body)
        relative_record = relative_path.as_posix()
        with stage_workspace(workspace) as stage:
            atomic_write(stage.root / relative_record, canonical)
            staged_documents(stage, "capture an approved record")

        try:
            exclusive_write(destination, canonical)
        except FileExistsError as exc:
            raise CaptureError(
                f"destination {workspace.relative(destination)} was created by another writer; refusing overwrite"
            ) from exc
        except OSError as exc:
            raise CaptureError(
                f"canonical capture write failed for {workspace.relative(destination)}; "
                f"run 'kos lint' before retrying: {exc}"
            ) from exc

        try:
            index_count = refresh_derived_indexes(workspace)
        except WorkspaceError as exc:
            raise CaptureError(str(exc)) from exc
        return CaptureResult(
            id=record_id,
            type=record_type,
            scope=metadata["scope"],
            path=workspace.relative(destination),
            status=metadata["status"],
            index_count=index_count,
        )
