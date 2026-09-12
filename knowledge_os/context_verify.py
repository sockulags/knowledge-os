"""Verify a generated context package against the current canonical workspace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .context_policy import is_context_eligible
from .model import ID_PATTERN, SHA256_PATTERN, content_sha256
from .skills import load_skills
from .workspace import Workspace, validate_workspace, workspace_identity


class ContextVerificationError(ValueError):
    """A malformed package or invalid verification workspace."""


def _manifest(path: Path) -> dict[str, Any]:
    candidate = path.expanduser().resolve()
    if not candidate.is_file():
        raise ContextVerificationError(f"context package is not a file: {candidate}")
    try:
        text = candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ContextVerificationError("context package must be UTF-8 text") from exc
    marker = "## Package manifest\n\n```json\n"
    if marker not in text:
        raise ContextVerificationError("context package has no kos-context/v1 manifest")
    payload = text.split(marker, 1)[1].split("\n```", 1)[0]
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ContextVerificationError(f"context package manifest is invalid JSON: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("contract") != "kos-context/v1":
        raise ContextVerificationError("context package contract must be kos-context/v1")
    return manifest


def verify_context_package(workspace: Workspace, package_path: Path) -> dict[str, Any]:
    """Return deterministic item drift statuses for one context package."""

    manifest = _manifest(package_path)
    documents, issues = validate_workspace(workspace)
    skills, skill_issues = load_skills(workspace.root)

    request = manifest.get("request")
    if not isinstance(request, dict) or not isinstance(request.get("project"), str):
        raise ContextVerificationError("context package request.project is missing or invalid")
    project = request["project"]
    if not ID_PATTERN.fullmatch(project):
        raise ContextVerificationError("context package request.project is not a valid project ID")
    project_scope = f"project:{project}"

    expected_workspace = manifest.get("workspace")
    if not isinstance(expected_workspace, dict):
        raise ContextVerificationError("context package workspace identity is missing")
    current_workspace = workspace_identity(workspace)

    raw_items = manifest.get("items")
    if not isinstance(raw_items, list):
        raise ContextVerificationError("context package items must be a list")
    documents_by_id = {document.metadata["id"]: document for document in documents}
    skills_by_id = {skill.name: skill for skill in skills}
    results: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            raise ContextVerificationError(f"context package items[{index}] must be an object")
        record_id = item.get("id")
        expected_hash = item.get("content_sha256")
        expected_path = item.get("path")
        item_type = item.get("type")
        if not isinstance(record_id, str) or not record_id:
            raise ContextVerificationError(f"context package items[{index}].id is missing or invalid")
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            raise ContextVerificationError(
                f"context package item {record_id!r} has no valid content_sha256"
            )
        if not isinstance(expected_path, str) or not expected_path:
            raise ContextVerificationError(f"context package item {record_id!r} has no valid path")

        current_path: Path | None
        eligible = True
        if item_type == "skill":
            skill = skills_by_id.get(record_id)
            current_path = skill.path if skill is not None else None
        else:
            document = documents_by_id.get(record_id)
            current_path = document.path if document is not None else None
            eligible = document is not None and is_context_eligible(document, project_scope)

        result: dict[str, Any] = {"id": record_id, "expected_sha256": expected_hash}
        if current_path is None:
            result["status"] = "missing"
        else:
            current_hash = content_sha256(current_path)
            current_relative = workspace.relative(current_path)
            result["current_sha256"] = current_hash
            result["current_path"] = current_relative
            if not eligible:
                result["status"] = "ineligible"
            elif current_hash != expected_hash or current_relative != expected_path:
                result["status"] = "changed"
            else:
                result["status"] = "unchanged"
        results.append(result)

    workspace_matches = current_workspace == expected_workspace
    current_issues = [
        {"path": workspace.relative(issue.path), "message": issue.message} for issue in issues
    ]
    known_issue_keys = {(item["path"], item["message"]) for item in current_issues}
    for path, message in skill_issues:
        item = {"path": workspace.relative(path), "message": message}
        if (item["path"], item["message"]) not in known_issue_keys:
            current_issues.append(item)
    return {
        "contract": "kos-context-verification/v1",
        "workspace": {
            "matches": workspace_matches,
            "expected": expected_workspace,
            "current": current_workspace,
            "issues": current_issues,
        },
        "items": results,
        "ok": not current_issues
        and workspace_matches
        and all(item["status"] == "unchanged" for item in results),
    }
