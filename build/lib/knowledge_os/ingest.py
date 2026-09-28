"""Local source ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import unicodedata

import yaml

from .model import MetadataError, parse_document
from .workspace import (
    Workspace,
    atomic_write,
    exclusive_write,
    refresh_derived_indexes,
    stage_workspace,
    staged_documents,
    validate_workspace,
    workspace_mutation_lock,
)


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (result[:48].rstrip("-") or "source")


def _frontmatter(metadata: dict[str, object], body: str) -> bytes:
    rendered = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{rendered}\n---\n\n{body}".encode("utf-8")


def ingest_source(workspace: Workspace, source_path: Path) -> tuple[str, bool, int]:
    with workspace_mutation_lock(workspace):
        documents, issues = validate_workspace(workspace)
        if issues:
            details = "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
            raise MetadataError(f"cannot ingest into invalid corpus:\n{details}")

        source_path = source_path.expanduser().resolve()
        if not source_path.is_file():
            raise MetadataError(f"input path is not a file: {source_path}")
        if source_path.suffix.lower() not in {".md", ".markdown", ".txt"}:
            raise MetadataError("ingest accepts only .md, .markdown, and .txt files")
        try:
            original = source_path.read_bytes()
            body = original.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError as exc:
            raise MetadataError("input file must be UTF-8 text") from exc

        digest = hashlib.sha256(original).hexdigest()
        record_id = f"{_slug(source_path.stem)}-{digest[:16]}"
        destination = workspace.root / "sources" / f"{record_id}.md"
        workspace.assert_safe_path(destination)
        today = datetime.now(timezone.utc).date().isoformat()
        metadata: dict[str, object] = {
            "id": record_id,
            "title": source_path.stem,
            "type": "source",
            "status": "active",
            "scope": "general",
            "created": today,
            "updated": today,
            "provenance": [
                {
                    "kind": "local-file",
                    "reference": str(source_path),
                    "captured": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "sha256": digest,
                }
            ],
        }
        content = _frontmatter(metadata, body)
        by_id = {document.metadata["id"]: document for document in documents}

        destination_exists = destination.exists() or destination.is_symlink()
        if destination_exists:
            if not destination.is_file():
                raise MetadataError(
                    f"existing destination {workspace.relative(destination)} is not a file; refusing overwrite"
                )
            try:
                existing = parse_document(destination)
            except MetadataError as exc:
                raise MetadataError(
                    f"existing destination {workspace.relative(destination)} is invalid; refusing overwrite: {exc}"
                ) from exc
            existing_digest = existing.metadata.get("provenance", [{}])[0].get("sha256")
            if existing_digest != digest:
                raise MetadataError(
                    f"existing destination {workspace.relative(destination)} has divergent content; refusing overwrite"
                )
            if existing.body != body:
                raise MetadataError(
                    f"existing destination {workspace.relative(destination)} has divergent body; refusing overwrite"
                )
            count = refresh_derived_indexes(workspace)
            return record_id, False, count

        if record_id in by_id:
            raise MetadataError(
                f"source ID {record_id!r} already exists at {workspace.relative(by_id[record_id].path)}; refusing overwrite"
            )

        with stage_workspace(workspace) as stage:
            atomic_write(stage.root / "sources" / f"{record_id}.md", content)
            staged_documents(stage, "ingest")

        try:
            exclusive_write(destination, content)
        except FileExistsError as exc:
            raise MetadataError(
                f"destination {workspace.relative(destination)} was created by another writer; refusing overwrite"
            ) from exc
        except OSError as exc:
            raise MetadataError(
                f"canonical source write failed for {workspace.relative(destination)}; run 'kos lint' before retrying: {exc}"
            ) from exc

        count = refresh_derived_indexes(workspace)
        return record_id, True, count
