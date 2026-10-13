"""Keep a project's documentation in step with its code (issue #84).

A project overview may list the code repositories it describes in its
``repositories`` metadata: where each one is on this computer (``path``,
absolute or relative to the knowledge base folder), optionally its
``remote``, and the commit its documentation was last checked against
(``checked``, with the date in ``checked_on``). Linking a repository records
its current commit, so the first check covers what happens after linking.

``check_documentation`` is deterministic and writes nothing. For each linked
repository it asks Git what changed between the checked commit and ``HEAD``
(commits, files, dependencies, commands and API routes, configuration,
modules, documentation), and turns that into suggestions, each naming the
commits it came from:

- a page update for every project page that mentions something that was
  removed or changed, and for the overview when something new is mentioned
  nowhere yet, or when the repository's README changed;
- a proposed decision for anything that reads like one: a dependency added or
  removed, or a top-level module added or removed.

Nothing is rewritten silently. A person or an agent writes the page updates
(under the review rules), a suggested decision becomes a draft decision whose
provenance names its commits (``decision_draft``), and ``with_checked``
records the commit a check covered so the next check starts there.
"""

from __future__ import annotations

import json
import os
import posixpath
import re
import subprocess
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .model import Document

#: The provenance kind of a decision drafted from a documentation check; its
#: reference is ``<repository label>@<full commit hash>``.
REPOSITORY_COMMIT_KIND = "repository-commit"

GIT_TIMEOUT_SECONDS = 60
MAX_COMMITS = 200
MAX_DIFF_BYTES = 8 * 1024 * 1024
MAX_PAGE_SUGGESTIONS = 25
MAX_REASONS_PER_PAGE = 8
MAX_DECISION_COMMITS = 10

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt", ".cs",
    ".rb", ".php", ".swift", ".c", ".cc", ".cpp", ".h", ".hpp", ".scala", ".ex", ".exs", ".vue", ".svelte",
}
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".adoc", ".txt"}
CONFIG_EXTENSIONS = {".toml", ".ini", ".cfg", ".conf", ".yaml", ".yml", ".env", ".properties"}
CONFIG_NAMES = {"dockerfile", "makefile", ".env.example", ".editorconfig", "procfile"}
LOCK_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "cargo.lock",
    "go.sum", "gemfile.lock", "composer.lock", "pipfile.lock",
}
#: Folders whose files are built, bundled, or vendored rather than written.
GENERATED_PARTS = {"node_modules", "dist", "build", "out", "vendor", "static", "__pycache__", ".venv", "target"}
TEST_PARTS = {"test", "tests", "__tests__", "spec", "specs", "testing"}

#: Lines in a diff that declare a command or an API route, in common frameworks.
COMMAND_PATTERNS = (re.compile(r"""add_parser\(\s*["']([\w][\w-]*)["']"""),)
ROUTE_PATTERNS = (
    re.compile(r"""\bRoute\(\s*["'](/[^"']*)["']"""),
    re.compile(r"""@\w+(?:\.\w+)*\.(?:get|post|put|patch|delete|route|api_route)\(\s*["'](/[^"']*)["']"""),
    re.compile(r"""\b(?:app|router|server)\.(?:get|post|put|patch|delete|all)\(\s*["'`](/[^"'`]*)["'`]"""),
)


class CodeDocsError(ValueError):
    """A user-actionable problem with a linked repository."""


# ---------------------------------------------------------------------------
# Links in the overview
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RepositoryLink:
    path: str
    remote: str | None
    checked: str | None
    checked_on: str | None

    def as_metadata(self) -> dict[str, str]:
        item: dict[str, str] = {"path": self.path}
        if self.remote:
            item["remote"] = self.remote
        if self.checked and self.checked_on:
            item["checked"] = self.checked
            item["checked_on"] = self.checked_on
        return item


def repository_links(metadata: Mapping[str, Any]) -> list[RepositoryLink]:
    """The repositories a (validated) project overview links."""

    links = []
    for item in metadata.get("repositories") or []:
        checked_on = item.get("checked_on")
        links.append(
            RepositoryLink(
                path=str(item["path"]),
                remote=item.get("remote"),
                checked=item.get("checked"),
                checked_on=str(checked_on) if checked_on is not None else None,
            )
        )
    return links


def resolve(root: Path, path: str) -> Path:
    """A link's folder on this computer: absolute, or relative to the knowledge base."""

    candidate = Path(os.path.expanduser(path))
    if not candidate.is_absolute():
        candidate = root / candidate
    return candidate.resolve(strict=False)


def label(link: RepositoryLink) -> str:
    """How provenance and messages name a repository: its remote without
    credentials, else its folder name."""

    if link.remote:
        return strip_credentials(link.remote)
    return Path(link.path.replace("\\", "/").rstrip("/")).name or link.path


def strip_credentials(url: str) -> str:
    return re.sub(r"^(\w[\w+.-]*://)[^/@]*@", r"\1", url.strip())


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def with_link(
    root: Path, links: Sequence[RepositoryLink], path: str, *, remote: str | None = None
) -> tuple[list[RepositoryLink], RepositoryLink]:
    """The overview's repositories with one more: ``path`` must be a Git
    repository with at least one commit, which becomes the checked commit."""

    clean = path.strip()
    if not clean:
        raise CodeDocsError("give the repository's folder")
    folder = resolve(root, clean)
    for link in links:
        if resolve(root, link.path) == folder:
            raise CodeDocsError(f"{clean} is already linked to this project")
    head = head_commit(folder)
    if remote is None:
        remote = _origin(folder)
    link = RepositoryLink(clean, strip_credentials(remote) if remote else None, head, _today())
    return [*links, link], link


def without_link(root: Path, links: Sequence[RepositoryLink], path: str) -> list[RepositoryLink]:
    folder = resolve(root, path.strip())
    kept = [link for link in links if link.path != path and resolve(root, link.path) != folder]
    if len(kept) == len(links):
        raise CodeDocsError(f"{path} is not linked to this project")
    return kept


def with_checked(root: Path, links: Sequence[RepositoryLink], path: str, commit: str) -> list[RepositoryLink]:
    """Record that the documentation was checked against ``commit``, which
    must exist in the repository and not go back behind the last check."""

    target = next((link for link in links if link.path == path), None)
    if target is None:
        raise CodeDocsError(f"{path} is not linked to this project")
    folder = resolve(root, target.path)
    full = _rev_parse(folder, commit)
    if target.checked and target.checked != full and not _is_ancestor(folder, target.checked, full):
        raise CodeDocsError(
            f"{commit[:12]} does not come after the last checked commit {target.checked[:12]}; nothing was recorded"
        )
    updated = RepositoryLink(target.path, target.remote, full, _today())
    return [updated if link is target else link for link in links]


def links_metadata(links: Iterable[RepositoryLink]) -> list[dict[str, str]] | None:
    """The ``repositories`` value to write (``None`` removes the field)."""

    items = [link.as_metadata() for link in links]
    return items or None


# ---------------------------------------------------------------------------
# Git
# ---------------------------------------------------------------------------


def _git(folder: Path, *args: str, limit: int | None = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"}
    try:
        completed = subprocess.run(
            # A linked folder is named by the knowledge base, so no program its
            # repository configures (fsmonitor, external diff, textconv) may run.
            ["git", "-C", str(folder), "-c", "core.quotepath=off", "-c", "core.fsmonitor=false", *args],
            capture_output=True,
            env=env,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CodeDocsError("Git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise CodeDocsError(f"git {args[0]} took longer than {GIT_TIMEOUT_SECONDS} seconds") from exc
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip().splitlines()
        raise CodeDocsError(message[-1] if message else f"git {args[0]} failed")
    output = completed.stdout if limit is None else completed.stdout[:limit]
    return output.decode("utf-8", "replace")


def head_commit(folder: Path) -> str:
    if not folder.is_dir():
        raise CodeDocsError(f"{folder} does not exist on this computer")
    try:
        inside = _git(folder, "rev-parse", "--is-inside-work-tree").strip()
    except CodeDocsError as exc:
        raise CodeDocsError(f"{folder} is not a Git repository") from exc
    if inside != "true":
        raise CodeDocsError(f"{folder} is not a Git working folder")
    try:
        return _git(folder, "rev-parse", "--verify", "HEAD^{commit}").strip()
    except CodeDocsError as exc:
        raise CodeDocsError(f"{folder} has no commits yet") from exc


def _rev_parse(folder: Path, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{4,64}", commit):
        raise CodeDocsError(f"{commit!r} is not a commit hash")
    try:
        return _git(folder, "rev-parse", "--verify", f"{commit}^{{commit}}").strip()
    except CodeDocsError as exc:
        raise CodeDocsError(f"commit {commit[:12]} is not in {folder}") from exc


def _is_ancestor(folder: Path, older: str, newer: str) -> bool:
    try:
        _git(folder, "merge-base", "--is-ancestor", older, newer)
    except CodeDocsError:
        return False
    return True


def _origin(folder: Path) -> str | None:
    try:
        url = _git(folder, "remote", "get-url", "origin").strip()
    except CodeDocsError:
        return None
    return url or None


def _show(folder: Path, commit: str, path: str) -> str | None:
    try:
        return _git(folder, "show", f"{commit}:{path}", limit=2 * 1024 * 1024)
    except CodeDocsError:
        return None


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Commit:
    sha: str
    short: str
    author: str
    date: str
    subject: str

    def as_json(self) -> dict[str, str]:
        return {"sha": self.sha, "short": self.short, "author": self.author, "date": self.date, "subject": self.subject}


def change_noun(kind: str) -> str:
    return {
        "dependency": "dependency",
        "command": "command",
        "route": "API route",
        "configuration": "configuration file",
        "module": "module",
        "documentation": "document",
    }[kind]


@dataclass(frozen=True)
class Change:
    """One thing that changed: ``kind`` is dependency, command, route,
    configuration, module, or documentation; ``action`` is added, removed, or
    changed."""

    kind: str
    action: str
    name: str
    files: tuple[str, ...]
    commits: tuple[str, ...]  # full hashes, oldest first
    detail: str = ""

    @property
    def key(self) -> str:
        return f"{self.kind}-{self.action}:{self.name}"

    def describe(self) -> str:
        noun = change_noun(self.kind)
        where = f" ({self.detail})" if self.detail else ""
        return f"{noun} `{self.name}` {self.action}{where}"

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "kind": self.kind,
            "action": self.action,
            "name": self.name,
            "detail": self.detail,
            "summary": self.describe(),
            "files": list(self.files),
            "commits": list(self.commits),
        }


@dataclass(frozen=True)
class PageReason:
    text: str
    changes: tuple[str, ...]  # Change.key of each change it is about
    commits: tuple[str, ...]

    def as_json(self) -> dict[str, Any]:
        return {"text": self.text, "changes": list(self.changes), "commits": list(self.commits)}


@dataclass(frozen=True)
class PageSuggestion:
    page_id: str
    title: str
    path: str
    reasons: tuple[PageReason, ...]

    @property
    def commits(self) -> tuple[str, ...]:
        return _ordered(sha for reason in self.reasons for sha in reason.commits)

    def as_json(self) -> dict[str, Any]:
        return {
            "page": self.page_id,
            "title": self.title,
            "path": self.path,
            "reasons": [reason.as_json() for reason in self.reasons],
            "commits": list(self.commits),
        }


@dataclass(frozen=True)
class DecisionSuggestion:
    key: str  # Change.key
    title: str
    summary: str
    commits: tuple[str, ...]
    existing: str | None  # a decision in the project with this title, if any

    def as_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "commits": list(self.commits),
            "existing": self.existing,
        }


@dataclass(frozen=True)
class RepositoryCheck:
    link: RepositoryLink
    folder: str
    state: str  # "changed", "up-to-date", "unavailable"
    message: str
    base: str | None = None
    head: str | None = None
    commits: tuple[Commit, ...] = ()
    commits_truncated: bool = False
    changes: tuple[Change, ...] = ()
    pages: tuple[PageSuggestion, ...] = ()
    decisions: tuple[DecisionSuggestion, ...] = ()

    def commit(self, sha: str) -> Commit | None:
        return next((item for item in self.commits if item.sha == sha), None)

    def as_json(self) -> dict[str, Any]:
        return {
            "path": self.link.path,
            "remote": self.link.remote,
            "label": label(self.link),
            "folder": self.folder,
            "state": self.state,
            "message": self.message,
            "checked": self.link.checked,
            "checked_on": self.link.checked_on,
            "base": self.base,
            "head": self.head,
            "commits": [item.as_json() for item in self.commits],
            "commits_truncated": self.commits_truncated,
            "changes": [item.as_json() for item in self.changes],
            "pages": [item.as_json() for item in self.pages],
            "decisions": [item.as_json() for item in self.decisions],
        }


@dataclass(frozen=True)
class DocumentationCheck:
    project: str
    repositories: tuple[RepositoryCheck, ...]

    def repository(self, path: str) -> RepositoryCheck:
        found = next((item for item in self.repositories if item.link.path == path), None)
        if found is None:
            raise CodeDocsError(f"{path} is not linked to project {self.project!r}")
        return found

    def as_json(self) -> dict[str, Any]:
        return {"project": self.project, "repositories": [item.as_json() for item in self.repositories]}


def _ordered(values: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)


def _commits(folder: Path, base: str, head: str) -> tuple[list[Commit], bool, dict[str, list[str]]]:
    """Commits in ``base..head`` oldest first, whether the list was cut, and
    for every path the commits that touched it."""

    raw = _git(
        folder,
        "log",
        "--reverse",
        "--no-renames",
        "--date=short",
        "--format=%x1e%H%x1f%h%x1f%an%x1f%ad%x1f%s",
        "--name-only",
        f"{base}..{head}",
        limit=MAX_DIFF_BYTES,
    )
    commits: list[Commit] = []
    touched: dict[str, list[str]] = {}
    for block in raw.split("\x1e"):
        if not block.strip():
            continue
        header, _, names = block.partition("\n")
        parts = header.split("\x1f")
        if len(parts) != 5:
            continue
        commit = Commit(*parts)
        commits.append(commit)
        for name in names.splitlines():
            if name.strip():
                touched.setdefault(name.strip(), []).append(commit.sha)
    truncated = len(commits) > MAX_COMMITS
    return commits[-MAX_COMMITS:] if truncated else commits, truncated, touched


def _name_status(folder: Path, base: str, head: str) -> list[tuple[str, str]]:
    raw = _git(folder, "diff", "--no-renames", "--name-status", "-z", base, head, limit=MAX_DIFF_BYTES)
    fields = raw.split("\0")
    pairs = []
    for index in range(0, len(fields) - 1, 2):
        status, path = fields[index], fields[index + 1]
        if status and path:
            pairs.append((status[0], path))
    return pairs


def _tree(folder: Path, commit: str) -> set[str]:
    raw = _git(folder, "ls-tree", "-r", "-z", "--name-only", commit, limit=MAX_DIFF_BYTES)
    return {name for name in raw.split("\0") if name}


def _parts(path: str) -> list[str]:
    return path.split("/")


def _is_generated(path: str) -> bool:
    parts = [part.lower() for part in _parts(path)[:-1]]
    name = _parts(path)[-1].lower()
    return any(part in GENERATED_PARTS for part in parts) or name.endswith((".min.js", ".min.css", ".map"))


def _is_test(path: str) -> bool:
    parts = [part.lower() for part in _parts(path)]
    name = parts[-1]
    stem = name.rsplit(".", 1)[0]
    return (
        any(part in TEST_PARTS for part in parts[:-1])
        or stem.startswith("test_")
        or stem.endswith(("_test", ".test", ".spec"))
        or stem == "conftest"
    )


def _is_code(path: str) -> bool:
    return posixpath.splitext(path)[1].lower() in CODE_EXTENSIONS and not _is_generated(path) and not _is_test(path)


def _is_doc(path: str) -> bool:
    lower = path.lower()
    name = posixpath.basename(lower)
    if _is_generated(path):
        return False
    if name.startswith(("readme", "changelog", "contributing")):
        return True
    return posixpath.splitext(name)[1] in DOC_EXTENSIONS and (lower.startswith("docs/") or "/" not in lower)


MANIFESTS = {"pyproject.toml", "package.json", "cargo.toml", "go.mod"}


def _is_manifest(path: str) -> bool:
    name = posixpath.basename(path).lower()
    return (name in MANIFESTS or (name.startswith("requirements") and name.endswith(".txt"))) and not _is_generated(path)


def _is_config(path: str) -> bool:
    name = posixpath.basename(path).lower()
    if _is_generated(path) or _is_manifest(path) or name in LOCK_NAMES:
        return False
    if path.startswith(".github/workflows/") or name in CONFIG_NAMES or name.startswith(("docker-compose", "compose.")):
        return True
    extension = posixpath.splitext(name)[1]
    if extension in CONFIG_EXTENSIONS:
        return True
    return "config" in name and extension in {".json", ".js", ".mjs", ".cjs", ".ts"}


_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _requirement(value: str) -> str | None:
    match = _REQUIREMENT_NAME.match(value)
    return match.group(1).lower().replace("_", "-") if match else None


def _manifest_facts(path: str, text: str | None) -> tuple[set[str], set[str]]:
    """The dependency names and command names a manifest declares."""

    if text is None:
        return set(), set()
    name = posixpath.basename(path).lower()
    dependencies: set[str] = set()
    commands: set[str] = set()
    try:
        if name == "pyproject.toml":
            data = tomllib.loads(text)
            project = data.get("project") or {}
            for value in project.get("dependencies") or []:
                if isinstance(value, str) and (requirement := _requirement(value)):
                    dependencies.add(requirement)
            for group in (project.get("optional-dependencies") or {}).values():
                for value in group or []:
                    if isinstance(value, str) and (requirement := _requirement(value)):
                        dependencies.add(requirement)
            for table in ("scripts", "gui-scripts"):
                commands.update(str(key) for key in (project.get(table) or {}))
            poetry = (data.get("tool") or {}).get("poetry") or {}
            dependencies.update(str(key).lower() for key in (poetry.get("dependencies") or {}) if key != "python")
            commands.update(str(key) for key in (poetry.get("scripts") or {}))
        elif name == "package.json":
            data = json.loads(text)
            for table in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                dependencies.update(str(key) for key in (data.get(table) or {}))
            binaries = data.get("bin")
            if isinstance(binaries, str) and isinstance(data.get("name"), str):
                commands.add(data["name"].split("/")[-1])
            elif isinstance(binaries, dict):
                commands.update(str(key) for key in binaries)
        elif name == "cargo.toml":
            data = tomllib.loads(text)
            for table in ("dependencies", "dev-dependencies", "build-dependencies"):
                dependencies.update(str(key) for key in (data.get(table) or {}))
            commands.update(str(item.get("name")) for item in data.get("bin") or [] if isinstance(item, dict) and item.get("name"))
        elif name == "go.mod":
            block = False
            for line in text.splitlines():
                stripped = line.split("//")[0].strip()
                if stripped.startswith("require ("):
                    block = True
                    continue
                if block and stripped == ")":
                    block = False
                    continue
                if block and stripped:
                    dependencies.add(stripped.split()[0])
                elif stripped.startswith("require ") and not stripped.endswith("("):
                    dependencies.add(stripped.split()[1])
        else:  # requirements*.txt
            for line in text.splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith(("#", "-")) and (requirement := _requirement(stripped)):
                    dependencies.add(requirement)
    except (ValueError, TypeError, AttributeError):
        return set(), set()
    return dependencies, commands


MAX_MANIFEST_COMMITS = 50


def _manifest_history(folder: Path, path: str, commits: Sequence[str]) -> dict[tuple[str, str, str], list[str]]:
    """For each (kind, action, name), the commits whose version of ``path``
    added or removed that dependency or command compared with their parent."""

    found: dict[tuple[str, str, str], list[str]] = {}
    for sha in list(commits)[-MAX_MANIFEST_COMMITS:]:
        before_deps, before_cmds = _manifest_facts(path, _show(folder, f"{sha}^", path))
        after_deps, after_cmds = _manifest_facts(path, _show(folder, sha, path))
        for kind, before, after in (("dependency", before_deps, after_deps), ("command", before_cmds, after_cmds)):
            for name in after - before:
                found.setdefault((kind, "added", name), []).append(sha)
            for name in before - after:
                found.setdefault((kind, "removed", name), []).append(sha)
    return found


def _declarations(diff: str) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Commands and API routes declared on added (``+``) and removed (``-``)
    lines of a diff, each with the files they are in."""

    added: dict[str, set[str]] = {}
    removed: dict[str, set[str]] = {}
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[4:].removeprefix("b/")
            continue
        if line.startswith("--- "):
            continue
        if not line.startswith(("+", "-")):
            continue
        target = added if line.startswith("+") else removed
        text = line[1:]
        for pattern in COMMAND_PATTERNS:
            for match in pattern.finditer(text):
                target.setdefault(f"command:{match.group(1)}", set()).add(current)
        for pattern in ROUTE_PATTERNS:
            for match in pattern.finditer(text):
                target.setdefault(f"route:{match.group(1)}", set()).add(current)
    return added, removed


def _top_new_folder(path: str, before: set[str]) -> str | None:
    """The shallowest folder above ``path`` under which ``before`` has no
    code, or ``None`` when every folder above it already had code."""

    parts = _parts(path)[:-1]
    for depth in range(1, len(parts) + 1):
        folder = "/".join(parts[:depth]) + "/"
        if not any(name.startswith(folder) for name in before):
            return folder.rstrip("/")
    return None


MAX_PICKAXE = 60


def _changes(folder: Path, base: str, head: str, touched: Mapping[str, list[str]]) -> list[Change]:
    files = [(status, path) for status, path in _name_status(folder, base, head)]
    action_of = {"A": "added", "D": "removed"}
    changes: list[Change] = []
    searches = [0]

    def commits_for(paths: Iterable[str]) -> tuple[str, ...]:
        return _ordered(sha for path in paths for sha in touched.get(path, ()))

    def commits_with(text: str, paths: Sequence[str]) -> tuple[str, ...]:
        """The commits that added or removed ``text`` in ``paths`` (git log -S),
        falling back to every commit that touched them."""

        if searches[0] < MAX_PICKAXE:
            searches[0] += 1
            try:
                found = _git(
                    folder, "log", "--no-textconv", "--reverse", "--format=%H", f"-S{text}", f"{base}..{head}", "--", *paths
                ).split()
            except CodeDocsError:
                found = []
            if found:
                return tuple(found)
        return commits_for(paths)

    # Dependencies and manifest-declared commands, each attributed to the
    # commits whose version of the manifest added or removed it.
    for status, path in files:
        if not _is_manifest(path):
            continue
        before_deps, before_cmds = _manifest_facts(path, _show(folder, base, path) if status != "A" else None)
        after_deps, after_cmds = _manifest_facts(path, _show(folder, head, path) if status != "D" else None)
        history = _manifest_history(folder, path, touched.get(path, [])) if (before_deps ^ after_deps) or (before_cmds ^ after_cmds) else {}
        for kind, names, action in (
            ("dependency", after_deps - before_deps, "added"),
            ("dependency", before_deps - after_deps, "removed"),
            ("command", after_cmds - before_cmds, "added"),
            ("command", before_cmds - after_cmds, "removed"),
        ):
            for name in sorted(names):
                commits = history.get((kind, action, name)) or commits_for([path])
                changes.append(Change(kind, action, name, (path,), tuple(commits), f"in {path}"))

    # Commands and API routes declared in code.
    code_paths = [path for _status, path in files if _is_code(path)]
    if code_paths:
        diff = _git(
            folder, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", "-U0", base, head, "--", *code_paths[:2000],
            limit=MAX_DIFF_BYTES,
        )
        added, removed = _declarations(diff)
        for key in sorted(set(added) | set(removed)):
            kind, _, name = key.partition(":")
            if key in added and key in removed:
                continue  # moved or reformatted, still declared
            action = "added" if key in added else "removed"
            paths = tuple(sorted((added if key in added else removed)[key]))
            changes.append(Change(kind, action, name, paths, commits_with(name, paths), f"in {', '.join(paths)}"))

    # Configuration and documentation files.
    for status, path in files:
        action = action_of.get(status, "changed")
        if _is_config(path):
            changes.append(Change("configuration", action, path, (path,), commits_for([path])))
        elif _is_doc(path):
            changes.append(Change("documentation", action, path, (path,), commits_for([path])))

    # Modules: new or removed code folders, else single code files.
    added_code = sorted(path for status, path in files if status == "A" and _is_code(path))
    removed_code = sorted(path for status, path in files if status == "D" and _is_code(path))
    if added_code or removed_code:
        before = {path for path in _tree(folder, base) if _is_code(path)}
        after = {path for path in _tree(folder, head) if _is_code(path)}
        for action, paths, other in (("added", added_code, before), ("removed", removed_code, after)):
            grouped: dict[str, list[str]] = {}
            for path in paths:
                top = _top_new_folder(path, other)
                grouped.setdefault(top or path, []).append(path)
            for name, members in sorted(grouped.items()):
                detail = f"{len(members)} file{'s' if len(members) != 1 else ''}" if name not in members else ""
                changes.append(Change("module", action, name, tuple(members), commits_for(members), detail))
    return changes


# Words that make a poor search term on their own.
_GENERIC_TERMS = {
    "index", "main", "utils", "util", "common", "types", "init", "__init__", "app", "core", "base", "config",
    "readme", "test", "tests", "helpers", "lib", "src", "api", "cli", "setup", "data", "model", "models",
}


def _terms(change: Change) -> list[str]:
    """What a page would say if it described ``change``."""

    terms = [change.name]
    if change.kind in {"module", "configuration", "documentation"}:
        base = posixpath.basename(change.name)
        stem = posixpath.splitext(base)[0]
        for term in (base, stem):
            if len(term) >= 4 and term.lower() not in _GENERIC_TERMS:
                terms.append(term)
    if change.kind == "command" and len(change.name) < 4:
        terms = []  # too short to find reliably
    if change.kind == "route" and change.name in {"/", ""}:
        terms = []
    return _ordered_list(term for term in terms if term)


def _ordered_list(values: Iterable[str]) -> list[str]:
    return list(_ordered(values))


def _mentions(text: str, term: str, *, ignore_case: bool) -> bool:
    if "/" in term or "." in term:
        return term in text
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", text, flags) is not None


def _is_decision(document: Document) -> bool:
    return document.metadata.get("record_kind") == "decision"


_KIND_PLURALS = {"dependency": "dependencies", "command": "commands", "route": "API routes", "module": "modules"}


def _page_suggestions(
    changes: Sequence[Change], pages: Sequence[Document], overview: Document, rel_path: Any
) -> list[PageSuggestion]:
    editable = [page for page in pages if not _is_decision(page)]
    reasons: dict[str, list[PageReason]] = {}

    def add(page: Document, reason: PageReason) -> None:
        bucket = reasons.setdefault(page.metadata["id"], [])
        if len(bucket) < MAX_REASONS_PER_PAGE:
            bucket.append(reason)

    for change in changes:
        if change.kind == "documentation" and change.name.lower().startswith("readme"):
            add(overview, PageReason(f"The repository's {change.name} was {change.action}; the overview may need the same change.", (change.key,), change.commits))

    unmentioned: dict[str, list[Change]] = {}
    for change in changes:
        terms = _terms(change)
        if change.kind == "documentation" or not terms:
            continue
        # Package names are written in any case; commands, routes, and paths exactly.
        ignore_case = change.kind == "dependency"
        mentioning = [page for page in editable if any(_mentions(page.body, term, ignore_case=ignore_case) for term in terms)]
        if change.action in {"removed", "changed"}:
            for page in mentioning:
                add(page, PageReason(f"Mentions the {change.describe()}.", (change.key,), change.commits))
        elif not mentioning and change.kind in _KIND_PLURALS and not (change.kind == "module" and not change.detail):
            # A single new source file is rarely worth a page; a new folder of them may be.
            unmentioned.setdefault(change.kind, []).append(change)

    for kind, group in unmentioned.items():
        names = ", ".join(f"`{change.name}`" for change in group[:6]) + (f", and {len(group) - 6} more" if len(group) > 6 else "")
        noun = _KIND_PLURALS[kind] if len(group) > 1 else change_noun(kind)
        add(
            overview,
            PageReason(
                f"No page mentions the new {noun} {names} yet.",
                tuple(change.key for change in group),
                _ordered(sha for change in group for sha in change.commits),
            ),
        )

    by_id = {page.metadata["id"]: page for page in [overview, *editable]}
    ordered = sorted(reasons.items(), key=lambda item: (item[0] != overview.metadata["id"], by_id[item[0]].metadata["title"].lower()))
    return [
        PageSuggestion(page_id, by_id[page_id].metadata["title"], rel_path(by_id[page_id].path), tuple(items))
        for page_id, items in ordered[:MAX_PAGE_SUGGESTIONS]
    ]


def decision_title(change: Change) -> str:
    if change.kind == "dependency":
        return f"{'Add' if change.action == 'added' else 'Remove'} the dependency {change.name}"
    return f"{'Add' if change.action == 'added' else 'Remove'} the module {change.name}"


def _decision_suggestions(changes: Sequence[Change], decisions: Sequence[Document]) -> list[DecisionSuggestion]:
    titles = {document.metadata["title"].strip().lower(): document.metadata["id"] for document in decisions}
    suggestions = []
    for change in changes:
        new_folder = change.kind == "module" and bool(change.detail)
        if change.kind != "dependency" and not new_folder:
            continue
        title = decision_title(change)
        suggestions.append(
            DecisionSuggestion(change.key, title, change.describe()[0].upper() + change.describe()[1:] + ".", change.commits, titles.get(title.lower()))
        )
    return suggestions


def _check_one(root: Path, link: RepositoryLink, overview: Document, pages: Sequence[Document], rel_path: Any, since: str | None) -> RepositoryCheck:
    folder = resolve(root, link.path)
    try:
        head = head_commit(folder)
        start = since or link.checked
        if start is None:
            return RepositoryCheck(link, str(folder), "unavailable", "This repository has not been checked yet; link it again to start from its current commit.")
        try:
            base = _rev_parse(folder, start)
        except CodeDocsError:
            return RepositoryCheck(
                link, str(folder), "unavailable",
                f"The last checked commit {start[:12]} is not in this repository (was its history rewritten, or is it not fetched?).",
                head=head,
            )
        if base == head:
            return RepositoryCheck(link, str(folder), "up-to-date", "Nothing changed since the last check.", base, head)
        if not _is_ancestor(folder, base, head):
            return RepositoryCheck(
                link, str(folder), "unavailable",
                f"The current commit {head[:12]} does not come after the last checked commit {base[:12]}; switch to the branch the documentation follows.",
                base, head,
            )
        commits, truncated, touched = _commits(folder, base, head)
        changes = _changes(folder, base, head, touched)
    except CodeDocsError as exc:
        return RepositoryCheck(link, str(folder), "unavailable", str(exc))
    decisions = [page for page in pages if _is_decision(page)]
    count = len(commits)
    message = f"{count}{'+' if truncated else ''} commit{'s' if count != 1 else ''} since {link.checked_on or base[:12]}."
    return RepositoryCheck(
        link, str(folder), "changed", message, base, head, tuple(commits), truncated, tuple(changes),
        tuple(_page_suggestions(changes, pages, overview, rel_path)),
        tuple(_decision_suggestions(changes, decisions)),
    )


def check_documentation(
    root: Path,
    project_id: str,
    documents: Sequence[Document],
    rel_path: Any,
    *,
    since: Mapping[str, str] | None = None,
) -> DocumentationCheck:
    """Compare a project's pages with what changed in its linked repositories.

    ``documents`` is the validated corpus, ``rel_path`` turns a document's
    path into its workspace-relative POSIX path, and ``since`` optionally
    starts a repository's check at another commit than its checked one."""

    scope = f"project:{project_id}"
    overview = next(
        (d for d in documents if d.metadata["type"] == "project" and d.metadata["id"] == project_id and d.metadata["scope"] == scope),
        None,
    )
    if overview is None:
        raise CodeDocsError(f"project not found: {project_id}")
    pages = [d for d in documents if d.metadata["scope"] == scope and d.metadata["type"] in {"project", "knowledge"}]
    links = repository_links(overview.metadata)
    return DocumentationCheck(
        project_id,
        tuple(_check_one(root, link, overview, pages, rel_path, (since or {}).get(link.path)) for link in links),
    )


def decision_draft(check: RepositoryCheck, key: str) -> tuple[str, str, list[dict[str, str]]]:
    """The title, body, and provenance of a draft decision for one suggestion:
    the provenance names each commit it came from."""

    suggestion = next((item for item in check.decisions if item.key == key), None)
    change = next((item for item in check.changes if item.key == key), None)
    if suggestion is None or change is None:
        raise CodeDocsError(f"the check of {check.link.path} suggests no decision {key!r}; run the check again")
    if suggestion.existing:
        raise CodeDocsError(f"the decision {suggestion.title!r} already exists ({suggestion.existing})")
    repository = label(check.link)
    lines = [
        f"The repository {repository} {change.action} the {change.kind} `{change.name}`"
        + (f" ({change.detail})" if change.detail else "")
        + ". This proposal was drafted by a documentation check; say why, or withdraw it if it needs no decision.",
        "",
        "## Commits",
        "",
    ]
    for sha in change.commits:
        commit = check.commit(sha)
        lines.append(f"- `{sha[:12]}` {commit.subject} ({commit.author}, {commit.date})" if commit else f"- `{sha[:12]}`")
    if len(change.files) > 1 or change.kind == "module":
        lines += ["", "## Files", ""] + [f"- `{path}`" for path in change.files[:30]]
    stamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    provenance = [
        {"kind": REPOSITORY_COMMIT_KIND, "reference": f"{repository}@{sha}", "captured": stamp}
        for sha in change.commits[-MAX_DECISION_COMMITS:]
    ] or [{"kind": REPOSITORY_COMMIT_KIND, "reference": f"{repository}@{check.head}", "captured": stamp}]
    return suggestion.title, "\n".join(lines) + "\n", provenance



MAX_COMMIT_DIFF_CHARS = 20_000


def commit_details(folder: Path, commit: str) -> dict[str, Any]:
    """One commit of a linked repository: its message, the files it changed,
    and its diff, cut at ``MAX_COMMIT_DIFF_CHARS`` characters. Read-only."""

    sha = _rev_parse(folder, commit)
    header = _git(folder, "show", "-s", "--date=short", "--format=%H%x1f%h%x1f%an%x1f%ad%x1f%s%x1f%b", sha)
    full, short, author, day, subject, body = (header.rstrip("\n").split("\x1f") + [""] * 6)[:6]
    files = []
    raw = _git(folder, "show", "--no-renames", "--format=", "--name-status", "-z", sha, limit=MAX_DIFF_BYTES)
    fields = raw.split("\0")
    for index in range(0, len(fields) - 1, 2):
        if fields[index] and fields[index + 1]:
            files.append({"status": {"A": "added", "D": "removed"}.get(fields[index][0], "changed"), "path": fields[index + 1]})
    diff = _git(
        folder, "show", "--no-ext-diff", "--no-textconv", "--no-renames", "--format=", "--patch", sha,
        limit=MAX_COMMIT_DIFF_CHARS * 4,
    )
    truncated = len(diff) > MAX_COMMIT_DIFF_CHARS
    return {
        "sha": full,
        "short": short,
        "author": author,
        "date": day,
        "subject": subject,
        "body": body.strip(),
        "files": files,
        "diff": diff[:MAX_COMMIT_DIFF_CHARS],
        "diff_truncated": truncated,
    }
