"""Create projects and folders; move and rename pages and folders.

Creating a project writes its required overview ``projects/<id>/README.md``,
and creating a folder writes the folder's ``README.md`` root record, both
through ``capture``'s create-only path. A folder therefore always exists as a
real, lintable page that Git tracks, even before anything else is filed in
it.

Moves keep every record ID (and so every filename). Renaming a page changes
its title only, since its filename is its ID; renaming a folder changes the
directory name and, when the folder has a ``README.md``, that page's title.
Every relative Markdown link in another record (and in the moved files
themselves) that pointed at a moved file is rewritten so it still resolves
(see ``links.py``); raw sources are never rewritten.

Moving a page or folder to another project changes each moved record's
``scope`` and is refused unless the caller confirms the scope change. A
decision whose ``supersedes`` lineage would cross project scopes is refused
outright, and anything else ``kos lint`` would reject is refused by staged
whole-corpus validation.

Each move holds the workspace mutation lock, reads every file it will change
under that lock, applies all changes to a disposable staged copy, validates
the staged corpus, and only then touches the canonical workspace. A caught
failure while writing restores every file and directory it had changed. As
with supersession this is not crash-atomic: if the process stops midway,
``kos lint`` reports the partial state; repair it, then run ``kos lint`` and
``kos index``.
"""

from __future__ import annotations

import os
import posixpath
import re
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .capture import CaptureIndexError, DuplicateRecordError, capture_record_text
from .links import rewrite_links
from .model import ID_PATTERN, SHA256_PATTERN, Document, MetadataError, content_sha256, parse_document_text, render_document
from .mutations import (
    MutationError,
    MutationIndexError,
    RecordNotFoundError,
    StaleRevisionError,
    update_record_text,
)
from .workspace import (
    PROJECT_ROOT_FILE,
    Workspace,
    WorkspaceError,
    atomic_write,
    exclusive_write,
    refresh_derived_indexes,
    stage_workspace,
    staged_documents,
    validate_workspace,
    workspace_mutation_lock,
)

#: Record types whose bodies are never rewritten: raw material stays exactly
#: as it was ingested.
UNREWRITTEN_TYPES = frozenset({"source"})


class StructureError(MutationError):
    """A user-actionable refusal of a structure change; nothing was written."""


class StructureIndexError(StructureError):
    """Every canonical change was written, but the derived indexes were not rebuilt.

    ``result`` describes what was written (its ``index_count`` is 0).
    """

    def __init__(self, message: str, result: "StructureResult"):
        super().__init__(message)
        self.result = result


@dataclass(frozen=True)
class ChangedFile:
    """One file a structure change created, moved, or rewrote."""

    old_path: str | None  # None for a created file
    path: str
    id: str | None  # None for a file that is not a record (an image in a moved folder)
    sha256: str


@dataclass(frozen=True)
class StructureResult:
    """What a structure change did.

    ``id``/``title``/``path``/``sha256`` describe the main record: the created
    overview or folder page, the moved or renamed page, or a moved folder's
    ``README.md`` (all ``None`` except ``path`` for a folder without one, where
    ``path`` is the folder). ``project`` and ``folder`` say where it now is.
    ``touched`` lists every workspace-relative file path that was created,
    changed, or removed, for the Git commit.
    """

    id: str | None
    title: str | None
    status: str | None
    path: str
    sha256: str | None
    project: str
    folder: str
    changed: tuple[ChangedFile, ...]
    touched: tuple[str, ...]
    scope_changed: bool = False
    index_count: int = 0


def cli_provenance(action: str) -> dict[str, str]:
    """Provenance for a record created with the ``kos`` command line."""

    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return {"kind": "cli-authored", "reference": f"cli:{stamp}:{action}", "captured": stamp}


def clean_folder(value: str | None) -> str:
    """A safe folder path relative to a project directory; ``""`` is the project's top level."""

    if value is None:
        return ""
    text = value.replace("\\", "/").strip().strip("/")
    if text in {"", "."}:
        return ""
    parts = text.split("/")
    for part in parts:
        if part in {"", ".", ".."} or part != part.strip() or ":" in part:
            raise StructureError(f"folder {value!r} must be a safe relative path inside the project")
    return "/".join(parts)


def _folder_name(name: str) -> str:
    cleaned = name.strip()
    if not ID_PATTERN.fullmatch(cleaned):
        raise StructureError(
            f"folder name {name!r} must be lowercase letters and digits joined by hyphens, like 'meeting-notes'"
        )
    return cleaned


def _title(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StructureError("title must be a non-empty string")
    return value.strip()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _today_after(value: object) -> str:
    current = value if isinstance(value, date) else date.fromisoformat(str(value))
    return max(datetime.now(UTC).date(), current).isoformat()


def _documents(workspace: Workspace, operation: str) -> tuple[list[Document], dict[str, Document]]:
    documents, issues = validate_workspace(workspace)
    if issues:
        details = "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise StructureError(f"cannot {operation} in an invalid corpus:\n{details}")
    return documents, {document.metadata["id"]: document for document in documents}


def _require_project(by_id: Mapping[str, Document], project_id: str) -> Document:
    overview = by_id.get(project_id)
    if (
        overview is None
        or overview.metadata["type"] != "project"
        or overview.metadata["scope"] != f"project:{project_id}"
    ):
        raise RecordNotFoundError(f"project not found: {project_id}")
    return overview


def _check_hash(path: Path, expected: str, label: str) -> None:
    if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
        raise StructureError(f"expected sha256 for {label} must be 64 lowercase hex characters")
    actual = content_sha256(path)
    if actual != expected:
        raise StaleRevisionError(
            f"conflict for {label}: expected sha256 {expected}, found {actual}; "
            "the file changed after it was read, so nothing was written",
            expected=expected,
            actual=actual,
        )


def _check_expected(workspace: Workspace, expected: Mapping[str, str] | None) -> None:
    """Optional extra preconditions: ``{workspace-relative path: sha256}`` the caller read."""

    for relative, digest in sorted((expected or {}).items()):
        path = workspace.root / relative
        workspace.assert_safe_path(path)
        if not path.is_file():
            raise RecordNotFoundError(f"file not found: {relative}")
        _check_hash(path, digest, relative)


def _split_frontmatter(text: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            return "".join(lines[: index + 1]), "".join(lines[index + 1 :])
    return "", text


def _with_metadata(content: bytes, changes: Mapping[str, Any]) -> bytes:
    document = parse_document_text(Path("record.md"), content.decode("utf-8"), check_filename=False)
    metadata = deepcopy(document.metadata)
    metadata.update(changes)
    metadata["updated"] = _today_after(metadata["updated"])
    return render_document(metadata, document.body)


def _link_rewrites(
    workspace: Workspace,
    documents: list[Document],
    relocate: Callable[[str], str | None],
) -> dict[str, bytes]:
    """New bytes for every record whose links change, keyed by its final path."""

    rewrites: dict[str, bytes] = {}
    for document in documents:
        if document.metadata["type"] in UNREWRITTEN_TYPES:
            continue
        old_path = workspace.relative(document.path)
        new_path = relocate(old_path) or old_path
        text = document.path.read_bytes().decode("utf-8")
        front, body = _split_frontmatter(text)
        new_body = rewrite_links(body, old_path, new_path, relocate)
        if new_body != body:
            rewrites[new_path] = (front + new_body).encode("utf-8")
    return rewrites


def _check_scope_change(
    moved: list[Document],
    documents: list[Document],
    *,
    allow: bool,
    source_project: str,
    target_project: str,
    what: str,
) -> None:
    if not allow:
        raise StructureError(
            f"moving {what} to project {target_project!r} changes its scope from 'project:{source_project}' "
            f"to 'project:{target_project}'; confirm the scope change to move it"
        )
    moved_ids = {document.metadata["id"] for document in moved}
    for document in moved:
        if document.metadata.get("record_kind") != "decision":
            continue
        record_id = document.metadata["id"]
        partners = set(document.metadata.get("supersedes", []))
        partners |= {
            other.metadata["id"] for other in documents if record_id in other.metadata.get("supersedes", [])
        }
        outside = sorted(partners - moved_ids)
        if outside:
            raise StructureError(
                f"decision {record_id!r} is linked through supersedes to {', '.join(outside)}, which stays in "
                f"project {source_project!r}; a decision's replacement lineage cannot cross project scopes"
            )


# ---------------------------------------------------------------------------
# Applying a planned change: staged first, then canonical with an undo log
# ---------------------------------------------------------------------------


@dataclass
class _Plan:
    directory_move: tuple[str, str] | None = None  # (old directory, new directory)
    file_moves: list[tuple[str, str]] = field(default_factory=list)  # (old path, new path)
    writes: dict[str, bytes] = field(default_factory=dict)  # final path -> bytes
    prune: list[tuple[str, str]] = field(default_factory=list)  # (directory, stop): remove while empty


def _make_parents(root: Path, relative: str, journal: list[tuple[Any, ...]]) -> None:
    missing: list[str] = []
    current = posixpath.dirname(relative)
    while current and not (root / current).exists():
        missing.append(current)
        current = posixpath.dirname(current)
    for directory in reversed(missing):
        (root / directory).mkdir()
        journal.append(("mkdir", directory))


def _apply(root: Path, plan: _Plan, journal: list[tuple[Any, ...]]) -> None:
    moved_to: set[str] = set()
    if plan.directory_move is not None:
        old, new = plan.directory_move
        _make_parents(root, new, journal)
        os.rename(root / old, root / new)
        journal.append(("rename", old, new))
    for old, new in plan.file_moves:
        _make_parents(root, new, journal)
        exclusive_write(root / new, plan.writes[new])
        journal.append(("created", new))
        original = (root / old).read_bytes()
        (root / old).unlink()
        journal.append(("removed", old, original))
        moved_to.add(new)
    for relative, content in plan.writes.items():
        if relative in moved_to:
            continue
        original = (root / relative).read_bytes()
        atomic_write(root / relative, content)
        journal.append(("replaced", relative, original))
    for directory, stop in plan.prune:
        current = directory
        while current.startswith(stop + "/"):
            path = root / current
            if not path.is_dir() or any(path.iterdir()):
                break
            path.rmdir()
            journal.append(("rmdir", current))
            current = posixpath.dirname(current)


def _undo(root: Path, journal: list[tuple[Any, ...]]) -> list[str]:
    errors: list[str] = []
    for entry in reversed(journal):
        kind, relative = entry[0], entry[1]
        try:
            if kind in {"replaced", "removed"}:
                atomic_write(root / relative, entry[2])
            elif kind == "created":
                (root / relative).unlink(missing_ok=True)
            elif kind == "rename":
                os.rename(root / entry[2], root / relative)
            elif kind == "mkdir":
                (root / relative).rmdir()
            elif kind == "rmdir":
                (root / relative).mkdir(exist_ok=True)
        except OSError as exc:
            errors.append(f"{relative}: {exc}")
    return errors


def _execute(workspace: Workspace, plan: _Plan, operation: str) -> None:
    with stage_workspace(workspace) as stage:
        _apply(stage.root, plan, [])
        staged_documents(stage, operation)

    journal: list[tuple[Any, ...]] = []
    try:
        _apply(workspace.root, plan, journal)
    except Exception as exc:  # restore on any caught failure, then report it
        errors = _undo(workspace.root, journal)
        if errors:
            raise StructureError(
                f"could not {operation}, and restoring the previous files was incomplete: "
                + "; ".join(errors)
                + "; inspect these paths, repair canonical Markdown, then run 'kos lint' and 'kos index'"
            ) from exc
        raise StructureError(f"could not {operation}; every file was restored: {exc}") from exc


def _finish(workspace: Workspace, result: StructureResult) -> StructureResult:
    try:
        count = refresh_derived_indexes(workspace)
    except WorkspaceError as exc:
        raise StructureIndexError(str(exc), result) from exc
    return replace(result, index_count=count)


def _record_id_at(path: Path) -> str | None:
    if path.suffix.lower() not in {".md", ".markdown"}:
        return None
    try:
        return parse_document_text(path, path.read_text(encoding="utf-8"), check_filename=False).metadata["id"]
    except (MetadataError, OSError, UnicodeDecodeError):
        return None


def _folder_of(workspace_path: str, project_id: str) -> str:
    prefix = f"projects/{project_id}/"
    return posixpath.dirname(workspace_path[len(prefix) :]) if workspace_path.startswith(prefix) else ""


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def _created(workspace: Workspace, capture: Callable[[], Any], project_id: str, folder: str) -> StructureResult:
    try:
        captured = capture()
    except CaptureIndexError as exc:
        written = exc.result
        result = _created_result(written, project_id, folder)
        raise StructureIndexError(str(exc), result) from exc
    return replace(_created_result(captured, project_id, folder), index_count=captured.index_count)


def _created_result(captured: Any, project_id: str, folder: str) -> StructureResult:
    return StructureResult(
        id=captured.id,
        title=None,
        status=captured.status,
        path=captured.path,
        sha256=captured.sha256,
        project=project_id,
        folder=folder,
        changed=(ChangedFile(None, captured.path, captured.id, captured.sha256),),
        touched=(captured.path,),
    )


def create_project(
    workspace: Workspace,
    project_id: str,
    *,
    title: str,
    provenance: list[dict[str, Any]],
    body: str | None = None,
) -> StructureResult:
    """Create ``projects/<project_id>/README.md``, the new project's overview (status ``active``)."""

    if not isinstance(project_id, str) or not ID_PATTERN.fullmatch(project_id):
        raise StructureError(
            f"project id {project_id!r} must be lowercase letters and digits joined by hyphens, like 'my-project'"
        )
    title = _title(title)
    if (workspace.root / "projects" / project_id).exists():
        raise DuplicateRecordError(f"destination projects/{project_id}/ already exists; refusing overwrite")
    metadata = {
        "id": project_id,
        "title": title,
        "type": "project",
        "status": "active",
        "scope": f"project:{project_id}",
        "created": _today(),
        "updated": _today(),
        "provenance": provenance,
    }
    text = render_document(metadata, body if body and body.strip() else f"# {title}\n").decode("utf-8")
    result = _created(workspace, lambda: capture_record_text(workspace, text), project_id, "")
    return replace(result, title=title)


def _default_folder_id(project_id: str, folder: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{project_id}-{folder}".lower()).strip("-")
    candidate, suffix = base, 2
    while candidate in taken:
        candidate, suffix = f"{base}-{suffix}", suffix + 1
    return candidate


def create_folder(
    workspace: Workspace,
    project_id: str,
    folder: str,
    *,
    title: str,
    provenance: list[dict[str, Any]],
    record_id: str | None = None,
    body: str | None = None,
) -> StructureResult:
    """Create a folder in a project, as the folder's ``README.md`` page.

    ``folder`` is the new folder's path inside the project; its parent must
    already exist and its last part must be a lowercase kebab-case name. The
    page ID defaults to ``<project>-<folder path joined by hyphens>``.
    """

    folder = clean_folder(folder)
    if not folder:
        raise StructureError("name the new folder, for example 'meeting-notes'")
    parent, name = posixpath.split(folder)
    _folder_name(name)
    title = _title(title)
    # Checked before capture takes the workspace lock; capture repeats the
    # ID and destination checks under the lock.
    documents, by_id = _documents(workspace, "create a folder")
    _require_project(by_id, project_id)
    directory = workspace.root / "projects" / project_id / folder
    workspace.assert_safe_path(directory)
    if directory.exists():
        raise DuplicateRecordError(f"folder {folder!r} already exists in project {project_id!r}")
    if parent and not (workspace.root / "projects" / project_id / parent).is_dir():
        raise RecordNotFoundError(f"folder not found: {parent} in project {project_id}")
    record_id = record_id or _default_folder_id(project_id, folder, set(by_id))
    metadata = {
        "id": record_id,
        "title": title,
        "type": "project",
        "status": "active",
        "scope": f"project:{project_id}",
        "created": _today(),
        "updated": _today(),
        "provenance": provenance,
    }
    text = render_document(metadata, body if body and body.strip() else f"# {title}\n").decode("utf-8")
    result = _created(
        workspace,
        lambda: capture_record_text(workspace, text, project_path=Path(folder) / PROJECT_ROOT_FILE),
        project_id,
        folder,
    )
    return replace(result, title=title)


# ---------------------------------------------------------------------------
# Rename a page
# ---------------------------------------------------------------------------


def rename_record(workspace: Workspace, record_id: str, *, expected_sha256: str, title: str) -> StructureResult:
    """Change one record's title with ``kos update``'s rules; its ID and file stay the same."""

    title = _title(title)
    documents, by_id = _documents(workspace, "rename a page")
    current = by_id.get(record_id)
    if current is None:
        raise RecordNotFoundError(f"record not found: {record_id}")
    raw = current.path.read_bytes()
    _check_hash(current.path, expected_sha256, current.path.name)
    document = parse_document_text(current.path, raw.decode("utf-8"), check_filename=False)
    metadata = deepcopy(document.metadata)
    metadata["title"] = title
    metadata["updated"] = _today_after(metadata["updated"])
    text = render_document(metadata, document.body).decode("utf-8")
    scope = metadata["scope"]
    project_id = scope.removeprefix("project:") if scope.startswith("project:") else ""
    relative = workspace.relative(current.path)

    def result_for(written: Any) -> StructureResult:
        return StructureResult(
            id=written.id,
            title=title,
            status=written.status,
            path=written.path,
            sha256=written.sha256,
            project=project_id,
            folder=_folder_of(relative, project_id),
            changed=(ChangedFile(written.path, written.path, written.id, written.sha256),),
            touched=(written.path,),
        )

    try:
        written = update_record_text(workspace, text, expected_sha256=expected_sha256)
    except MutationIndexError as exc:
        raise StructureIndexError(str(exc), result_for(exc.result)) from exc
    return replace(result_for(written), index_count=written.index_count)


# ---------------------------------------------------------------------------
# Move a page
# ---------------------------------------------------------------------------


def move_record(
    workspace: Workspace,
    record_id: str,
    *,
    expected_sha256: str,
    folder: str | None = "",
    project: str | None = None,
    allow_scope_change: bool = False,
    expected: Mapping[str, str] | None = None,
) -> StructureResult:
    """Move one project page to ``folder`` (``""`` is the top level) of ``project``.

    ``project`` defaults to the page's own project; another project changes
    the page's scope and needs ``allow_scope_change``. The target folder must
    exist. The page keeps its ID and filename.
    """

    folder = clean_folder(folder)
    with workspace_mutation_lock(workspace):
        documents, by_id = _documents(workspace, "move a page")
        current = by_id.get(record_id)
        if current is None:
            raise RecordNotFoundError(f"record not found: {record_id}")
        _check_hash(current.path, expected_sha256, current.path.name)
        if current.metadata["type"] != "project":
            raise StructureError(
                f"only project pages can be moved between project folders; {record_id!r} is a "
                f"{current.metadata['type']!r} record"
            )
        source_project = current.metadata["scope"].removeprefix("project:")
        if record_id == source_project:
            raise StructureError(
                f"{record_id!r} is the project overview and must stay at projects/{source_project}/README.md"
            )
        if current.path.name == PROJECT_ROOT_FILE:
            raise StructureError(f"{record_id!r} is a folder's own page; move the folder instead")
        target_project = project or source_project
        _require_project(by_id, target_project)
        target_directory = f"projects/{target_project}/{folder}" if folder else f"projects/{target_project}"
        workspace.assert_safe_path(workspace.root / target_directory)
        if not (workspace.root / target_directory).is_dir():
            raise RecordNotFoundError(f"folder not found: {folder} in project {target_project}")
        old_path = workspace.relative(current.path)
        new_path = f"{target_directory}/{current.path.name}"
        if new_path == old_path:
            raise StructureError(f"{record_id!r} is already in that folder; nothing was moved")
        destination = workspace.root / new_path
        if destination.exists() or destination.is_symlink():
            raise DuplicateRecordError(f"destination {new_path} already exists; refusing overwrite")
        scope_changed = target_project != source_project
        if scope_changed:
            _check_scope_change(
                [current],
                documents,
                allow=allow_scope_change,
                source_project=source_project,
                target_project=target_project,
                what=f"page {record_id!r}",
            )
        _check_expected(workspace, expected)

        def relocate(target: str) -> str | None:
            return new_path if target == old_path else None

        writes = _link_rewrites(workspace, documents, relocate)
        content = writes.get(new_path, current.path.read_bytes())
        if scope_changed:
            content = _with_metadata(content, {"scope": f"project:{target_project}"})
        writes[new_path] = content
        plan = _Plan(
            file_moves=[(old_path, new_path)],
            writes=writes,
            prune=[(posixpath.dirname(old_path), f"projects/{source_project}")],
        )
        _execute(workspace, plan, "move a page")

        by_path = {workspace.relative(document.path): document.metadata["id"] for document in documents}
        changed = tuple(
            ChangedFile(
                old_path if path == new_path else path,
                path,
                record_id if path == new_path else by_path.get(path),
                content_sha256(workspace.root / path),
            )
            for path in sorted(writes)
        )
        result = StructureResult(
            id=record_id,
            title=current.metadata["title"],
            status=current.metadata["status"],
            path=new_path,
            sha256=content_sha256(destination),
            project=target_project,
            folder=folder,
            changed=changed,
            touched=tuple(sorted({old_path, *writes})),
            scope_changed=scope_changed,
        )
        return _finish(workspace, result)


# ---------------------------------------------------------------------------
# Move or rename a folder
# ---------------------------------------------------------------------------


def _files_below(root: Path, directory: str) -> list[str]:
    found: list[str] = []
    for current, _directories, files in os.walk(root / directory):
        for name in files:
            found.append((Path(current) / name).relative_to(root).as_posix())
    return sorted(found)


def move_folder(
    workspace: Workspace,
    project_id: str,
    folder: str,
    *,
    to_project: str | None = None,
    to_parent: str | None = None,
    name: str | None = None,
    title: str | None = None,
    allow_scope_change: bool = False,
    expected: Mapping[str, str] | None = None,
) -> StructureResult:
    """Move and/or rename one folder with everything in it.

    ``to_parent`` is the new parent folder (``""`` is the project's top
    level; ``None`` keeps the current parent), ``name`` the new directory
    name, and ``title`` the new title of the folder's ``README.md`` page when
    it has one. ``to_project`` moves it to another project, which changes the
    scope of every record in it and needs ``allow_scope_change``.
    """

    folder = clean_folder(folder)
    if not folder:
        raise StructureError("name a folder inside the project; a whole project cannot be moved")
    current_parent, current_name = posixpath.split(folder)
    parent = current_parent if to_parent is None else clean_folder(to_parent)
    new_name = current_name if name is None else _folder_name(name)
    new_title = None if title is None else _title(title)
    target_project = to_project or project_id
    new_folder = f"{parent}/{new_name}" if parent else new_name

    with workspace_mutation_lock(workspace):
        documents, by_id = _documents(workspace, "move a folder")
        _require_project(by_id, project_id)
        _require_project(by_id, target_project)
        old_directory = f"projects/{project_id}/{folder}"
        new_directory = f"projects/{target_project}/{new_folder}"
        workspace.assert_safe_path(workspace.root / old_directory)
        workspace.assert_safe_path(workspace.root / new_directory)
        if not (workspace.root / old_directory).is_dir():
            raise RecordNotFoundError(f"folder not found: {folder} in project {project_id}")
        if new_directory.startswith(old_directory + "/"):
            raise StructureError(f"folder {folder!r} cannot be moved into itself")
        if parent and not (workspace.root / "projects" / target_project / parent).is_dir():
            raise RecordNotFoundError(f"folder not found: {parent} in project {target_project}")
        moves = new_directory != old_directory
        if moves and (workspace.root / new_directory).exists():
            same = os.path.normcase(str(workspace.root / new_directory)) == os.path.normcase(
                str(workspace.root / old_directory)
            )
            if not same:
                raise DuplicateRecordError(f"destination {new_directory} already exists; refusing overwrite")

        readme_path = f"{old_directory}/{PROJECT_ROOT_FILE}"
        moved = [
            document
            for document in documents
            if workspace.relative(document.path).startswith(old_directory + "/")
        ]
        readme = next((document for document in moved if workspace.relative(document.path) == readme_path), None)
        retitle = new_title is not None and readme is not None and readme.metadata["title"] != new_title
        if not moves and not retitle:
            raise StructureError(f"folder {folder!r} already has that name and place; nothing was changed")
        scope_changed = target_project != project_id
        if scope_changed:
            _check_scope_change(
                moved,
                documents,
                allow=allow_scope_change,
                source_project=project_id,
                target_project=target_project,
                what=f"folder {folder!r}",
            )
        _check_expected(workspace, expected)

        def relocate(target: str) -> str | None:
            if not moves:
                return None
            if target == old_directory or target.startswith(old_directory + "/"):
                return new_directory + target[len(old_directory) :]
            return None

        writes = _link_rewrites(workspace, documents, relocate)
        for document in moved:
            old_path = workspace.relative(document.path)
            new_path = relocate(old_path) or old_path
            changes: dict[str, Any] = {}
            if scope_changed:
                changes["scope"] = f"project:{target_project}"
            if retitle and document is readme:
                changes["title"] = new_title
            if changes:
                content = writes.get(new_path, document.path.read_bytes())
                writes[new_path] = _with_metadata(content, changes)
        old_files = _files_below(workspace.root, old_directory)
        plan = _Plan(
            directory_move=(old_directory, new_directory) if moves else None,
            writes=writes,
            prune=[(posixpath.dirname(old_directory), f"projects/{project_id}")] if moves else [],
        )
        verb = "rename a folder" if moves and parent == current_parent and not scope_changed else "move a folder"
        _execute(workspace, plan, verb)

        by_path = {workspace.relative(document.path): document.metadata["id"] for document in documents}
        changed: list[ChangedFile] = []
        seen: set[str] = set()
        for old_path in old_files:
            new_path = relocate(old_path) or old_path
            if not moves and new_path not in writes:
                continue
            seen.add(new_path)
            changed.append(
                ChangedFile(
                    old_path,
                    new_path,
                    by_path.get(old_path) or _record_id_at(workspace.root / new_path),
                    content_sha256(workspace.root / new_path),
                )
            )
        for path in sorted(writes):
            if path not in seen:
                changed.append(ChangedFile(path, path, by_path.get(path), content_sha256(workspace.root / path)))
        touched = {*writes}
        if moves:
            touched |= set(old_files) | {relocate(path) or path for path in old_files}
        new_readme = f"{new_directory}/{PROJECT_ROOT_FILE}"
        result = StructureResult(
            id=readme.metadata["id"] if readme is not None else None,
            title=(new_title if retitle else readme.metadata["title"]) if readme is not None else None,
            status=readme.metadata["status"] if readme is not None else None,
            path=new_readme if readme is not None else new_directory,
            sha256=content_sha256(workspace.root / new_readme) if readme is not None else None,
            project=target_project,
            folder=new_folder,
            changed=tuple(changed),
            touched=tuple(sorted(touched)),
            scope_changed=scope_changed,
        )
        return _finish(workspace, result)
