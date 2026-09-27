"""Configurable review: which writes wait for a person before they land.

By default every note is written directly and every decision is created as a
draft (the ``write-approval-policy`` decision). A knowledge base can send
some note writes to review instead, with rules in ``knowledge-os.toml``:

```toml
[[review.rule]]
folder = "drafts"          # everything in a drafts/ folder is direct
action = "direct"

[[review.rule]]
writer = "agent"           # notes agents write in project acme need review
project = "acme"

[[review.rule]]
writer = "referat"         # Referat imports go to review
```

Each rule may name:

- ``writer``: ``agent`` (any agent), ``agent:<client>`` (one MCP client, such
  as ``agent:claude-code``), ``referat`` (the Referat import), ``person``
  (someone in the app), or ``any`` (the default);
- ``project``: a project id, or ``general`` for knowledge and memory pages;
- ``folder``: a folder inside the project; it matches that folder and every
  folder below it (``""`` matches only the project's top level);
- ``writes``: ``create``, ``edit``, or ``any`` (the default);
- ``action``: ``review`` (the default) or ``direct``.

The first rule that matches decides; no match means direct, as before.
Rules govern note writes through the local API (the app, the MCP server, and
the Referat import). Decisions are not governed by them: a decision is always
a draft that a person accepts. The command line writes directly, as always.

A write that needs review is validated exactly as if it were applied, then
stored as a proposed change in ``proposals/<id>.md`` instead: a small
frontmatter block that says what it is (a new page or an edit of an existing
one, the page's revision it was made against, who proposed it and which rule
sent it to review) followed by the page's complete proposed Markdown.
Proposals are not records; nothing indexes or lints them. Accepting one
applies it with the same rules as a direct write (an edit refuses when the
page changed since it was proposed) and removes the proposal; discarding
removes it.
"""

from __future__ import annotations

import hashlib
import os
import posixpath
import re
import secrets
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from .capture import CaptureIndexError, capture_record_text
from .model import ID_PATTERN, MetadataError, SHA256_PATTERN, parse_document_text, render_document
from .mutations import MutationIndexError, MutationResult, StaleRevisionError, update_record_text
from .workspace import (
    Workspace,
    WorkspaceError,
    exclusive_write,
    is_managed_link,
    stage_workspace,
    workspace_mutation_lock,
)

PROPOSALS_DIR = "proposals"
WRITERS = ("agent", "referat", "person", "any")
WRITES = ("create", "edit", "any")
ACTIONS = ("review", "direct")
GENERAL = "general"
_RULE_FIELDS = {"writer", "project", "folder", "writes", "action"}
_PROPOSAL_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[a-z0-9-]+$")
_PROPOSAL_FIELDS = (
    "proposal",
    "action",
    "record",
    "title",
    "project_path",
    "base_sha256",
    "proposed_by",
    "proposed_at",
    "rule",
)


class ReviewError(ValueError):
    """A user-actionable refusal: the policy cannot be read, or a proposal
    cannot be stored, found, or applied."""


class ReviewPolicyError(ReviewError):
    """The review rules in ``knowledge-os.toml`` cannot be used."""


class ProposalNotFoundError(ReviewError):
    pass


# ---------------------------------------------------------------------------
# The policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewRule:
    number: int  # 1-based position in the file
    writer: str  # "agent", "agent:<client>", "referat", "person", or "any"
    project: str | None
    folder: str | None
    writes: str
    action: str

    def describe(self) -> str:
        """A short sentence naming what the rule covers, for the Decide inbox."""

        who = {
            "agent": "agents",
            "referat": "Referat imports",
            "person": "people in the app",
            "any": "anyone",
        }.get(self.writer, f"the agent {self.writer.removeprefix('agent:')}")
        what = {"create": "new pages", "edit": "edits", "any": "notes"}[self.writes]
        where = ""
        if self.project == GENERAL:
            where = " in general knowledge"
        elif self.project is not None:
            where = f" in project {self.project}"
        if self.folder is not None:
            where += f" in folder {self.folder or '(top level)'}"
        return f"Rule {self.number}: {what} by {who}{where}"


@dataclass(frozen=True)
class Writer:
    """Who is writing: ``kind`` is ``agent``, ``referat``, or ``person``;
    ``client`` is the MCP client name for an agent."""

    kind: str
    client: str | None = None


def _clean_folder(value: str, number: int) -> str:
    text = value.replace("\\", "/").strip().strip("/")
    parts = [part for part in text.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ReviewPolicyError(f"review rule {number}: folder {value!r} must be a path inside the project")
    return "/".join(parts)


def load_policy(workspace: Workspace) -> tuple[ReviewRule, ...]:
    """The review rules in ``knowledge-os.toml``, in order; none means every
    note is written directly."""

    try:
        config = tomllib.loads((workspace.root / "knowledge-os.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ReviewPolicyError(f"knowledge-os.toml cannot be read: {exc}") from exc
    section = config.get("review")
    if section is None:
        return ()
    if not isinstance(section, dict):
        raise ReviewPolicyError("[review] in knowledge-os.toml must be a table holding [[review.rule]] entries")
    unknown = sorted(set(section) - {"rule"})
    if unknown:
        raise ReviewPolicyError(f"[review] has unknown key(s) {', '.join(unknown)}; write rules as [[review.rule]]")
    entries = section.get("rule", [])
    if not isinstance(entries, list):
        raise ReviewPolicyError("review rules must be written as [[review.rule]] tables")
    rules: list[ReviewRule] = []
    for number, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ReviewPolicyError(f"review rule {number} must be a table")
        unknown = sorted(set(entry) - _RULE_FIELDS)
        if unknown:
            raise ReviewPolicyError(
                f"review rule {number} has unknown key(s) {', '.join(unknown)}; a rule may have "
                "writer, project, folder, writes, and action"
            )
        for key, value in entry.items():
            if not isinstance(value, str):
                raise ReviewPolicyError(f"review rule {number}: {key} must be text")
        writer = entry.get("writer", "any")
        if writer not in WRITERS and not (writer.startswith("agent:") and len(writer) > len("agent:")):
            raise ReviewPolicyError(
                f"review rule {number}: writer must be agent, agent:<client>, referat, person, or any, not {writer!r}"
            )
        project = entry.get("project")
        if project is not None and project != GENERAL and not ID_PATTERN.fullmatch(project):
            raise ReviewPolicyError(f"review rule {number}: project must be a project id or general, not {project!r}")
        folder = entry.get("folder")
        if folder is not None:
            if project == GENERAL:
                raise ReviewPolicyError(f"review rule {number}: general knowledge has no folders")
            folder = _clean_folder(folder, number)
        writes = entry.get("writes", "any")
        if writes not in WRITES:
            raise ReviewPolicyError(f"review rule {number}: writes must be create, edit, or any, not {writes!r}")
        action = entry.get("action", "review")
        if action not in ACTIONS:
            raise ReviewPolicyError(f"review rule {number}: action must be review or direct, not {action!r}")
        rules.append(ReviewRule(number, writer, project, folder, writes, action))
    return tuple(rules)


def _writer_matches(rule: ReviewRule, writer: Writer) -> bool:
    if rule.writer == "any":
        return True
    if rule.writer.startswith("agent:"):
        return writer.kind == "agent" and writer.client == rule.writer.removeprefix("agent:")
    return rule.writer == writer.kind


def _place_matches(rule: ReviewRule, project: str | None, folder: str) -> bool:
    if rule.project is not None and rule.project != (project or GENERAL):
        return False
    if rule.folder is None:
        return True
    if project is None:
        return False
    if rule.folder == "":
        return folder == ""
    return folder == rule.folder or folder.startswith(rule.folder + "/")


def matching_rule(
    rules: tuple[ReviewRule, ...], *, writer: Writer, project: str | None, folder: str, write: str
) -> ReviewRule | None:
    """The first rule that covers this write, or ``None`` (written directly).
    ``project`` is ``None`` for a general page; ``folder`` is the page's
    folder inside its project (``""`` at the top level)."""

    for rule in rules:
        if rule.writes not in {"any", write}:
            continue
        if _writer_matches(rule, writer) and _place_matches(rule, project, folder):
            return rule
    return None


def needs_review(
    rules: tuple[ReviewRule, ...], *, writer: Writer, project: str | None, folder: str, write: str
) -> ReviewRule | None:
    """The rule that sends this write to review, or ``None`` when it is written directly."""

    rule = matching_rule(rules, writer=writer, project=project, folder=folder, write=write)
    return rule if rule is not None and rule.action == "review" else None


# ---------------------------------------------------------------------------
# Proposed changes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Proposal:
    id: str
    action: str  # "create" or "edit"
    record_id: str
    title: str
    project_path: str | None  # create: the path inside the project, as for capture
    base_sha256: str | None  # edit: the page's revision the change was made against
    proposed_by: Mapping[str, Any]  # a provenance-shaped entry: kind, reference, captured
    proposed_at: str
    rule: str
    metadata: Mapping[str, Any]  # the page's complete proposed frontmatter
    body: str
    path: str  # workspace-relative
    sha256: str  # of the proposal file

    def text(self) -> str:
        """The page's complete proposed Markdown."""

        return render_document(dict(self.metadata), self.body).decode("utf-8")


def _stamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_id(record_id: str) -> str:
    now = datetime.now(UTC)
    return f"{now:%Y%m%d-%H%M%S}-{record_id[:60].strip('-')}-{secrets.token_hex(2)}"


def _dump(proposal_fields: dict[str, Any], metadata: Mapping[str, Any], body: str) -> bytes:
    header = yaml.safe_dump(proposal_fields, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{header}---\n{render_document(dict(metadata), body).decode('utf-8')}".encode("utf-8")


def _parse(path: Path, relative: str) -> Proposal:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as exc:
        raise ReviewError(f"{relative} is not UTF-8 text") from exc
    if not text.startswith("---\n"):
        raise ReviewError(f"{relative} does not start with the proposal's frontmatter")
    closing = text.find("\n---\n", 3)
    if closing == -1:
        raise ReviewError(f"{relative}: the proposal's frontmatter is not closed")
    try:
        fields = yaml.safe_load(text[4:closing]) or {}
    except yaml.YAMLError as exc:
        raise ReviewError(f"{relative}: the proposal's frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(fields, dict) or fields.get("action") not in {"create", "edit"}:
        raise ReviewError(f"{relative}: action must be create or edit")
    try:
        document = parse_document_text(Path("proposal.md"), text[closing + 5 :], check_filename=False)
    except MetadataError as exc:
        raise ReviewError(f"{relative}: the proposed page is not valid: {exc}") from exc
    metadata = document.metadata
    base = fields.get("base_sha256")
    if fields["action"] == "edit" and not (isinstance(base, str) and SHA256_PATTERN.fullmatch(base)):
        raise ReviewError(f"{relative}: an edit needs the page's base_sha256")
    proposed_by = fields.get("proposed_by") if isinstance(fields.get("proposed_by"), dict) else {}
    return Proposal(
        id=path.stem,
        action=fields["action"],
        record_id=str(metadata["id"]),
        title=str(metadata["title"]),
        project_path=fields.get("project_path") if isinstance(fields.get("project_path"), str) else None,
        base_sha256=base if fields["action"] == "edit" else None,
        proposed_by=proposed_by,
        proposed_at=str(fields.get("proposed_at") or ""),
        rule=str(fields.get("rule") or ""),
        metadata=metadata,
        body=document.body,
        path=relative,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


@dataclass(frozen=True)
class BrokenProposal:
    path: str
    message: str


def list_proposals(workspace: Workspace) -> tuple[list[Proposal], list[BrokenProposal]]:
    """Every proposed change, oldest first, and the files that cannot be read."""

    directory = workspace.root / PROPOSALS_DIR
    if is_managed_link(directory) or not directory.is_dir():
        return [], []
    proposals: list[Proposal] = []
    broken: list[BrokenProposal] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.suffix != ".md" or path.name == "README.md" or not path.is_file() or is_managed_link(path):
            continue
        relative = f"{PROPOSALS_DIR}/{path.name}"
        try:
            proposals.append(_parse(path, relative))
        except (ReviewError, OSError) as exc:
            broken.append(BrokenProposal(relative, str(exc)))
    proposals.sort(key=lambda item: (item.proposed_at, item.id))
    return proposals, broken


def load_proposal(workspace: Workspace, proposal_id: str) -> Proposal:
    if not _PROPOSAL_ID.fullmatch(proposal_id):
        raise ProposalNotFoundError(f"proposed change not found: {proposal_id}")
    path = workspace.root / PROPOSALS_DIR / f"{proposal_id}.md"
    try:
        workspace.assert_safe_path(path)
    except WorkspaceError as exc:
        raise ProposalNotFoundError(str(exc)) from exc
    if not path.is_file():
        raise ProposalNotFoundError(f"proposed change not found: {proposal_id}")
    return _parse(path, f"{PROPOSALS_DIR}/{proposal_id}.md")


def propose(
    workspace: Workspace,
    *,
    action: str,
    text: str,
    proposed_by: Mapping[str, Any],
    rule: str,
    project_path: str | None = None,
    base_sha256: str | None = None,
) -> Proposal:
    """Store one write as a proposed change instead of applying it.

    ``text`` is the page's complete Markdown as the write would leave it. It
    is first applied to a disposable staged copy of the workspace with the
    same rules as the direct write (capture for ``create``, ``kos update``
    with ``base_sha256`` for ``edit``), so a proposal that could never be
    accepted is refused now, with the same message.
    """

    if action not in {"create", "edit"}:
        raise ReviewError("a proposed change is a create or an edit")
    if action == "edit" and not (isinstance(base_sha256, str) and SHA256_PATTERN.fullmatch(base_sha256)):
        raise ReviewError("an edit is proposed against the page's current revision (base_sha256)")
    try:
        document = parse_document_text(Path("candidate.md"), text, check_filename=False)
    except MetadataError as exc:
        raise ReviewError(f"invalid page: {exc}") from exc
    record_id = str(document.metadata["id"])
    with workspace_mutation_lock(workspace):
        with stage_workspace(workspace) as stage:
            try:
                if action == "create":
                    capture_record_text(stage, text, project_path=Path(project_path) if project_path else None)
                else:
                    update_record_text(stage, text, expected_sha256=base_sha256 or "")
            except (CaptureIndexError, MutationIndexError):
                pass  # the staged record was written; only the staged index failed
        proposal_id = _new_id(record_id)
        relative = f"{PROPOSALS_DIR}/{proposal_id}.md"
        fields: dict[str, Any] = {
            "proposal": proposal_id,
            "action": action,
            "record": record_id,
            "title": str(document.metadata["title"]),
        }
        if action == "create" and project_path:
            fields["project_path"] = project_path
        if action == "edit":
            fields["base_sha256"] = base_sha256
        fields["proposed_by"] = dict(proposed_by)
        fields["proposed_at"] = _stamp()
        fields["rule"] = rule
        target = workspace.root / relative
        workspace.assert_safe_path(target)
        target.parent.mkdir(exist_ok=True)
        exclusive_write(target, _dump(fields, document.metadata, document.body))
    return load_proposal(workspace, proposal_id)


def _remove(workspace: Workspace, proposal: Proposal) -> None:
    path = workspace.root / proposal.path
    path.unlink(missing_ok=True)
    directory = path.parent
    try:
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        pass


def _check_unchanged(workspace: Workspace, proposal: Proposal, expected_sha256: str | None) -> None:
    if expected_sha256 is not None and expected_sha256 != proposal.sha256:
        raise StaleRevisionError(
            f"conflict for {proposal.path}: the proposed change was edited after it was shown, so nothing was done",
            expected=expected_sha256,
            actual=proposal.sha256,
        )


def accept_proposal(workspace: Workspace, proposal_id: str, *, expected_sha256: str | None = None) -> MutationResult:
    """Apply a proposed change with the direct write's rules, then remove it.

    An edit refuses (``StaleRevisionError``) when the page changed after the
    change was proposed; discard it and propose again instead. Like other
    multi-file changes this is not crash-atomic: if the process stops after
    the page is written, the proposal is still there and accepting it again
    is refused as a duplicate or a conflict; discard it.
    """

    proposal = load_proposal(workspace, proposal_id)
    _check_unchanged(workspace, proposal, expected_sha256)
    text = proposal.text()
    try:
        if proposal.action == "create":
            result = capture_record_text(
                workspace, text, project_path=Path(proposal.project_path) if proposal.project_path else None
            )
            outcome = MutationResult(result.id, result.path, result.status, result.sha256, result.index_count)
        else:
            outcome = update_record_text(workspace, text, expected_sha256=proposal.base_sha256 or "")
    except CaptureIndexError as exc:
        with workspace_mutation_lock(workspace):
            _remove(workspace, proposal)
        written = exc.result
        raise MutationIndexError(
            str(exc), MutationResult(written.id, written.path, written.status, written.sha256, 0)
        ) from exc
    except MutationIndexError:
        with workspace_mutation_lock(workspace):
            _remove(workspace, proposal)
        raise
    with workspace_mutation_lock(workspace):
        _remove(workspace, proposal)
    return outcome


def discard_proposal(workspace: Workspace, proposal_id: str, *, expected_sha256: str | None = None) -> Proposal:
    """Remove a proposed change without applying it."""

    with workspace_mutation_lock(workspace):
        proposal = load_proposal(workspace, proposal_id)
        _check_unchanged(workspace, proposal, expected_sha256)
        _remove(workspace, proposal)
    return proposal


def project_and_folder(metadata: Mapping[str, Any], relative_path: str | None) -> tuple[str | None, str]:
    """The project (``None`` for general knowledge or memory) and the folder
    inside it that a page with ``metadata`` lives in, from its
    workspace-relative path when it exists or its create ``project_path``."""

    scope = str(metadata.get("scope", ""))
    if not scope.startswith("project:"):
        return None, ""
    project = scope.removeprefix("project:")
    if relative_path is None:
        return project, ""
    prefix = f"projects/{project}/"
    inside = relative_path[len(prefix) :] if relative_path.startswith(prefix) else relative_path
    folder = posixpath.dirname(inside.replace(os.sep, "/"))
    return project, folder

