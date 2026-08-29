"""Deterministic, read-only Markdown context packages for external agents."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import json
import math
import re
from typing import Any, Iterable

from .context_policy import (
    CONTEXT_DURABLE_STATUSES,
    CONTEXT_DURABLE_TYPES,
    DISCOVERY_CONTEXT_STATUS,
    DISCOVERY_TRUST_LABEL,
    OPERATIONAL_SKILL_TRUST_LABEL,
    classify_context_document,
    context_scopes,
    context_search_statuses,
    context_search_types,
    is_context_eligible,
)
from .index import search_index_terms, validate_index
from .model import ID_PATTERN, Document, RELATION_FIELDS
from .skills import Skill, load_skills, skill_search_terms
from .workspace import Workspace, validate_workspace


STATUS_WEIGHTS = {"active": 15, "draft": 5, "retained": 15}
TYPE_WEIGHTS = {"project": 30, "knowledge": 20, "synthesis": 15, "memory": 10, "discovery": 10}
SKILL_STATUS = "operational"
TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
MAX_OMITTED_IDS = 10


class ContextError(ValueError):
    """A user-actionable context package error."""


@dataclass(frozen=True)
class ContextRequest:
    project: str
    task: str
    budget: int
    work_item: str | None = None


@dataclass(frozen=True)
class Candidate:
    key: str
    id: str
    title: str
    type: str
    status: str
    scope: str
    path: str
    provenance: list[dict[str, Any]]
    body: str
    discovery: str
    selection_reason: str
    matched_terms: tuple[str, ...] = ()
    fts_rank: int | None = None
    relationship_to: str | None = None
    score: int = 0
    trust_label: str = ""
    verified: str | None = None
    record_kind: str | None = None


def estimate_tokens(text: str) -> int:
    """Estimate tokens deterministically as ceil(Unicode characters / 4)."""

    return math.ceil(len(text) / 4)


def _terms(*values: str | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in TOKEN_PATTERN.findall(value.casefold() if value else ""):
            if term not in seen:
                seen.add(term)
                result.append(term)
    return result


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def _document_candidate(
    workspace: Workspace,
    document: Document,
    *,
    project_scope: str,
    discovery: str,
    selection_reason: str,
    matched_terms: Iterable[str] = (),
    fts_rank: int | None = None,
    relationship_to: str | None = None,
) -> Candidate:
    metadata = document.metadata
    eligibility = classify_context_document(document, project_scope)
    if eligibility is None:
        raise ContextError(f"record {metadata['id']!r} is not eligible for context")
    terms = tuple(matched_terms)
    record_kind = metadata.get("record_kind") if metadata["type"] in {"knowledge", "project"} else None
    if metadata["type"] in {"knowledge", "project"} and record_kind is None:
        record_kind = "ordinary"
    return Candidate(
        key=metadata["id"],
        id=metadata["id"],
        title=metadata["title"],
        type=metadata["type"],
        status=metadata["status"],
        scope=metadata["scope"],
        path=workspace.relative(document.path),
        provenance=_json_value(metadata["provenance"]),
        body=document.body,
        discovery=discovery,
        selection_reason=selection_reason,
        matched_terms=terms,
        fts_rank=fts_rank,
        relationship_to=relationship_to,
        score=_document_score(metadata, project_scope, len(terms), fts_rank, relationship_to is not None),
        trust_label=eligibility.trust_label,
        verified=eligibility.verified,
        record_kind=record_kind,
    )


def _document_score(
    metadata: dict[str, Any],
    project_scope: str,
    match_count: int,
    fts_rank: int | None,
    related: bool,
) -> int:
    scope_bonus = 100 if metadata["scope"] == project_scope else 0
    match_bonus = match_count * 25
    fts_bonus = max(0, 30 - fts_rank) if fts_rank is not None else 0
    type_bonus = TYPE_WEIGHTS[metadata["type"]]
    status_bonus = STATUS_WEIGHTS[metadata["status"]]
    relationship_bonus = 20 if related else 0
    return scope_bonus + match_bonus + fts_bonus + type_bonus + status_bonus + relationship_bonus


def _skill_candidate(workspace: Workspace, skill: Skill, request_terms: list[str]) -> Candidate | None:
    searchable_terms = set(_terms(*skill_search_terms(skill)))
    matched = tuple(term for term in request_terms if term in searchable_terms)
    if len(matched) < 2:
        return None
    return Candidate(
        key=f"skill:{skill.name}",
        id=skill.name,
        title=skill.description,
        type="skill",
        status=SKILL_STATUS,
        scope="operational",
        path=workspace.relative(skill.path),
        provenance=[{"kind": "skill-file", "reference": workspace.relative(skill.path)}],
        body=skill.body,
        discovery="relevant-skill",
        selection_reason=f"skill matches distinct request terms: {', '.join(matched)}",
        matched_terms=matched,
        score=len(matched) * 25 + 18,
        trust_label=OPERATIONAL_SKILL_TRUST_LABEL,
    )


def _skill_candidates(workspace: Workspace, request_terms: list[str]) -> list[Candidate]:
    skills, issues = load_skills(workspace.root)
    if issues:
        details = "\n".join(f"{path}: {message}" for path, message in issues)
        raise ContextError(f"cannot use invalid skills:\n{details}")
    return [candidate for skill in skills if (candidate := _skill_candidate(workspace, skill, request_terms)) is not None]


def _resolve_project(documents: list[Document], project: str) -> Document:
    scope = f"project:{project}"
    scoped = [document for document in documents if document.metadata["scope"] == scope]
    if not scoped:
        raise ContextError(f"project {project!r} was not found (expected scope {scope!r})")

    exact = [
        document
        for document in scoped
        if document.metadata["type"] == "project" and document.metadata["id"] == project
    ]
    if len(exact) != 1:
        if len(exact) > 1:
            raise ContextError(
                f"project {project!r} has an ambiguous project overview; expected exactly one "
                f"type 'project' record with id {project!r} and scope {scope!r}"
            )
        raise ContextError(
            f"project {project!r} has no valid project overview; expected exactly one usable "
            f"type 'project' record with id {project!r} and scope {scope!r}"
        )
    if not is_context_eligible(exact[0], scope):
        raise ContextError(
            f"project {project!r} has no usable project overview; the exact overview must have "
            "draft or active status"
        )
    return exact[0]


def _rank_key(candidate: Candidate) -> tuple[int, int, str, str]:
    return (-candidate.score, candidate.fts_rank if candidate.fts_rank is not None else 10**9, candidate.id, candidate.path)


def _with_relationship(candidate: Candidate, related_id: str, reason: str) -> Candidate:
    if candidate.relationship_to is not None:
        return candidate
    return replace(
        candidate,
        discovery=f"{candidate.discovery}+explicit-one-hop-relationship",
        selection_reason=f"{candidate.selection_reason}; {reason}",
        relationship_to=related_id,
        score=candidate.score + 20,
    )


def _context_eligible(document: Document, project_scope: str) -> bool:
    return is_context_eligible(document, project_scope)


def _manifest_item(candidate: Candidate) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": candidate.id,
        "title": candidate.title,
        "selection_mode": "mandatory" if candidate.discovery.startswith("mandatory-project") else "ranked",
        "discovery": candidate.discovery,
        "selection_reason": candidate.selection_reason,
        "score": candidate.score,
        "matched_terms": list(candidate.matched_terms),
        "fts_rank": candidate.fts_rank,
        "relationship_to": candidate.relationship_to,
        "type": candidate.type,
        "scope": candidate.scope,
        "status": candidate.status,
        "trust": candidate.trust_label,
        "path": candidate.path,
        "provenance": candidate.provenance,
    }
    if candidate.record_kind is not None:
        item["record_kind"] = candidate.record_kind
    if candidate.verified is not None:
        item["verified"] = candidate.verified
    return item


def _render(
    request: ContextRequest,
    selected: list[Candidate],
    ranked_candidates: list[Candidate],
    excluded: list[Candidate],
    used_tokens: int,
) -> str:
    project_scope = f"project:{request.project}"
    manifest = {
        "contract": "kos-context/v1",
        "request": {
            "project": request.project,
            "task": request.task,
            "work_item": request.work_item,
        },
        "eligibility": {
            "included_scopes": list(context_scopes(request.project)),
            "durable_types": list(CONTEXT_DURABLE_TYPES),
            "durable_statuses": list(CONTEXT_DURABLE_STATUSES),
            "retained_discovery": {
                "scope": project_scope,
                "status": DISCOVERY_CONTEXT_STATUS,
                "trust": DISCOVERY_TRUST_LABEL,
            },
            "sources": "excluded from default context",
        },
        "budget": {
            "configured_tokens": request.budget,
            "used_tokens": used_tokens,
            "estimator": "ceil(unicode_character_count/4)",
        },
        "selection": {
            "mode": "deterministic-greedy-rank",
            "ranked_candidates": len(ranked_candidates),
            "budget_excluded": len(excluded),
            "budget_excluded_ids": [candidate.id for candidate in excluded[:MAX_OMITTED_IDS]],
        },
        "items": [_manifest_item(candidate) for candidate in selected],
    }
    lines = [
        "# WARNING: GENERATED, NON-CANONICAL CONTEXT PACKAGE",
        "",
        "This package is read-only agent context assembled from canonical Markdown and operational skills. It is not canonical knowledge; do not write it back as a durable record.",
        "",
        "## Package manifest",
        "",
        "```json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Selected context",
        "",
    ]
    for candidate in selected:
        kind = candidate.record_kind if candidate.record_kind is not None else "n/a"
        lines.extend(
            [
                f"--- BEGIN ITEM {candidate.id} ---",
                f"**Title:** {candidate.title}",
                f"**Type:** {candidate.type} | **Record kind:** {kind} | **Scope:** {candidate.scope} | **Status:** {candidate.status}",
                f"**Trust:** {candidate.trust_label}",
                *([f"**Verified:** {candidate.verified}"] if candidate.verified is not None else []),
                f"**Path:** {candidate.path}",
                f"**Selection:** {candidate.selection_reason}",
                "**Content:**",
                candidate.body,
                f"--- END ITEM {candidate.id} ---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _stable_render(
    request: ContextRequest,
    selected: list[Candidate],
    ranked_candidates: list[Candidate],
    excluded: list[Candidate],
) -> tuple[str, int]:
    used = 0
    for _ in range(100):
        rendered = _render(request, selected, ranked_candidates, excluded, used)
        estimated = estimate_tokens(rendered)
        if estimated == used:
            return rendered, estimated
        used = estimated
    raise ContextError("could not stabilize deterministic package budget estimate")


def _validate_request(request: ContextRequest) -> None:
    if not isinstance(request.project, str) or not ID_PATTERN.fullmatch(request.project):
        raise ContextError("--project must be a lowercase kebab-case project ID")
    if not isinstance(request.task, str) or not request.task.strip():
        raise ContextError("--task must not be empty")
    if request.work_item is not None and not request.work_item.strip():
        raise ContextError("--work-item must not be empty when provided")
    if not isinstance(request.budget, int) or isinstance(request.budget, bool) or request.budget < 1:
        raise ContextError("--budget must be at least 1")


def _collect_ranked_candidates(
    workspace: Workspace,
    documents: list[Document],
    overview: Document,
    request_terms: list[str],
    project_scope: str,
) -> list[Candidate]:
    document_by_id = {document.metadata["id"]: document for document in documents}
    scopes = context_scopes(project_scope.removeprefix("project:"))
    fts_rows = search_index_terms(
        workspace,
        request_terms,
        scopes,
        context_search_statuses(),
        types=context_search_types(),
    )
    retained_discovery_rows = search_index_terms(
        workspace,
        request_terms,
        (project_scope,),
        (DISCOVERY_CONTEXT_STATUS,),
        types=("discovery",),
    )
    fts_rows.extend(retained_discovery_rows)
    direct_ids: set[str] = set()
    candidates: dict[str, Candidate] = {}
    for row in fts_rows:
        document = document_by_id[row["id"]]
        if not _context_eligible(document, project_scope):
            continue
        direct_ids.add(row["id"])
        matched = tuple(row["matched_terms"])
        candidates[row["id"]] = _document_candidate(
            workspace,
            document,
            project_scope=project_scope,
            discovery="fts-task-work-item",
            selection_reason=f"FTS task/work-item match: {', '.join(matched)}",
            matched_terms=matched,
            fts_rank=row["fts_rank"],
        )

    relationship_sources = set(direct_ids)
    relationship_sources.add(overview.metadata["id"])
    for source_id in sorted(relationship_sources):
        source = document_by_id.get(source_id)
        if source is None or not _context_eligible(source, project_scope):
            continue
        for field in RELATION_FIELDS:
            for target_id in source.metadata.get(field, []):
                target = document_by_id[target_id]
                if not _context_eligible(target, project_scope) or target_id == overview.metadata["id"]:
                    continue
                if target_id in candidates:
                    candidates[target_id] = _with_relationship(
                        candidates[target_id],
                        source_id,
                        f"one-hop relationship from {source_id} via {field}",
                    )
                else:
                    candidates[target_id] = _document_candidate(
                        workspace,
                        target,
                        project_scope=project_scope,
                        discovery="explicit-one-hop-relationship",
                        selection_reason=f"one-hop relationship from {source_id} via {field}",
                        relationship_to=source_id,
                    )

    for source in documents:
        if not _context_eligible(source, project_scope):
            continue
        source_id = source.metadata["id"]
        for field in RELATION_FIELDS:
            related_ids = [target_id for target_id in source.metadata.get(field, []) if target_id in relationship_sources]
            if not related_ids or source_id == overview.metadata["id"]:
                continue
            target_id = related_ids[0]
            if source_id in candidates:
                candidates[source_id] = _with_relationship(
                    candidates[source_id],
                    target_id,
                    f"one-hop relationship via {field} to {target_id}",
                )
            else:
                candidates[source_id] = _document_candidate(
                    workspace,
                    source,
                    project_scope=project_scope,
                    discovery="explicit-one-hop-relationship",
                    selection_reason=f"one-hop relationship via {field} to {target_id}",
                    relationship_to=target_id,
                )
            break

    for skill in _skill_candidates(workspace, request_terms):
        candidates[skill.key] = skill
    return sorted(candidates.values(), key=_rank_key)


def _fit_to_budget(
    request: ContextRequest,
    overview: Candidate,
    ranked_candidates: list[Candidate],
) -> str:
    _, minimum_tokens = _stable_render(request, [overview], ranked_candidates, ranked_candidates)
    if minimum_tokens > request.budget:
        raise ContextError(
            f"--budget {request.budget} is too small for the mandatory project context envelope; "
            f"requires at least {minimum_tokens} estimated tokens"
        )

    selected = [overview]
    for candidate in ranked_candidates:
        tentative = selected + [candidate]
        tentative_keys = {item.key for item in tentative}
        excluded = [item for item in ranked_candidates if item.key not in tentative_keys]
        _, estimated = _stable_render(request, tentative, ranked_candidates, excluded)
        if estimated <= request.budget:
            selected.append(candidate)

    selected_keys = {item.key for item in selected}
    excluded = [candidate for candidate in ranked_candidates if candidate.key not in selected_keys]
    rendered, _ = _stable_render(request, selected, ranked_candidates, excluded)
    return rendered


def build_context(request: ContextRequest, workspace: Workspace) -> str:
    """Build one deterministic package without mutating Markdown or indexes."""

    _validate_request(request)
    documents, issues = validate_workspace(workspace)
    if issues:
        details = "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise ContextError(f"cannot generate context from invalid corpus:\n{details}")
    validate_index(workspace, documents)

    overview = _resolve_project(documents, request.project)
    project_scope = f"project:{request.project}"
    request_terms = _terms(request.task, request.work_item)
    if not request_terms:
        raise ContextError("context request must contain at least one searchable term")
    optional = _collect_ranked_candidates(workspace, documents, overview, request_terms, project_scope)

    overview_candidate = _document_candidate(
        workspace,
        overview,
        project_scope=project_scope,
        discovery="mandatory-project-overview",
        selection_reason="mandatory project context",
    )
    optional = [candidate for candidate in optional if candidate.key != overview_candidate.key]
    return _fit_to_budget(request, overview_candidate, optional)
