"""Parsing and validation for managed Markdown records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from pathlib import Path
from typing import Any

import yaml


ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MANAGED_TYPES = {"source", "knowledge", "project", "memory", "synthesis"}
STATUSES = {"draft", "active", "verified", "deprecated", "superseded", "archived"}
ALLOWED_FIELDS = {
    "id",
    "title",
    "type",
    "status",
    "scope",
    "created",
    "updated",
    "verified",
    "provenance",
    "tags",
    "related",
    "sources",
    "supersedes",
    "extensions",
}
RELATION_FIELDS = ("related", "sources", "supersedes")


class MetadataError(ValueError):
    """A user-actionable error in one managed record."""


@dataclass(frozen=True)
class Document:
    path: Path
    metadata: dict[str, Any]
    body: str


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(f"{field} must be a non-empty string")
    return value.strip()


def _date(value: Any, field: str) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = _string(value, field)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise MetadataError(f"{field} must be an ISO date (YYYY-MM-DD)")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise MetadataError(f"{field} must be a valid ISO date") from exc


def _id_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise MetadataError(f"{field} must be a list of IDs")
    for item in value:
        if not ID_PATTERN.fullmatch(item):
            raise MetadataError(f"{field} contains invalid ID {item!r}")
    return value


def _validate_provenance(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise MetadataError("provenance must be a non-empty list")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise MetadataError(f"provenance[{index}] must be an object")
        for field in ("kind", "reference"):
            if field not in item:
                raise MetadataError(f"provenance[{index}] requires {field}")
            _string(item[field], f"provenance[{index}].{field}")
        if "captured" in item:
            captured_value = item["captured"]
            if not isinstance(captured_value, datetime):
                captured = _string(captured_value, f"provenance[{index}].captured")
                try:
                    datetime.fromisoformat(captured.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise MetadataError(f"provenance[{index}].captured must be an ISO timestamp") from exc
        if "sha256" in item:
            digest = _string(item["sha256"], f"provenance[{index}].sha256")
            if not SHA256_PATTERN.fullmatch(digest):
                raise MetadataError(f"provenance[{index}].sha256 must be 64 lowercase hex characters")


def validate_metadata(metadata: Any, path: Path) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        raise MetadataError("frontmatter must be a YAML object")
    unknown = sorted(
        (key for key in metadata if not isinstance(key, str) or key not in ALLOWED_FIELDS),
        key=str,
    )
    if unknown:
        raise MetadataError(f"unknown top-level field(s): {', '.join(map(str, unknown))}")
    required = ("id", "title", "type", "status", "scope", "created", "updated", "provenance")
    missing = [field for field in required if field not in metadata]
    if missing:
        raise MetadataError(f"missing required field(s): {', '.join(missing)}")

    record_id = _string(metadata["id"], "id")
    if not ID_PATTERN.fullmatch(record_id):
        raise MetadataError("id must be lowercase kebab-case")
    title = _string(metadata["title"], "title")
    record_type = _string(metadata["type"], "type")
    if record_type not in MANAGED_TYPES:
        raise MetadataError(f"type must be one of: {', '.join(sorted(MANAGED_TYPES))}")
    status = _string(metadata["status"], "status")
    if status not in STATUSES:
        raise MetadataError(f"status must be one of: {', '.join(sorted(STATUSES))}")
    scope = _string(metadata["scope"], "scope")
    if scope != "general" and not re.fullmatch(r"project:[a-z0-9]+(?:-[a-z0-9]+)*", scope):
        raise MetadataError("scope must be general or project:<lowercase-kebab>")
    if record_type == "project" and scope == "general":
        raise MetadataError("project records require scope project:<lowercase-kebab>")
    created = _date(metadata["created"], "created")
    updated = _date(metadata["updated"], "updated")
    if updated < created:
        raise MetadataError("updated must be on or after created")
    if status == "verified" and "verified" not in metadata:
        raise MetadataError("verified date is required when status is verified")
    if "verified" in metadata:
        verified = _date(metadata["verified"], "verified")
        if verified < created or verified > updated:
            raise MetadataError("verified must be between created and updated")
    _validate_provenance(metadata["provenance"])

    for field in ("tags",):
        if field in metadata and (not isinstance(metadata[field], list) or any(not isinstance(v, str) for v in metadata[field])):
            raise MetadataError(f"{field} must be a list of strings")
    for field in RELATION_FIELDS:
        if field in metadata:
            _id_list(metadata[field], field)
    if "extensions" in metadata and not isinstance(metadata["extensions"], dict):
        raise MetadataError("extensions must be an object")

    if path.stem != record_id:
        raise MetadataError(f"filename stem must equal id {record_id!r}")
    return metadata


def parse_document(path: Path) -> Document:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MetadataError("file must be UTF-8 text") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\n") != "---":
        raise MetadataError("missing YAML frontmatter opening delimiter")
    closing = next((index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\n") == "---"), None)
    if closing is None:
        raise MetadataError("missing YAML frontmatter closing delimiter")
    try:
        metadata = yaml.safe_load("".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise MetadataError(f"invalid YAML frontmatter: {exc}") from exc
    validated = validate_metadata(metadata, path)
    body = "".join(lines[closing + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    return Document(path=path, metadata=validated, body=body)
