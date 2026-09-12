"""Deterministic initialization for the knowledge-os-documentation skill."""

from __future__ import annotations

import json
import os
import tomllib
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Iterable

from .model import ID_PATTERN
from .workspace import Workspace, WorkspaceError, atomic_write, validate_workspace, workspace_identity


BEGIN_MARKER = "<!-- BEGIN KNOWLEDGE OS DOCUMENTATION -->"
END_MARKER = "<!-- END KNOWLEDGE OS DOCUMENTATION -->"
CONFIG_PATH = Path(".knowledge-os") / "config.toml"
REPO_CONFIG_NAME = ".knowledge-os-project.toml"


class DocumentationInitError(ValueError):
    """A user-actionable initialization error."""


def _absolute(path: Path, *, label: str) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except Exception as exc:
        raise DocumentationInitError(f"{label} cannot be resolved: {exc}") from exc


def _validated_workspace(path: Path) -> Workspace:
    try:
        workspace = Workspace(path)
    except (WorkspaceError, OSError, RuntimeError) as exc:
        raise DocumentationInitError(f"invalid Knowledge OS workspace: {exc}") from exc
    _, issues = validate_workspace(workspace)
    if issues:
        details = "\n".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise DocumentationInitError(f"invalid Knowledge OS workspace:\n{details}")
    return workspace


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _global_config(workspace: Workspace) -> bytes:
    return (
        "[knowledge_os]\n"
        "version = 1\n"
        f"workspace = {_toml_string(str(workspace.root))}\n"
    ).encode("utf-8")


def _block(newline: str) -> str:
    return newline.join(
        (
            BEGIN_MARKER,
            "Use knowledge-os-documentation when durable user context or a repository binding may affect the task.",
            "Read only relevant records.",
            "Write only with authority from the current request.",
            END_MARKER,
        )
    )


def _managed_block_content(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentationInitError("a harness instruction file is not valid UTF-8") from exc

    newline = "\r\n" if "\r\n" in text else "\n"
    begin_count = text.count(BEGIN_MARKER)
    end_count = text.count(END_MARKER)
    if begin_count != end_count or begin_count > 1:
        raise DocumentationInitError(
            "a harness instruction file has an incomplete or duplicated Knowledge OS block"
        )

    if begin_count == 1:
        begin = text.index(BEGIN_MARKER)
        end = text.index(END_MARKER)
        if begin > end:
            raise DocumentationInitError("a harness instruction file has reversed Knowledge OS block markers")
        line_start = text.rfind("\n", 0, begin) + 1
        if text[line_start:begin].strip("\r"):
            raise DocumentationInitError("Knowledge OS block markers must start at the beginning of a line")
        after_end = end + len(END_MARKER)
        if after_end < len(text) and text[after_end] not in "\r\n":
            raise DocumentationInitError("Knowledge OS block end marker must end a line")
        if after_end < len(text) and text[after_end:after_end + 2] == "\r\n":
            after_end += 2
        elif after_end < len(text) and text[after_end] == "\n":
            after_end += 1
        replacement = _block(newline)
        if after_end < len(text) or text.endswith(("\n", "\r")):
            replacement += newline
        return (text[:line_start] + replacement + text[after_end:]).encode("utf-8")

    separator = ""
    if text:
        separator = "" if text.endswith(("\n", "\r")) else newline
    return (text + separator + _block(newline) + newline).encode("utf-8")


def _read_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise DocumentationInitError(f"cannot read {path}: {exc}") from exc


def _restore(path: Path, original: bytes | None) -> None:
    try:
        if original is None:
            if path.exists() or path.is_symlink():
                path.unlink()
        else:
            atomic_write(path, original)
    except OSError:
        pass


def _write_plan(plan: list[tuple[Path, bytes]]) -> list[Path]:
    snapshots = {path: _read_bytes(path) for path, _ in plan}
    changed = [(path, content) for path, content in plan if snapshots[path] != content]
    if not changed:
        return []
    try:
        for path, content in changed:
            atomic_write(path, content)
    except Exception as exc:
        for path, _ in reversed(changed):
            _restore(path, snapshots[path])
        raise DocumentationInitError(f"write failed for {path}; changed files were restored: {exc}") from exc
    return [path for path, _ in changed]


def init_global(
    workspace_path: Path,
    *,
    hosts: Iterable[str] | None = None,
    user_home: Path | None = None,
    replace: bool = False,
) -> dict[str, object]:
    """Plan and write the global Knowledge OS configuration and host blocks."""

    workspace = _validated_workspace(_absolute(workspace_path, label="workspace"))
    home = _absolute(user_home or Path.home(), label="user home")
    requested_hosts = set(hosts or ("codex", "claude"))
    invalid_hosts = sorted(requested_hosts - {"codex", "claude"})
    if invalid_hosts:
        raise DocumentationInitError(f"unsupported host(s): {', '.join(invalid_hosts)}")
    selected_hosts = tuple(host for host in ("codex", "claude") if host in requested_hosts)

    config_path = home / CONFIG_PATH
    config_content = _global_config(workspace)
    existing_config = _read_bytes(config_path)
    if existing_config is not None and existing_config != config_content and not replace:
        raise DocumentationInitError(f"conflicting Knowledge OS config exists at {config_path}; use --replace")

    plan: list[tuple[Path, bytes]] = [(config_path, config_content)]
    for host in selected_hosts:
        host_path = home / (".codex" if host == "codex" else ".claude") / ("AGENTS.md" if host == "codex" else "CLAUDE.md")
        existing = _read_bytes(host_path)
        plan.append((host_path, _managed_block_content(existing or b"")))

    changed = _write_plan(plan)
    return {
        "config": str(config_path),
        "hosts": list(selected_hosts),
        "workspace": str(workspace.root),
        "changed": bool(changed),
        "changed_paths": [str(path) for path in changed],
    }


def _load_global_config(home: Path) -> tuple[Path, dict[str, object]]:
    path = home / CONFIG_PATH
    raw = _read_bytes(path)
    if raw is None:
        raise DocumentationInitError(f"global Knowledge OS config not found at {path}; run 'kos documentation init-global'")
    try:
        config = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise DocumentationInitError(f"invalid Knowledge OS config at {path}: {exc}") from exc
    section = config.get("knowledge_os")
    workspace_value = section.get("workspace") if isinstance(section, dict) else None
    if (
        not isinstance(section, dict)
        or section.get("version") != 1
        or not isinstance(workspace_value, str)
        or not workspace_value.strip()
        or not Path(workspace_value).is_absolute()
    ):
        raise DocumentationInitError(f"invalid Knowledge OS config at {path}: expected [knowledge_os], version = 1, and workspace")
    return path, section


def _portable_relative(value: str) -> str:
    if not value:
        raise DocumentationInitError("project mapping path must not be empty")
    try:
        posix = PurePosixPath(value.replace("\\", "/"))
        windows = PureWindowsPath(value)
    except (TypeError, ValueError) as exc:
        raise DocumentationInitError(f"invalid project mapping path {value!r}") from exc
    if posix.is_absolute() or windows.is_absolute() or windows.drive or windows.root:
        raise DocumentationInitError(f"project mapping path must be relative: {value!r}")
    if ".." in posix.parts or ".." in windows.parts:
        raise DocumentationInitError(f"project mapping path must not contain parent traversal: {value!r}")
    if value in {".", "./"}:
        return "."
    normalized = PurePosixPath(*posix.parts).as_posix()
    if normalized in {"", "."}:
        return "."
    return normalized


def _project_mappings(values: Iterable[str]) -> list[tuple[str, str]]:
    mappings: list[tuple[str, str]] = []
    ids: set[str] = set()
    paths: set[str] = set()
    for value in values:
        if "=" in value:
            project_id, raw_path = value.split("=", 1)
            relative = _portable_relative(raw_path)
        else:
            project_id, relative = value, "."
        if not ID_PATTERN.fullmatch(project_id):
            raise DocumentationInitError(f"project ID must be lowercase kebab-case: {project_id!r}")
        if project_id in ids:
            raise DocumentationInitError(f"project ID is mapped more than once: {project_id!r}")
        if relative in paths:
            raise DocumentationInitError(f"repository path is mapped more than once: {relative!r}")
        ids.add(project_id)
        paths.add(relative)
        mappings.append((project_id, relative))
    if not mappings:
        raise DocumentationInitError("at least one --project mapping is required")
    return sorted(mappings)


def _repo_config(workspace: Workspace, mappings: list[tuple[str, str]]) -> bytes:
    identity = workspace_identity(workspace)
    workspace_name = identity["name"]
    if not isinstance(workspace_name, str) or not workspace_name.strip():
        raise DocumentationInitError("configured workspace must have a non-empty workspace name")
    lines = [
        "[knowledge_os]",
        "version = 1",
        f"workspace_name = {_toml_string(workspace_name)}",
        f"workspace_schema_version = {identity['schema_version']}",
        "",
    ]
    for project_id, relative in mappings:
        lines.extend(
            (
                "[[knowledge_os.projects]]",
                f"id = {_toml_string(project_id)}",
                f"path = {_toml_string(relative)}",
                "",
            )
        )
    return ("\n".join(lines)).encode("utf-8")


def init_repo(
    repo_path: Path,
    projects: Iterable[str],
    *,
    user_home: Path | None = None,
    replace: bool = False,
) -> dict[str, object]:
    """Plan and write one repository binding file."""

    home = _absolute(user_home or Path.home(), label="user home")
    _, global_config = _load_global_config(home)
    workspace_value = global_config["workspace"]
    workspace = _validated_workspace(Path(str(workspace_value)))

    repo = _absolute(repo_path, label="repository")
    if not repo.is_dir():
        raise DocumentationInitError(f"repository directory not found: {repo}")

    mappings = _project_mappings(projects)
    documents, _ = validate_workspace(workspace)
    resolved_mappings: dict[str, str] = {}
    for project_id, relative in mappings:
        mapped = repo if relative == "." else repo / Path(*relative.split("/"))
        try:
            resolved = mapped.resolve(strict=True)
        except Exception as exc:
            raise DocumentationInitError(f"repository mapping path does not exist: {relative!r}") from exc
        try:
            resolved.relative_to(repo)
        except ValueError as exc:
            raise DocumentationInitError(f"repository mapping path escapes the repository: {relative!r}") from exc
        if not resolved.is_dir():
            raise DocumentationInitError(f"repository mapping path is not a directory: {relative!r}")
        resolved_key = os.path.normcase(str(resolved))
        previous = resolved_mappings.get(resolved_key)
        if previous is not None:
            raise DocumentationInitError(
                f"repository paths {previous!r} and {relative!r} resolve to the same directory"
            )
        resolved_mappings[resolved_key] = relative
        overviews = [
            document
            for document in documents
            if document.metadata["type"] == "project"
            and document.metadata["id"] == project_id
            and document.metadata["scope"] == f"project:{project_id}"
        ]
        if len(overviews) != 1:
            raise DocumentationInitError(
                f"project {project_id!r} has no usable unique project overview in the configured workspace"
            )
        if overviews[0].metadata["status"] not in {"draft", "active"}:
            raise DocumentationInitError(f"project {project_id!r} overview must have draft or active status")

    destination = repo / REPO_CONFIG_NAME
    content = _repo_config(workspace, mappings)
    existing = _read_bytes(destination)
    if existing is not None and existing != content and not replace:
        raise DocumentationInitError(f"conflicting repository binding exists at {destination}; use --replace")
    changed = _write_plan([(destination, content)])
    return {
        "path": str(destination),
        "workspace_name": workspace.config["workspace"].get("name"),
        "projects": [{"id": project_id, "path": relative} for project_id, relative in mappings],
        "changed": bool(changed),
        "changed_paths": [str(path) for path in changed],
    }
