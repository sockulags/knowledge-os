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
MANAGED_TYPES = {"source", "knowledge", "project", "memory", "synthesis", "discovery"}
STANDARD_STATUSES = {"draft", "active", "verified", "deprecated", "superseded", "archived"}
DISCOVERY_STATUSES = {"proposed", "retained", "rejected", "promoted"}
DISCOVERY_DECISION_TO_STATUS = {"retain": "retained", "reject": "rejected", "promote": "promoted"}
DISCOVERY_DECISIONS = set(DISCOVERY_DECISION_TO_STATUS)
DISCOVERY_TRANSITIONS = {
    "proposed": frozenset({"retained", "rejected", "promoted"}),
    "retained": frozenset({"rejected", "promoted"}),
    "rejected": frozenset(),
    "promoted": frozenset(),
}
CONFIDENCE_VALUES = {"low", "medium", "high"}
DISCOVERY_ONLY_FIELDS = {"evidence", "origin", "confidence", "reviews"}
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
    "evidence",
    "origin",
    "confidence",
    "reviews",
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


def _validate_evidence(value: Any) -> None:
    if not isinstance(value, list) or not value:
        raise MetadataError("evidence must be a non-empty list")
    allowed_fields = {"kind", "reference", "captured", "sha256"}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise MetadataError(f"evidence[{index}] must be an object")
        unknown = sorted(set(item) - allowed_fields, key=str)
        if unknown:
            raise MetadataError(f"evidence[{index}] has unknown field(s): {', '.join(map(str, unknown))}")
        for field in ("kind", "reference"):
            if field not in item:
                raise MetadataError(f"evidence[{index}] requires {field}")
            _string(item[field], f"evidence[{index}].{field}")
        if "captured" in item:
            captured_value = item["captured"]
            if not isinstance(captured_value, datetime):
                captured = _string(captured_value, f"evidence[{index}].captured")
                try:
                    datetime.fromisoformat(captured.replace("Z", "+00:00"))
                except ValueError as exc:
                    raise MetadataError(f"evidence[{index}].captured must be an ISO timestamp") from exc
        if "sha256" in item:
            digest = _string(item["sha256"], f"evidence[{index}].sha256")
            if not SHA256_PATTERN.fullmatch(digest):
                raise MetadataError(f"evidence[{index}].sha256 must be 64 lowercase hex characters")


def _validate_origin(value: Any) -> None:
    if not isinstance(value, dict):
        raise MetadataError("origin must be an object")
    allowed_fields = {"project", "work_item", "run"}
    unknown = sorted(set(value) - allowed_fields, key=str)
    if unknown:
        raise MetadataError(f"origin has unknown field(s): {', '.join(map(str, unknown))}")
    for field, item in value.items():
        _string(item, f"origin.{field}")
    if "project" in value and not ID_PATTERN.fullmatch(value["project"]):
        raise MetadataError("origin.project must be a lowercase kebab-case project ID")


def _validate_reviews(value: Any, created: date, updated: date) -> list[date]:
    if not isinstance(value, list):
        raise MetadataError("reviews must be a list")
    review_dates: list[date] = []
    allowed_fields = {"decision", "date", "reviewer", "reason", "target"}
    state = "proposed"
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise MetadataError(f"reviews[{index}] must be an object")
        unknown = sorted(set(item) - allowed_fields, key=str)
        if unknown:
            raise MetadataError(f"reviews[{index}] has unknown field(s): {', '.join(map(str, unknown))}")
        if "decision" not in item:
            raise MetadataError(f"reviews[{index}] requires decision")
        decision = _string(item["decision"], f"reviews[{index}].decision")
        if decision not in DISCOVERY_DECISIONS:
            raise MetadataError(f"reviews[{index}].decision must be one of: {', '.join(sorted(DISCOVERY_DECISIONS))}")
        if "date" not in item:
            raise MetadataError(f"reviews[{index}] requires date")
        review_date = _date(item["date"], f"reviews[{index}].date")
        if review_date < created or review_date > updated:
            raise MetadataError(f"reviews[{index}].date must be between created and updated")
        if review_dates and review_date < review_dates[-1]:
            raise MetadataError("review dates must be nondecreasing")
        for field in ("reviewer", "reason", "target"):
            if field in item:
                _string(item[field], f"reviews[{index}].{field}")
        if "target" in item and not ID_PATTERN.fullmatch(item["target"]):
            raise MetadataError(f"reviews[{index}].target must be a lowercase kebab-case ID")
        if decision == "reject" and not item.get("reason", "").strip():
            raise MetadataError(f"reviews[{index}] reject decision requires reason")
        if decision == "promote":
            target = item.get("target")
            if not isinstance(target, str) or not ID_PATTERN.fullmatch(target):
                raise MetadataError(f"reviews[{index}] promote decision requires a valid target")

        next_state = DISCOVERY_DECISION_TO_STATUS[decision]
        if next_state not in DISCOVERY_TRANSITIONS[state]:
            raise MetadataError(f"reviews[{index}] contains invalid discovery transition {state} -> {next_state}")
        state = next_state
        review_dates.append(review_date)
    return review_dates


def validate_metadata(metadata: Any, path: Path, *, check_filename: bool = True) -> dict[str, Any]:
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
    allowed_statuses = DISCOVERY_STATUSES if record_type == "discovery" else STANDARD_STATUSES
    if status not in allowed_statuses:
        raise MetadataError(f"status for type {record_type!r} must be one of: {', '.join(sorted(allowed_statuses))}")
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

    if record_type != "discovery":
        unexpected_discovery_fields = sorted(DISCOVERY_ONLY_FIELDS.intersection(metadata), key=str)
        if unexpected_discovery_fields:
            raise MetadataError(
                f"field(s) only allowed for discovery records: {', '.join(unexpected_discovery_fields)}"
            )
    else:
        _validate_evidence(metadata.get("evidence"))
        if "origin" in metadata:
            _validate_origin(metadata["origin"])
            origin_project = metadata["origin"].get("project")
            if origin_project is not None and scope != f"project:{origin_project}":
                raise MetadataError("discovery origin.project requires matching project scope")
        if "confidence" in metadata:
            confidence = _string(metadata["confidence"], "confidence")
            if confidence not in CONFIDENCE_VALUES:
                raise MetadataError(f"confidence must be one of: {', '.join(sorted(CONFIDENCE_VALUES))}")
        if "reviews" in metadata:
            review_dates = _validate_reviews(metadata["reviews"], created, updated)
        else:
            review_dates = []
        if status == "retained" and scope == "general":
            raise MetadataError("retained discoveries require project scope")
        reviews = metadata.get("reviews", [])
        expected_status = "proposed" if not reviews else DISCOVERY_DECISION_TO_STATUS[reviews[-1]["decision"]]
        if status != expected_status:
            raise MetadataError("discovery status must match the latest review decision")
        if status != "proposed" and review_dates[-1] != updated:
            raise MetadataError("latest review date must equal updated for non-proposed discovery")

    if check_filename and path.stem != record_id:
        raise MetadataError(f"filename stem must equal id {record_id!r}")
    return metadata


def parse_document_text(path: Path, text: str, *, check_filename: bool = True) -> Document:
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
    validated = validate_metadata(metadata, path, check_filename=check_filename)
    body = "".join(lines[closing + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    if validated["type"] == "discovery" and not body.strip():
        raise MetadataError("discovery body must be non-empty")
    return Document(path=path, metadata=validated, body=body)


def parse_document(path: Path) -> Document:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MetadataError("file must be UTF-8 text") from exc
    return parse_document_text(path, text)
