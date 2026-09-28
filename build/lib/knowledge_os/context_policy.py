"""Trust and scope policy for the read-only context provider."""

from __future__ import annotations

from dataclasses import dataclass

from .model import Document


CONTEXT_DURABLE_TYPES = ("knowledge", "project", "memory", "synthesis")
CONTEXT_DURABLE_STATUSES = ("draft", "active")
DISCOVERY_CONTEXT_STATUS = "retained"
DISCOVERY_TRUST_LABEL = "reviewed observation; not established knowledge"
RAW_SOURCE_TRUST_LABEL = "raw source; not established knowledge"
DRAFT_DURABLE_TRUST_LABEL = "draft durable; not verified"
ACTIVE_DURABLE_TRUST_LABEL = "active durable; not verified"
VERIFIED_DURABLE_TRUST_LABEL = "verified durable"
OPERATIONAL_SKILL_TRUST_LABEL = "operational guidance"


@dataclass(frozen=True)
class ContextEligibility:
    trust_label: str
    verified: str | None = None


def context_scopes(project: str) -> tuple[str, str]:
    """Return the only scopes eligible for an ordinary project context."""

    return "general", f"project:{project}"


def context_search_types() -> tuple[str, ...]:
    return CONTEXT_DURABLE_TYPES


def context_search_statuses() -> tuple[str, ...]:
    return CONTEXT_DURABLE_STATUSES


def trust_label(document: Document) -> str:
    """Classify the epistemic state without treating lifecycle as verification."""

    metadata = document.metadata
    if metadata["type"] == "source":
        return RAW_SOURCE_TRUST_LABEL
    if metadata["type"] == "discovery":
        return DISCOVERY_TRUST_LABEL if metadata["status"] == DISCOVERY_CONTEXT_STATUS else "discovery observation; not default context"
    if metadata.get("verified") is not None:
        return VERIFIED_DURABLE_TRUST_LABEL
    if metadata["status"] == "draft":
        return DRAFT_DURABLE_TRUST_LABEL
    if metadata["status"] == "active":
        return ACTIVE_DURABLE_TRUST_LABEL
    return "unusable durable record"


def classify_context_document(document: Document, project_scope: str) -> ContextEligibility | None:
    """Classify an item or return ``None`` when it cannot enter context."""

    metadata = document.metadata
    scope = metadata["scope"]
    if scope not in {"general", project_scope}:
        return None

    record_type = metadata["type"]
    if record_type == "source":
        return None
    if record_type == "discovery":
        if scope != project_scope or metadata["status"] != DISCOVERY_CONTEXT_STATUS:
            return None
        return ContextEligibility(DISCOVERY_TRUST_LABEL)
    if record_type not in CONTEXT_DURABLE_TYPES or metadata["status"] not in CONTEXT_DURABLE_STATUSES:
        return None

    verified = metadata.get("verified")
    if verified is not None:
        verified_value = verified.isoformat() if hasattr(verified, "isoformat") else str(verified)
    else:
        verified_value = None
    return ContextEligibility(trust_label(document), verified_value)


def is_context_eligible(document: Document, project_scope: str) -> bool:
    return classify_context_document(document, project_scope) is not None
