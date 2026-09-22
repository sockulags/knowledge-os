"""Conflict-safe updates and accepted decision transitions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from .model import (
    DECISION_ACCEPTANCE_KIND,
    DECISION_WITHDRAWAL_KIND,
    SHA256_PATTERN,
    Document,
    MetadataError,
    content_sha256,
    parse_document_text,
    render_document,
)
from .workspace import (
    Issue,
    Workspace,
    WorkspaceError,
    atomic_write,
    refresh_derived_indexes,
    stage_workspace,
    staged_documents,
    validate_workspace,
    workspace_mutation_lock,
)

SYSTEM_PROVENANCE_KINDS = {"discovery", DECISION_ACCEPTANCE_KIND, DECISION_WITHDRAWAL_KIND}
IMMUTABLE_UPDATE_FIELDS = ("id", "type", "scope", "created", "record_kind", "status", "supersedes")


class MutationError(ValueError):
    """A user-actionable canonical mutation error."""


@dataclass(frozen=True)
class MutationResult:
    id: str
    path: str
    status: str
    sha256: str
    index_count: int


@dataclass(frozen=True)
class SupersedeResult:
    old_id: str
    new_id: str
    old_status: str
    new_status: str
    old_sha256: str
    new_sha256: str
    index_count: int


def _details(issues: list[Issue]) -> str:
    return "\n".join(f"{issue.path}: {issue.message}" for issue in issues)


def _load_candidate(input_path: Path) -> Document:
    path = input_path.expanduser().resolve()
    if not path.is_file():
        raise MutationError(f"update input path is not a file: {path}")
    if path.suffix.lower() not in {".md", ".markdown"}:
        raise MutationError("update accepts only .md and .markdown structured input")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise MutationError("update input must be UTF-8 text") from exc
    try:
        return parse_document_text(path, text, check_filename=False)
    except MetadataError as exc:
        raise MutationError(f"invalid update candidate {path}: {exc}") from exc


def _require_hash(value: str, option: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise MutationError(f"{option} must be 64 lowercase hex characters")
    return value


def _assert_expected(path: Path, expected: str, option: str) -> None:
    expected = _require_hash(expected, option)
    actual = content_sha256(path)
    if actual != expected:
        raise MutationError(
            f"conflict for {path.name}: expected sha256 {expected}, found {actual}; "
            "the record changed after it was read, so nothing was written"
        )


def _documents_for_mutation(workspace: Workspace, operation: str) -> tuple[list[Document], dict[str, Document]]:
    documents, issues = validate_workspace(workspace)
    if issues:
        raise MutationError(f"cannot {operation} in an invalid corpus:\n{_details(issues)}")
    return documents, {document.metadata["id"]: document for document in documents}


def _today_after(value: object) -> str:
    current = value if isinstance(value, date) else date.fromisoformat(str(value))
    return max(datetime.now(UTC).date(), current).isoformat()


def _date_value(value: object) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _acceptance(reference: str) -> dict[str, object]:
    if not isinstance(reference, str) or not reference.strip():
        raise MutationError("--acceptance-reference must be a non-empty string")
    return {
        "kind": DECISION_ACCEPTANCE_KIND,
        "reference": reference.strip(),
        "captured": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _withdrawal(reason: str) -> dict[str, object]:
    if not isinstance(reason, str) or not reason.strip():
        raise MutationError("--reason must be a non-empty string")
    return {
        "kind": DECISION_WITHDRAWAL_KIND,
        "reference": reason.strip(),
        "captured": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _write_one(workspace: Workspace, document: Document, metadata: dict[str, object], body: str, operation: str) -> MutationResult:
    canonical = render_document(metadata, body)
    relative = workspace.relative(document.path)
    with stage_workspace(workspace) as stage:
        atomic_write(stage.root / relative, canonical)
        staged_documents(stage, operation)

    try:
        atomic_write(document.path, canonical)
    except OSError as exc:
        raise MutationError(f"canonical write failed for {relative}; nothing was replaced: {exc}") from exc

    try:
        count = refresh_derived_indexes(workspace)
    except WorkspaceError as exc:
        raise MutationError(str(exc)) from exc
    return MutationResult(
        id=str(metadata["id"]),
        path=relative,
        status=str(metadata["status"]),
        sha256=content_sha256(document.path),
        index_count=count,
    )


def update_record(
    workspace: Workspace,
    input_path: Path,
    *,
    expected_sha256: str,
    confirm_non_material: bool = False,
    change_reference: str | None = None,
) -> MutationResult:
    """Replace one record only when the caller still has its exact prior bytes."""

    with workspace_mutation_lock(workspace):
        _, by_id = _documents_for_mutation(workspace, "update a record")
        candidate = _load_candidate(input_path)
        current = by_id.get(candidate.metadata["id"])
        if current is None:
            raise MutationError(f"record not found: {candidate.metadata['id']}")
        _assert_expected(current.path, expected_sha256, "--expected-sha256")

        for field in IMMUTABLE_UPDATE_FIELDS:
            current_value = current.metadata.get(field)
            candidate_value = candidate.metadata.get(field)
            if field == "created":
                current_value = _date_value(current_value)
                candidate_value = _date_value(candidate_value)
            if current_value != candidate_value:
                raise MutationError(
                    f"update must not change {field}; use the dedicated lifecycle or supersede operation"
                )
        if _date_value(candidate.metadata["updated"]) < _date_value(current.metadata["updated"]):
            raise MutationError("update candidate updated date must not move backwards")

        if change_reference is not None and not confirm_non_material:
            raise MutationError("--change-reference is only valid with --confirm-non-material")

        current_system = [
            item for item in current.metadata["provenance"] if item["kind"] in SYSTEM_PROVENANCE_KINDS
        ]
        candidate_system = [
            item for item in candidate.metadata["provenance"] if item["kind"] in SYSTEM_PROVENANCE_KINDS
        ]
        if current_system != candidate_system:
            raise MutationError("update must not alter system-managed discovery or decision-acceptance provenance")

        metadata = deepcopy(candidate.metadata)
        if (
            current.metadata.get("record_kind") == "decision"
            and current.metadata["status"] in {"active", "superseded"}
            and current.body != candidate.body
        ):
            if not confirm_non_material:
                raise MutationError(
                    "changing an accepted decision body requires --confirm-non-material; "
                    "a material decision change must use a new draft and 'kos supersede'"
                )
            if not isinstance(change_reference, str) or not change_reference.strip():
                raise MutationError("--change-reference is required with --confirm-non-material")
            metadata["provenance"] = [
                *metadata["provenance"],
                {
                    "kind": "editorial-update",
                    "reference": change_reference.strip(),
                    "captured": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                },
            ]
            metadata["updated"] = _today_after(metadata["updated"])

        return _write_one(workspace, current, metadata, candidate.body, "update a record")


def accept_decision(
    workspace: Workspace,
    record_id: str,
    *,
    expected_sha256: str,
    acceptance_reference: str,
) -> MutationResult:
    """Make one proposed decision active with explicit acceptance provenance."""

    with workspace_mutation_lock(workspace):
        _, by_id = _documents_for_mutation(workspace, "accept a decision")
        current = by_id.get(record_id)
        if current is None:
            raise MutationError(f"record not found: {record_id}")
        _assert_expected(current.path, expected_sha256, "--expected-sha256")
        if current.metadata.get("record_kind") != "decision":
            raise MutationError(f"record {record_id!r} is not a decision")
        if current.metadata["status"] != "draft":
            raise MutationError(f"decision {record_id!r} must be draft before acceptance")
        if current.metadata.get("supersedes"):
            raise MutationError(
                f"decision {record_id!r} proposes a replacement; use 'kos supersede' to activate it"
            )

        metadata = deepcopy(current.metadata)
        metadata["status"] = "active"
        metadata["updated"] = _today_after(metadata["updated"])
        metadata["provenance"] = [*metadata["provenance"], _acceptance(acceptance_reference)]
        return _write_one(workspace, current, metadata, current.body, "accept a decision")


def withdraw_decision(
    workspace: Workspace,
    record_id: str,
    *,
    expected_sha256: str,
    reason: str,
) -> MutationResult:
    """Retire one proposed decision to archived without accepting it."""

    with workspace_mutation_lock(workspace):
        _, by_id = _documents_for_mutation(workspace, "withdraw a decision")
        current = by_id.get(record_id)
        if current is None:
            raise MutationError(f"record not found: {record_id}")
        _assert_expected(current.path, expected_sha256, "--expected-sha256")
        if current.metadata.get("record_kind") != "decision":
            raise MutationError(f"record {record_id!r} is not a decision")
        if current.metadata["status"] != "draft":
            raise MutationError(
                f"decision {record_id!r} must be draft before withdrawal; "
                "retire an active decision with 'kos supersede' instead"
            )

        metadata = deepcopy(current.metadata)
        metadata["status"] = "archived"
        metadata["updated"] = _today_after(metadata["updated"])
        metadata["provenance"] = [*metadata["provenance"], _withdrawal(reason)]
        return _write_one(workspace, current, metadata, current.body, "withdraw a decision")


def supersede_decision(
    workspace: Workspace,
    old_id: str,
    new_id: str,
    *,
    expected_old_sha256: str,
    expected_new_sha256: str,
    acceptance_reference: str,
) -> SupersedeResult:
    """Atomically intend and best-effort commit an accepted decision replacement pair."""

    if old_id == new_id:
        raise MutationError("old and new decision IDs must differ")
    with workspace_mutation_lock(workspace):
        documents, by_id = _documents_for_mutation(workspace, "supersede a decision")
        old = by_id.get(old_id)
        new = by_id.get(new_id)
        if old is None:
            raise MutationError(f"record not found: {old_id}")
        if new is None:
            raise MutationError(f"record not found: {new_id}")
        _assert_expected(old.path, expected_old_sha256, "--expected-old-sha256")
        _assert_expected(new.path, expected_new_sha256, "--expected-new-sha256")
        if old.metadata.get("record_kind") != "decision" or new.metadata.get("record_kind") != "decision":
            raise MutationError("supersede requires two decision records")
        if old.metadata["status"] != "active":
            raise MutationError(f"old decision {old_id!r} must be active")
        if new.metadata["status"] != "draft":
            raise MutationError(f"replacement decision {new_id!r} must be draft")
        if old.metadata["scope"] != new.metadata["scope"]:
            raise MutationError("replacement decision must use the same scope as the old decision")
        if new.metadata.get("supersedes") != [old_id]:
            raise MutationError(f"replacement decision {new_id!r} must declare supersedes: [{old_id}]")
        competing = [
            item.metadata["id"]
            for item in documents
            if item.metadata.get("record_kind") == "decision"
            and item.metadata["status"] == "draft"
            and old_id in item.metadata.get("supersedes", [])
            and item.metadata["id"] != new_id
        ]
        if competing:
            raise MutationError(
                f"old decision {old_id!r} has competing draft replacements: {', '.join(sorted(competing))}"
            )

        old_metadata = deepcopy(old.metadata)
        new_metadata = deepcopy(new.metadata)
        old_metadata["status"] = "superseded"
        old_metadata["updated"] = _today_after(old_metadata["updated"])
        new_metadata["status"] = "active"
        new_metadata["updated"] = _today_after(new_metadata["updated"])
        new_metadata["provenance"] = [*new_metadata["provenance"], _acceptance(acceptance_reference)]
        old_bytes = render_document(old_metadata, old.body)
        new_bytes = render_document(new_metadata, new.body)
        old_relative = workspace.relative(old.path)
        new_relative = workspace.relative(new.path)

        with stage_workspace(workspace) as stage:
            atomic_write(stage.root / new_relative, new_bytes)
            atomic_write(stage.root / old_relative, old_bytes)
            staged_documents(stage, "supersede a decision")

        old_snapshot = old.path.read_bytes()
        new_snapshot = new.path.read_bytes()
        try:
            # Keep the old accepted decision active until the replacement bytes exist.
            atomic_write(new.path, new_bytes)
            atomic_write(old.path, old_bytes)
        except OSError as exc:
            recovery_errors: list[str] = []
            for path, snapshot in ((new.path, new_snapshot), (old.path, old_snapshot)):
                try:
                    atomic_write(path, snapshot)
                except OSError as recovery_exc:
                    recovery_errors.append(f"{workspace.relative(path)}: {recovery_exc}")
            if recovery_errors:
                raise MutationError(
                    "supersede was interrupted and automatic repair was incomplete for "
                    f"{old_relative} and {new_relative}; inspect both records, repair canonical Markdown, "
                    "then run 'kos lint' and 'kos index': " + "; ".join(recovery_errors)
                ) from exc
            raise MutationError(
                f"supersede write failed for {old_relative} and {new_relative}; original bytes were restored: {exc}"
            ) from exc

        try:
            count = refresh_derived_indexes(workspace)
        except WorkspaceError as exc:
            raise MutationError(str(exc)) from exc
        return SupersedeResult(
            old_id=old_id,
            new_id=new_id,
            old_status="superseded",
            new_status="active",
            old_sha256=content_sha256(old.path),
            new_sha256=content_sha256(new.path),
            index_count=count,
        )
