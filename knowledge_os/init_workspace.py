"""Create an empty, valid Knowledge OS workspace in a chosen folder.

``kos init PATH`` writes the workspace marker (``knowledge-os.toml``), the
managed directory layout with its documentation README files, a Git ignore
file for the disposable SQLite cache, and fresh indexes, so the result passes
``kos lint`` and is searchable immediately. It refuses a folder that is not
empty, that already is a workspace, or that lies inside another workspace, so
it never merges into, overwrites, or corrupts something that already exists.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

from .index import rebuild_indexes
from .model import ID_PATTERN
from .workspace import MANAGED_DIRS, Workspace, exclusive_write

MARKER = "knowledge-os.toml"

#: Every directory a fresh workspace gets: the six managed record roots plus
#: the conventional roots that ``docs/architecture.md`` and ``AGENTS.md``
#: describe (``inbox/``, ``indexes/``, ``skills/``, ``tooling/``).
LAYOUT_DIRS: tuple[str, ...] = (*MANAGED_DIRS, "inbox", "indexes", "skills", "tooling")

#: Root-level ``README.md`` files are documentation, not records
#: (``docs/architecture.md``, "Workspace and filesystem"). The texts match this
#: repository's own root-level READMEs; ``tests/test_init_workspace.py`` fails
#: if the two drift apart. This repository has no ``skills/README.md``.
README_CONTENT: dict[str, str] = {
    "sources": (
        "# Sources\n\n"
        "Ingested raw material lives here with provenance. Sources are searchable and\n"
        "inspectable, but are raw claims, excluded from default context, and never\n"
        "automatically verified knowledge.\n"
    ),
    "knowledge": (
        "# General knowledge\n\n"
        "Durable general knowledge records live here as metadata-bearing Markdown and\n"
        "must use `scope: general`. `record_kind: decision` is optional for an\n"
        "architectural decision; absence means an ordinary record.\n"
        "Decision records are captured as drafts. An active or superseded decision must\n"
        "retain explicit `decision-acceptance` provenance; acceptance is independent of\n"
        "implementation and verification.\n"
    ),
    "projects": (
        "# Projects\n\n"
        "Each project owns one directory at `projects/<project-id>/`. Its required\n"
        "overview is `projects/<project-id>/README.md` with `id: <project-id>`, `type:\n"
        "project`, and `scope: project:<project-id>`; its status must be `draft` or\n"
        "`active`. Every other project record with that scope also stays below the same\n"
        "project directory.\n\n"
        "Inside a project directory, folders may use any safe filesystem name and nest\n"
        "to any depth. A folder may have its own metadata-bearing `README.md` root\n"
        "record; other records retain the normal `<id>.md` filename. IDs remain globally\n"
        "unique. `kos capture --project-path PATH` creates a project record at an\n"
        "explicit path relative to its project directory and creates missing parent\n"
        "folders. `kos lint` enforces containment and the overview identity invariant.\n"
        "Project decision records use the same explicit acceptance and supersession\n"
        "contract as general decisions. A draft replacement does not retire its active\n"
        "target; only `kos supersede` performs that coordinated transition.\n"
    ),
    "memory": (
        "# Memory\n\n"
        "Durable user or agent memory records live here as metadata-bearing Markdown.\n"
    ),
    "syntheses": (
        "# Syntheses\n\n"
        "Explicitly synthesized durable records live here with provenance and relationship links.\n"
    ),
    "discoveries": (
        "# Discoveries\n\n"
        "External-agent observations live here as evidence-bearing Markdown records. A discovery is "
        "canonical as an observation, never established knowledge by ingestion or indexing.\n\n"
        "The explicit lifecycle is `proposed -> retained | rejected | promoted`.\n"
        "Retained discoveries must be project-scoped and are eligible only for that\n"
        "project's context, where they are labeled reviewed observations. Promotion\n"
        "creates a new draft knowledge/project record with direct discovery provenance\n"
        "and a promote review target; it never adds duplicate `sources` or `related`\n"
        "lineage, merges, overwrites, or supersedes an existing record.\n"
    ),
    "inbox": (
        "# Inbox\n\n"
        "Place untrusted intake here. Inbox files are not required to have durable "
        "metadata and are not indexed until explicitly ingested or promoted.\n"
    ),
    "indexes": (
        "# Indexes\n\n"
        "Generated catalogs are disposable caches. Run `kos index`; do not edit\n"
        "generated files manually. The catalog and SQLite FTS cache include discovery\n"
        "records and all discovery statuses for audit; context applies the separate\n"
        "trust and scope policy. Deleting both generated files leaves the Markdown\n"
        "corpus valid and `kos index` rebuilds them.\n"
    ),
    "tooling": (
        "# Tooling\n\n"
        "Small local support material may live here. Core knowledge remains in the "
        "semantic directories.\n"
    ),
}

#: Keeps the binary SQLite cache out of the knowledge base's own Git history,
#: matching this repository's ignore rules; ``indexes/catalog.md`` stays tracked.
GITIGNORE_CONTENT = "indexes/catalog.sqlite3\nindexes/catalog.sqlite3-*\nindexes/.catalog.sqlite3.tmp\n"


class WorkspaceInitError(ValueError):
    """A user-actionable error creating a new workspace."""


def default_workspace_name(path: Path) -> str:
    """Derive a lowercase kebab-case workspace name from a folder name."""

    candidate = re.sub(r"[^a-z0-9]+", "-", path.name.lower()).strip("-")
    return candidate if ID_PATTERN.fullmatch(candidate) else "workspace"


def _enclosing_workspace(target: Path) -> Path | None:
    for candidate in target.parents:
        if (candidate / MARKER).exists():
            return candidate
    return None


def init_workspace(path: Path, *, name: str | None = None) -> Path:
    """Create a new, empty, valid workspace at ``path`` and return its root.

    ``path`` may be missing (it is created with its parents) or an empty
    directory. Opening an existing workspace is ``kos --root PATH ...``, not
    this command.
    """

    target = Path.cwd() / path.expanduser()
    target = target.resolve(strict=False)
    workspace_name = default_workspace_name(target) if name is None else name
    if not ID_PATTERN.fullmatch(workspace_name):
        raise WorkspaceInitError("workspace name must be lowercase kebab-case, for example my-notes")

    enclosing = _enclosing_workspace(target)
    if enclosing is not None:
        raise WorkspaceInitError(
            f"{target} is inside the existing workspace {enclosing}; choose a folder outside it"
        )
    created = False
    if target.exists():
        if not target.is_dir():
            raise WorkspaceInitError(f"{target} exists and is not a directory")
        if (target / MARKER).exists():
            raise WorkspaceInitError(f"{target} already contains a Knowledge OS workspace")
        if any(target.iterdir()):
            raise WorkspaceInitError(f"{target} is not empty; choose an empty or new folder")
    else:
        target.mkdir(parents=True)
        created = True

    try:
        for directory in LAYOUT_DIRS:
            (target / directory).mkdir()
            readme = README_CONTENT.get(directory)
            if readme is not None:
                exclusive_write(target / directory / "README.md", readme.encode("utf-8"))
        exclusive_write(target / ".gitignore", GITIGNORE_CONTENT.encode("utf-8"))
        # The marker is written last: a failure before this point leaves no
        # half-made folder that other commands would mistake for a workspace.
        exclusive_write(target / MARKER, f'[workspace]\nname = "{workspace_name}"\nversion = 1\n'.encode("utf-8"))
        # Validates the whole new corpus before writing the empty indexes.
        rebuild_indexes(Workspace(target))
    except (OSError, sqlite3.Error, ValueError) as exc:
        if created:
            shutil.rmtree(target, ignore_errors=True)
        raise WorkspaceInitError(f"could not create workspace at {target}: {exc}") from exc
    return target
