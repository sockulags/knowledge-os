"""Workspace discovery, corpus validation, and safe file writes."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Iterable

from .model import Document, MetadataError, parse_document


MANAGED_DIRS = {
    "sources": "source",
    "knowledge": "knowledge",
    "projects": "project",
    "memory": "memory",
    "syntheses": "synthesis",
    "discoveries": "discovery",
}


class WorkspaceError(ValueError):
    """A workspace or operation error."""


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


class Workspace:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        if not (self.root / "knowledge-os.toml").is_file():
            raise WorkspaceError(f"workspace marker not found at {self.root / 'knowledge-os.toml'}")

    @classmethod
    def discover(cls, requested: Path | None = None, start: Path | None = None) -> "Workspace":
        if requested is not None:
            return cls(requested)
        current = (start or Path.cwd()).expanduser().resolve()
        for candidate in (current, *current.parents):
            if (candidate / "knowledge-os.toml").is_file():
                return cls(candidate)
        raise WorkspaceError("workspace marker knowledge-os.toml not found; use --root PATH")

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def managed_files(self) -> Iterable[Path]:
        for directory in MANAGED_DIRS:
            base = self.root / directory
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if (
                    path.is_file()
                    and path.suffix.lower() in {".md", ".markdown"}
                    and path != base / "README.md"
                ):
                    yield path


def validate_workspace(workspace: Workspace) -> tuple[list[Document], list[Issue]]:
    documents: list[Document] = []
    issues: list[Issue] = []
    ids: dict[str, Path] = {}
    for path in workspace.managed_files():
        try:
            document = parse_document(path)
        except MetadataError as exc:
            issues.append(Issue(path, str(exc)))
            continue
        expected_type = MANAGED_DIRS[path.relative_to(workspace.root).parts[0]]
        if document.metadata["type"] != expected_type:
            issues.append(Issue(path, f"type {document.metadata['type']!r} does not match directory ({expected_type!r})"))
        record_id = document.metadata["id"]
        if record_id in ids:
            issues.append(Issue(path, f"duplicate id {record_id!r}; already defined at {workspace.relative(ids[record_id])}"))
        else:
            ids[record_id] = path
        documents.append(document)

    documents_by_id = {document.metadata["id"]: document for document in documents}
    for document in documents:
        for field in ("related", "sources", "supersedes"):
            for target in document.metadata.get(field, []):
                if target not in ids:
                    issues.append(Issue(document.path, f"unresolved relationship id {target!r} in {field}"))
        if document.metadata["type"] == "discovery":
            for index, evidence in enumerate(document.metadata["evidence"]):
                if evidence["kind"] == "record" and evidence["reference"] not in ids:
                    issues.append(
                        Issue(
                            document.path,
                            f"unresolved evidence record id {evidence['reference']!r} in evidence[{index}]",
                        )
                    )
        if document.metadata["type"] == "discovery" and document.metadata["status"] == "promoted":
            metadata = document.metadata
            discovery_id = metadata["id"]
            target_id = metadata["reviews"][-1]["target"]
            if target_id == discovery_id:
                issues.append(Issue(document.path, "promoted discovery target must not reference itself"))
                continue
            target = documents_by_id.get(target_id)
            if target is None:
                issues.append(Issue(document.path, f"promoted discovery target {target_id!r} does not exist"))
                continue

            target_metadata = target.metadata
            target_scope = target_metadata["scope"]
            expected_type = "knowledge" if target_scope == "general" else "project"
            if target_metadata["type"] != expected_type:
                issues.append(
                    Issue(
                        document.path,
                        f"promoted discovery target {target_id!r} with scope {target_scope!r} "
                        f"must have type {expected_type!r}",
                    )
                )
            discovery_scope = metadata["scope"]
            if (
                discovery_scope.startswith("project:")
                and target_scope.startswith("project:")
                and target_scope != discovery_scope
            ):
                issues.append(
                    Issue(
                        document.path,
                        f"project-scoped promoted discovery cannot target different project scope {target_scope!r}",
                    )
                )
            if target_id not in metadata.get("related", []):
                issues.append(Issue(document.path, f"promoted discovery related must contain target {target_id!r}"))
            if discovery_id not in target_metadata.get("sources", []):
                issues.append(
                    Issue(
                        document.path,
                        f"promotion target {target_id!r} sources must contain discovery id {discovery_id!r}",
                    )
                )
            if not any(
                item.get("kind") == "discovery" and item.get("reference") == discovery_id
                for item in target_metadata["provenance"]
            ):
                issues.append(
                    Issue(
                        document.path,
                        f"promotion target {target_id!r} provenance must include discovery reference {discovery_id!r}",
                    )
                )
    return sorted(documents, key=lambda item: item.metadata["id"]), sorted(issues, key=lambda item: (str(item.path), item.message))


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()
