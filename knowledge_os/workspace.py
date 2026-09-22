"""Workspace discovery, corpus validation, locking, and safe file writes."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import tomllib
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from .model import ID_PATTERN, RELATION_FIELDS, Document, MetadataError, parse_document

MANAGED_DIRS = {
    "sources": "source",
    "knowledge": "knowledge",
    "projects": "project",
    "memory": "memory",
    "syntheses": "synthesis",
    "discoveries": "discovery",
}
PROJECT_ROOT_FILE = "README.md"
CANONICAL_PROVENANCE_KINDS = {"record", "discovery"}


class WorkspaceError(ValueError):
    """A workspace or operation error."""


class CorpusValidationError(WorkspaceError):
    """The intended result of a mutation would leave the corpus invalid.

    ``issues`` holds ``(workspace-relative path, message)`` pairs: the same
    messages ``kos lint`` prints, located relative to the staged workspace.
    """

    def __init__(self, message: str, issues: tuple[tuple[str, str], ...]):
        super().__init__(message)
        self.issues = issues


@dataclass(frozen=True)
class Issue:
    path: Path
    message: str


def is_managed_link(path: Path) -> bool:
    """Recognize symbolic links and Windows reparse-point links."""

    if path.is_symlink() or os.path.islink(path):
        return True
    if os.name == "nt":
        try:
            attributes = os.lstat(path).st_file_attributes
        except (AttributeError, OSError):
            return False
        return bool(attributes & 0x40000000)  # FILE_ATTRIBUTE_REPARSE_POINT
    return False


class Workspace:
    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        marker = self.root / "knowledge-os.toml"
        if is_managed_link(marker):
            raise WorkspaceError("workspace marker knowledge-os.toml must not be a symlink")
        if not marker.is_file():
            raise WorkspaceError(f"workspace marker not found at {marker}")
        self.config = _load_config(marker)

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
        candidate = path.expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve(strict=False).relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"path {path} resolves outside workspace root {self.root}") from exc
        return resolved.as_posix()

    def assert_safe_path(self, path: Path) -> None:
        """Reject symlinked managed components and paths outside this workspace."""

        candidate = path.expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            resolved = candidate.resolve(strict=False)
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"managed path {path} resolves outside workspace root {self.root}") from exc

        lexical = Path(os.path.abspath(str(candidate)))
        try:
            relative = lexical.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceError(f"managed path {path} is outside workspace root {self.root}") from exc
        cursor = self.root
        for part in relative.parts:
            cursor /= part
            if is_managed_link(cursor):
                raise WorkspaceError(f"managed path {path} must not contain symlinks")

    def _managed_file_scan(self) -> tuple[list[Path], list[Issue]]:
        paths: list[Path] = []
        issues: list[Issue] = []
        for directory in MANAGED_DIRS:
            base = self.root / directory
            if not base.exists() and not is_managed_link(base):
                continue
            if is_managed_link(base):
                issues.append(Issue(base, "managed directory must not be a symlink"))
                continue
            if not base.is_dir():
                issues.append(Issue(base, "managed path must be a directory"))
                continue
            for current, directories, files in os.walk(base, topdown=True, followlinks=False):
                current_path = Path(current)
                for name in sorted(tuple(directories)):
                    path = current_path / name
                    if is_managed_link(path):
                        issues.append(Issue(path, "managed directory must not be a symlink"))
                        directories.remove(name)
                for name in sorted(files):
                    path = current_path / name
                    if is_managed_link(path):
                        issues.append(Issue(path, "managed file must not be a symlink"))
                        continue
                    if path.suffix.lower() in {".md", ".markdown"} and path != base / "README.md":
                        try:
                            self.assert_safe_path(path)
                        except WorkspaceError as exc:
                            issues.append(Issue(path, str(exc)))
                            continue
                        paths.append(path)
        return sorted(paths, key=lambda path: path.as_posix()), issues

    def managed_files(self) -> Iterable[Path]:
        paths, issues = self._managed_file_scan()
        if issues:
            issue = sorted(issues, key=lambda item: (str(item.path), item.message))[0]
            raise WorkspaceError(f"{issue.path}: {issue.message}")
        return paths


def _load_config(marker: Path) -> dict[str, object]:
    try:
        config = tomllib.loads(marker.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise WorkspaceError("knowledge-os.toml must be UTF-8 text") from exc
    except tomllib.TOMLDecodeError as exc:
        raise WorkspaceError(f"invalid knowledge-os.toml: {exc}") from exc
    workspace_config = config.get("workspace")
    if not isinstance(workspace_config, dict):
        raise WorkspaceError("knowledge-os.toml requires a [workspace] table")
    version = workspace_config.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise WorkspaceError("knowledge-os.toml requires [workspace].version = 1")
    if version != 1:
        raise WorkspaceError(f"unsupported workspace version {version}; supported version is 1")
    return config


def workspace_identity(workspace: Workspace) -> dict[str, object]:
    """Return the stable, clone-safe identity embedded in generated artifacts."""

    config = workspace.config.get("workspace", {})
    marker = workspace.root / "knowledge-os.toml"
    return {
        "name": config.get("name") if isinstance(config, dict) else None,
        "schema_version": config.get("version") if isinstance(config, dict) else None,
        "marker_sha256": hashlib.sha256(marker.read_bytes()).hexdigest(),
    }


def validate_workspace(workspace: Workspace) -> tuple[list[Document], list[Issue]]:
    documents: list[Document] = []
    issues: list[Issue] = []
    ids: dict[str, Path] = {}
    paths, path_issues = workspace._managed_file_scan()
    issues.extend(path_issues)
    indexes = workspace.root / "indexes"
    if is_managed_link(indexes):
        issues.append(Issue(indexes, "managed index directory must not be a symlink"))
    elif indexes.exists() and not indexes.is_dir():
        issues.append(Issue(indexes, "managed index path must be a directory"))

    for path in paths:
        relative_path = path.relative_to(workspace.root)
        expected_type = MANAGED_DIRS[relative_path.parts[0]]
        is_project_root_file = (
            expected_type == "project"
            and len(relative_path.parts) >= 3
            and path.name == PROJECT_ROOT_FILE
        )
        try:
            document = parse_document(path, check_filename=not is_project_root_file)
        except MetadataError as exc:
            issues.append(Issue(path, str(exc)))
            continue
        if document.metadata["type"] != expected_type:
            issues.append(Issue(path, f"type {document.metadata['type']!r} does not match directory ({expected_type!r})"))
        if document.metadata["type"] == "project":
            _validate_project_path(workspace, document, issues)
        record_id = document.metadata["id"]
        if record_id in ids:
            issues.append(Issue(path, f"duplicate id {record_id!r}; already defined at {workspace.relative(ids[record_id])}"))
        else:
            ids[record_id] = path
        documents.append(document)

    from .skills import load_skills

    _, skill_issues = load_skills(workspace.root)
    issues.extend(Issue(path, message) for path, message in skill_issues)

    documents_by_id = {document.metadata["id"]: document for document in documents}
    _validate_project_overviews(documents, issues)
    for document in documents:
        metadata = document.metadata
        record_id = metadata["id"]
        for field in RELATION_FIELDS:
            for target in metadata.get(field, []):
                if target == record_id and field == "sources":
                    issues.append(Issue(document.path, "self-source relationship is not allowed: sources contains its own id"))
                if target == record_id and field == "supersedes":
                    issues.append(Issue(document.path, "self-supersedes relationship is not allowed: supersedes contains its own id"))
                if target not in ids:
                    issues.append(Issue(document.path, f"unresolved relationship id {target!r} in {field}"))

        for index, provenance in enumerate(metadata["provenance"]):
            kind = provenance["kind"]
            reference = provenance["reference"]
            if kind not in CANONICAL_PROVENANCE_KINDS:
                continue
            target = documents_by_id.get(reference) if ID_PATTERN.fullmatch(reference) else None
            if target is None:
                issues.append(
                    Issue(
                        document.path,
                        f"unresolved canonical provenance {kind!r} reference {reference!r} in provenance[{index}]",
                    )
                )
            elif kind == "discovery" and target.metadata["type"] != "discovery":
                issues.append(
                    Issue(
                        document.path,
                        f"canonical provenance discovery reference {reference!r} must point to a discovery record",
                    )
                )

        if metadata["type"] == "discovery":
            for index, evidence in enumerate(metadata["evidence"]):
                if evidence["kind"] == "record" and evidence["reference"] not in ids:
                    issues.append(
                        Issue(
                            document.path,
                            f"unresolved evidence record id {evidence['reference']!r} in evidence[{index}]",
                        )
                    )

        if metadata["type"] == "discovery" and metadata["status"] == "promoted":
            _validate_promoted_discovery(document, documents_by_id, issues)

    _validate_discovery_provenance_lineage(documents, documents_by_id, issues)
    _validate_supersession_cycles(documents, documents_by_id, issues)
    _validate_decision_supersession(documents, documents_by_id, issues)

    return sorted(documents, key=lambda item: item.metadata["id"]), sorted(
        issues,
        key=lambda item: (str(item.path), item.message),
    )


def _validate_project_overviews(documents: list[Document], issues: list[Issue]) -> None:
    """Require one usable exact overview for every project scope in the corpus."""

    project_scopes = sorted(
        {document.metadata["scope"] for document in documents if document.metadata["scope"].startswith("project:")}
    )
    for scope in project_scopes:
        project_id = scope.removeprefix("project:")
        exact = [
            document
            for document in documents
            if document.metadata["type"] == "project"
            and document.metadata["id"] == project_id
            and document.metadata["scope"] == scope
        ]
        scope_documents = [document for document in documents if document.metadata["scope"] == scope]
        anchor = exact[0].path if exact else scope_documents[0].path
        if len(exact) != 1:
            issues.append(
                Issue(
                    anchor,
                    f"project scope {scope!r} requires exactly one valid project overview with "
                    f"type 'project', id {project_id!r}, and scope {scope!r}",
                )
            )
            continue
        if exact[0].metadata["status"] not in {"draft", "active"}:
            issues.append(
                Issue(
                    exact[0].path,
                    f"project overview {project_id!r} for scope {scope!r} is not usable; "
                    "status must be draft or active",
                )
            )


def project_directory(scope: str) -> Path:
    """Return the canonical project directory for a project scope."""

    return Path("projects") / scope.removeprefix("project:")


def default_project_record_path(record_id: str, scope: str) -> Path:
    """Return the default canonical path for a project record."""

    directory = project_directory(scope)
    if record_id == scope.removeprefix("project:"):
        return directory / PROJECT_ROOT_FILE
    return directory / f"{record_id}.md"


def _validate_project_path(workspace: Workspace, document: Document, issues: list[Issue]) -> None:
    """Keep every project record inside the directory named by its scope."""

    metadata = document.metadata
    project_id = metadata["scope"].removeprefix("project:")
    relative = document.path.relative_to(workspace.root)
    expected_directory = Path("projects") / project_id
    try:
        relative.relative_to(expected_directory)
    except ValueError:
        issues.append(
            Issue(
                document.path,
                f"project record with scope {metadata['scope']!r} must be inside "
                f"{expected_directory.as_posix()}/",
            )
        )
        return

    if metadata["id"] == project_id:
        expected = expected_directory / PROJECT_ROOT_FILE
        if relative != expected:
            issues.append(
                Issue(
                    document.path,
                    f"project overview {project_id!r} must be {expected.as_posix()}",
                )
            )


def _validate_promoted_discovery(
    discovery: Document,
    documents_by_id: dict[str, Document],
    issues: list[Issue],
) -> None:
    metadata = discovery.metadata
    target_id = metadata["reviews"][-1]["target"]
    if target_id == metadata["id"]:
        issues.append(Issue(discovery.path, "promoted discovery target must not reference itself"))
        return
    target = documents_by_id.get(target_id)
    if target is None:
        issues.append(Issue(discovery.path, f"promoted discovery target {target_id!r} does not exist"))
        return

    target_metadata = target.metadata
    target_scope = target_metadata["scope"]
    expected_type = "knowledge" if target_scope == "general" else "project"
    if target_metadata["type"] != expected_type:
        issues.append(
            Issue(
                discovery.path,
                f"promoted discovery target {target_id!r} with scope {target_scope!r} must have type {expected_type!r}",
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
                discovery.path,
                f"project-scoped promoted discovery cannot target different project scope {target_scope!r}",
            )
        )
    if metadata["id"] in target_metadata.get("sources", []):
        issues.append(
            Issue(
                target.path,
                f"redundant legacy promotion lineage: target {target_id!r} must not list promoted "
                f"discovery {metadata['id']!r} in sources; use target provenance only",
            )
        )
    if target_id in metadata.get("related", []):
        issues.append(
            Issue(
                discovery.path,
                f"redundant legacy promotion lineage: promoted discovery {metadata['id']!r} must not "
                f"list review target {target_id!r} in related; use the promote review target only",
            )
        )
    if not any(
        item.get("kind") == "discovery" and item.get("reference") == metadata["id"]
        for item in target_metadata["provenance"]
    ):
        issues.append(
            Issue(
                discovery.path,
                f"promotion target {target_id!r} provenance must include discovery reference {metadata['id']!r}",
            )
        )


def _validate_discovery_provenance_lineage(
    documents: list[Document],
    documents_by_id: dict[str, Document],
    issues: list[Issue],
) -> None:
    for document in documents:
        if document.metadata["type"] not in {"knowledge", "project"}:
            continue
        for provenance in document.metadata["provenance"]:
            if provenance["kind"] != "discovery":
                continue
            discovery = documents_by_id.get(provenance["reference"])
            if discovery is None or discovery.metadata["type"] != "discovery":
                continue
            if discovery.metadata["status"] != "promoted":
                issues.append(
                    Issue(
                        document.path,
                        f"discovery provenance {discovery.metadata['id']!r} targets {document.metadata['id']!r} "
                        f"but discovery status is {discovery.metadata['status']!r}, expected promoted",
                    )
                )
                continue
            target = discovery.metadata["reviews"][-1].get("target")
            if target != document.metadata["id"]:
                issues.append(
                    Issue(
                        document.path,
                        f"discovery provenance {discovery.metadata['id']!r} disagrees with promote review target {target!r}",
                    )
                )


def _validate_supersession_cycles(
    documents: list[Document],
    documents_by_id: dict[str, Document],
    issues: list[Issue],
) -> None:
    graph = {
        document.metadata["id"]: sorted(
            target
            for target in document.metadata.get("supersedes", [])
            if target in documents_by_id and target != document.metadata["id"]
        )
        for document in documents
    }
    state: dict[str, int] = {}
    reported: set[tuple[str, ...]] = set()

    def visit(record_id: str, stack: list[str]) -> None:
        state[record_id] = 1
        stack.append(record_id)
        for target in graph[record_id]:
            if state.get(target) == 1:
                cycle = tuple(stack[stack.index(target) :] + [target])
                signature = tuple(sorted(set(cycle)))
                if signature not in reported:
                    reported.add(signature)
                    issues.append(
                        Issue(
                            documents_by_id[record_id].path,
                            f"supersedes cycle detected: {' -> '.join(cycle)}",
                        )
                    )
            elif state.get(target, 0) == 0:
                visit(target, stack)
        stack.pop()
        state[record_id] = 2

    for record_id in sorted(graph):
        if state.get(record_id, 0) == 0:
            visit(record_id, [])


def _validate_decision_supersession(
    documents: list[Document],
    documents_by_id: dict[str, Document],
    issues: list[Issue],
) -> None:
    """Keep proposed and effective decision replacement states distinct."""

    decisions = [document for document in documents if document.metadata.get("record_kind") == "decision"]
    incoming: dict[str, list[Document]] = {}
    for document in decisions:
        targets = document.metadata.get("supersedes", [])
        if len(targets) > 1:
            issues.append(Issue(document.path, "decision records may supersede exactly one prior decision"))
        for target_id in targets:
            incoming.setdefault(target_id, []).append(document)
            target = documents_by_id.get(target_id)
            if target is None:
                continue
            if target.metadata.get("record_kind") != "decision":
                issues.append(Issue(document.path, f"decision supersedes target {target_id!r} must be a decision"))
                continue
            if target.metadata["scope"] != document.metadata["scope"]:
                issues.append(Issue(document.path, f"decision supersedes target {target_id!r} must use the same scope"))
            if document.metadata["status"] == "draft" and target.metadata["status"] != "active":
                issues.append(
                    Issue(
                        document.path,
                        f"draft replacement {document.metadata['id']!r} must target an active decision; "
                        f"{target_id!r} is {target.metadata['status']!r}",
                    )
                )
            if document.metadata["status"] in {"active", "superseded"} and target.metadata["status"] != "superseded":
                issues.append(
                    Issue(
                        document.path,
                        f"effective replacement {document.metadata['id']!r} requires superseded target "
                        f"{target_id!r}; found {target.metadata['status']!r}",
                    )
                )

    for document in decisions:
        if document.metadata["status"] != "superseded":
            continue
        effective = [
            replacement
            for replacement in incoming.get(document.metadata["id"], [])
            if replacement.metadata["status"] in {"active", "superseded"}
        ]
        if len(effective) != 1:
            ids = ", ".join(sorted(item.metadata["id"] for item in effective)) or "none"
            issues.append(
                Issue(
                    document.path,
                    f"superseded decision {document.metadata['id']!r} requires exactly one effective "
                    f"replacement; found {ids}",
                )
            )


@contextmanager
def workspace_mutation_lock(workspace: Workspace) -> Iterator[None]:
    """Serialize cooperating mutations for one workspace across processes."""

    identity = str(workspace.root).casefold() if os.name == "nt" else str(workspace.root)
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    lock_path = Path(tempfile.gettempdir()) / f"knowledge-os-workspace-{digest}.lock"
    handle = lock_path.open("a+b")
    locked = False
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError as exc:
            raise WorkspaceError(f"could not acquire workspace mutation lock for {workspace.root}: {exc}") from exc
        locked = True
        yield
    finally:
        if locked:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


@contextmanager
def stage_workspace(workspace: Workspace) -> Iterator[Workspace]:
    """Create a disposable candidate workspace for intended-state validation."""

    temporary = tempfile.TemporaryDirectory(prefix="kos-stage-", dir=workspace.root.parent)
    stage_root = Path(temporary.name)
    try:
        shutil.copy2(workspace.root / "knowledge-os.toml", stage_root / "knowledge-os.toml")
        for directory in (*MANAGED_DIRS, "skills"):
            source = workspace.root / directory
            destination = stage_root / directory
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=True)
            else:
                destination.mkdir(parents=True)
        yield Workspace(stage_root)
    finally:
        temporary.cleanup()


def atomic_write(path: Path, content: bytes) -> None:
    """Atomically replace one file in the canonical or staged workspace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def exclusive_write(path: Path, content: bytes) -> None:
    """Create one file without replacing a path created by another writer."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def staged_documents(workspace: Workspace, operation: str) -> list[Document]:
    """Validate a disposable intended-state workspace before live writes."""

    documents, issues = validate_workspace(workspace)
    if issues:
        details = "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
        relative: list[tuple[str, str]] = []
        for issue in issues:
            try:
                location = workspace.relative(issue.path)
            except WorkspaceError:
                location = str(issue.path)
            relative.append((location, issue.message))
        raise CorpusValidationError(
            f"resulting corpus is invalid while attempting to {operation}:\n{details}",
            tuple(relative),
        )
    return documents


def refresh_derived_indexes(workspace: Workspace) -> int:
    """Rebuild disposable indexes after canonical writes without rollback."""

    from .index import _rebuild_indexes_locked

    try:
        return _rebuild_indexes_locked(workspace)
    except Exception as exc:
        raise WorkspaceError(
            "canonical corpus is authoritative, but derived indexes could not be rebuilt; "
            "run 'kos lint' and then 'kos index' to recover: "
            f"{exc}"
        ) from exc
