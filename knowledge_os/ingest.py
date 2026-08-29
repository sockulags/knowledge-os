"""Local source ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
import tempfile
import unicodedata

import yaml

from .index import rebuild_indexes
from .model import MetadataError, parse_document
from .workspace import Workspace, atomic_write, validate_workspace


def _slug(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    result = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (result[:48].rstrip("-") or "source")


def _frontmatter(metadata: dict[str, object], body: str) -> bytes:
    rendered = yaml.safe_dump(metadata, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{rendered}\n---\n\n{body}".encode("utf-8")


def ingest_source(workspace: Workspace, source_path: Path) -> tuple[str, bool, int]:
    _, issues = validate_workspace(workspace)
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
    with tempfile.TemporaryDirectory(prefix="kos-validate-") as validation_dir:
        temp_validation = Path(validation_dir) / f"{record_id}.md"
        temp_validation.write_bytes(content)
        parse_document(temp_validation)

    if destination.exists():
        try:
            existing = parse_document(destination)
        except MetadataError as exc:
            raise MetadataError(f"existing destination {workspace.relative(destination)} is invalid; refusing overwrite: {exc}") from exc
        existing_digest = existing.metadata.get("provenance", [{}])[0].get("sha256")
        if existing_digest != digest:
            raise MetadataError(f"existing destination {workspace.relative(destination)} has divergent content; refusing overwrite")
        if existing.body != body:
            raise MetadataError(f"existing destination {workspace.relative(destination)} has divergent body; refusing overwrite")
        count = rebuild_indexes(workspace)
        return record_id, False, count

    atomic_write(destination, content)
    count = rebuild_indexes(workspace)
    return record_id, True, count
