"""Read-only hardening tests for the Knowledge OS Reader.

This is the regression suite for unit 11's audit: every filesystem and
SQLite access the reader makes must be read-only in intent and in effect.
Three kinds of proof live here:

1. Structural import checks (``ImportCheckerSelfTest`` and
   ``OneAdapterRuleTests``) that walk the reader package's own source with
   ``ast`` rather than trust a comment. ``ImportCheckerSelfTest`` proves the
   checker functions actually fire on synthetic bad code, so the regression
   tests that follow are not checking a rule that can never fail.
2. Functional byte-identity checks (``LibraryReadOnlyTests``,
   ``SearchReadOnlyTests``) that call the adapter directly and diff the
   workspace before and after.
3. One end-to-end check (``ServeReadOnlyTests``) that starts the real
   ``kos-read`` server, exercises every route, and diffs the whole workspace
   plus ``git status``.

Follows the repository's convention: unittest only, no pytest, no fixtures,
workspaces built on disk in a ``tempfile.TemporaryDirectory()``. Never
mutates the real workspace this repository lives in.
"""

from __future__ import annotations

import ast
import subprocess
import tempfile
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace

REPOSITORY = Path(__file__).resolve().parents[1]
READER_PACKAGE = REPOSITORY / "knowledge_os" / "reader"
#: The JSON API package replaces the old Jinja "views" package one-for-one:
#: every endpoint module in it is a non-adapter module, exactly like the
#: HTML views were (see api/__init__.py's own docstring).
API_PACKAGE = READER_PACKAGE / "api"
LIBRARY_MODULE = READER_PACKAGE / "library.py"

#: The reader's assigned end-to-end port for this unit. Ten sibling agents
#: are each assigned a different port; this one is 8822.
PORT = 8822

#: The core's write modules. The editable-interface decision lets the
#: interface write, but only through the core's own mutations and only from
#: the one adapter: ``library.py`` may import exactly the names in
#: ``ADAPTER_WRITE_ENTRY_POINTS``; every other reader module, and every other
#: name, stays forbidden.
FORBIDDEN_MODULES = {
    "knowledge_os.capture",
    "knowledge_os.ingest",
    "knowledge_os.mutations",
    "knowledge_os.discovery",
    "knowledge_os.documentation_init",
    "knowledge_os.structure",
}
ADAPTER_WRITE_ENTRY_POINTS = {
    "knowledge_os.capture": {
        "CAPTURE_DIRECTORIES",
        "CaptureError",
        "CaptureIndexError",
        "DuplicateRecordError",
        "capture_record_text",
    },
    "knowledge_os.mutations": {
        "MutationError",
        "MutationIndexError",
        "RecordNotFoundError",
        "StaleRevisionError",
        "SupersedeIndexError",
        "accept_decision",
        "supersede_decision",
        "update_record_text",
        "withdraw_decision",
    },
    "knowledge_os.structure": {
        "ChangedFile",
        "StructureIndexError",
        "StructureResult",
        "clean_folder",
        "create_folder",
        "create_project",
        "move_folder",
        "move_record",
        "rename_record",
    },
}
FORBIDDEN_WORKSPACE_NAMES = {
    "atomic_write",
    "exclusive_write",
    "stage_workspace",
    "refresh_derived_indexes",
    "workspace_mutation_lock",
}
#: The core's index module has two read-write-adjacent siblings
#: (``search_index`` opens the catalog with a bare read-write
#: ``sqlite3.connect``; ``rebuild_indexes``/``search_index_terms`` either
#: write or are not what the adapter is meant to use). ``library.search``
#: must issue its own ``mode=ro`` connection instead of importing any of
#: these.
FORBIDDEN_INDEX_NAMES = {"search_index", "search_index_terms", "rebuild_indexes"}

#: Every module the reader package's non-adapter modules are allowed to
#: import from ``knowledge_os`` at all: the opaque workspace handle used to
#: discover a root and bind a server to it (``app.py``, ``cli.py``), never a
#: data-shaping function. This is the "views never import the core
#: directly" rule from the decision record's Boundaries section, applied
#: precisely: ``library.py`` is the one adapter; ``app.py``/``cli.py`` carry
#: the workspace handle as plumbing, and every ``views/*.py`` module is
#: completely clean of ``knowledge_os`` imports.
ALLOWED_WORKSPACE_HANDLE_NAMES = {"Workspace", "WorkspaceError"}


# ---------------------------------------------------------------------------
# AST-based import checking
# ---------------------------------------------------------------------------


def _imported_modules(tree: ast.Module) -> set[str]:
    """Every module named by a top-level ``import`` or ``from ... import``."""

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _names_imported_from(tree: ast.Module, module: str) -> set[str]:
    """Names pulled in via ``from <module> import name[, ...]`` (exact module
    match; a relative import never matches, since ``node.module`` excludes
    the leading dots and this repository's reader package never re-exports
    ``knowledge_os`` symbols through a relative alias)."""

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module and node.level == 0:
            names.update(alias.name for alias in node.names)
    return names


def knowledge_os_imports(tree: ast.Module) -> set[str]:
    """Every ``knowledge_os`` or ``knowledge_os.*`` module imported by ``tree``."""

    return {
        module
        for module in _imported_modules(tree)
        if module == "knowledge_os" or module.startswith("knowledge_os.")
    }


def forbidden_write_path_violations(
    tree: ast.Module, allowed: dict[str, set[str]] | None = None
) -> set[str]:
    """Every forbidden module or write-path name imported by ``tree``, as a
    human-readable label. Applies to the whole reader package. ``allowed``
    names the only ``from <module> import name`` imports a module may make
    from a forbidden module (``ADAPTER_WRITE_ENTRY_POINTS`` for
    ``library.py``); a bare ``import <module>`` is never allowed."""

    allowed = allowed or {}
    violations: set[str] = set()
    imported = _imported_modules(tree)
    bare_imports = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    for module in FORBIDDEN_MODULES:
        if module not in imported:
            continue
        extra_names = _names_imported_from(tree, module) - allowed.get(module, set())
        if module in bare_imports or module not in allowed:
            violations.add(f"import {module}")
        for name in extra_names:
            violations.add(f"from {module} import {name}")
    workspace_names = _names_imported_from(tree, "knowledge_os.workspace")
    for name in workspace_names & FORBIDDEN_WORKSPACE_NAMES:
        violations.add(f"from knowledge_os.workspace import {name}")
    index_names = _names_imported_from(tree, "knowledge_os.index")
    for name in index_names & FORBIDDEN_INDEX_NAMES:
        violations.add(f"from knowledge_os.index import {name}")
    return violations


def non_adapter_violations(tree: ast.Module) -> set[str]:
    """Imports a *non-adapter* reader module (anything but ``library.py``) is
    not allowed to have: any ``knowledge_os.*`` import beyond the bare
    workspace handle (``Workspace``/``WorkspaceError`` from
    ``knowledge_os.workspace``)."""

    violations: set[str] = set()
    for module in knowledge_os_imports(tree):
        if module != "knowledge_os.workspace":
            violations.add(f"import {module}")
    handle_names = _names_imported_from(tree, "knowledge_os.workspace")
    for name in handle_names - ALLOWED_WORKSPACE_HANDLE_NAMES:
        violations.add(f"from knowledge_os.workspace import {name}")
    return violations


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class ImportCheckerSelfTest(unittest.TestCase):
    """Prove the checker functions above actually fire on a violation, so the
    regression tests in ``OneAdapterRuleTests`` and
    ``ForbiddenWritePathTests`` are not exercising a rule that can never
    fail. Each case parses a synthetic snippet, not a file on disk."""

    def test_forbidden_module_import_is_detected(self) -> None:
        tree = ast.parse("import knowledge_os.capture\n")
        self.assertIn("import knowledge_os.capture", forbidden_write_path_violations(tree))

    def test_forbidden_module_import_via_from_is_detected(self) -> None:
        tree = ast.parse("from knowledge_os import discovery\n")
        # `from knowledge_os import discovery` imports module "knowledge_os",
        # not "knowledge_os.discovery"; the *name* discovery is not one of
        # the tracked workspace/index names, so this specific phrasing is not
        # caught by forbidden_write_path_violations. It IS caught as a bare
        # knowledge_os import by knowledge_os_imports / non_adapter_violations.
        self.assertIn("import knowledge_os", non_adapter_violations(tree))

    def test_forbidden_workspace_write_function_is_detected(self) -> None:
        tree = ast.parse("from knowledge_os.workspace import atomic_write\n")
        self.assertIn(
            "from knowledge_os.workspace import atomic_write",
            forbidden_write_path_violations(tree),
        )

    def test_forbidden_index_write_function_is_detected(self) -> None:
        tree = ast.parse("from knowledge_os.index import search_index\n")
        self.assertIn(
            "from knowledge_os.index import search_index",
            forbidden_write_path_violations(tree),
        )

    def test_benign_workspace_handle_import_is_not_flagged(self) -> None:
        tree = ast.parse("from knowledge_os.workspace import Workspace, WorkspaceError\n")
        self.assertEqual(forbidden_write_path_violations(tree), set())
        self.assertEqual(non_adapter_violations(tree), set())

    def test_non_adapter_module_importing_the_core_directly_is_detected(self) -> None:
        tree = ast.parse("from knowledge_os.model import Document\n")
        self.assertIn("import knowledge_os.model", non_adapter_violations(tree))

    def test_non_adapter_module_importing_a_write_function_is_detected(self) -> None:
        tree = ast.parse("from knowledge_os.workspace import Workspace, atomic_write\n")
        self.assertIn(
            "from knowledge_os.workspace import atomic_write",
            non_adapter_violations(tree),
        )

    def test_relative_import_is_never_mistaken_for_a_core_import(self) -> None:
        tree = ast.parse("from . import strings\nfrom ..app import get_library\n")
        self.assertEqual(knowledge_os_imports(tree), set())
        self.assertEqual(non_adapter_violations(tree), set())


class OneAdapterRuleTests(unittest.TestCase):
    """``library.py`` is the only module in the package permitted to import
    ``knowledge_os.*`` beyond the bare workspace handle. Every ``api/*.py``
    endpoint module must be completely clean; ``app.py`` and ``cli.py`` may
    carry the handle only."""

    def test_every_api_module_is_free_of_knowledge_os_imports(self) -> None:
        api_files = sorted(API_PACKAGE.glob("*.py"))
        self.assertGreater(len(api_files), 0, "expected API endpoint modules to exist")
        for path in api_files:
            with self.subTest(module=path.name):
                violations = knowledge_os_imports(_parse(path))
                self.assertEqual(violations, set(), f"{path.name} imports knowledge_os directly: {violations}")

    def test_markdown_and_strings_are_free_of_knowledge_os_imports(self) -> None:
        for name in ("markdown.py", "strings.py", "__init__.py", "__main__.py"):
            path = READER_PACKAGE / name
            with self.subTest(module=name):
                violations = knowledge_os_imports(_parse(path))
                self.assertEqual(violations, set(), f"{name} imports knowledge_os directly: {violations}")

    def test_app_and_cli_carry_only_the_workspace_handle(self) -> None:
        for name in ("app.py", "cli.py"):
            path = READER_PACKAGE / name
            with self.subTest(module=name):
                violations = non_adapter_violations(_parse(path))
                self.assertEqual(violations, set(), f"{name} reaches beyond the workspace handle: {violations}")

    def test_library_is_the_only_module_with_broad_knowledge_os_access(self) -> None:
        """Walk the whole package (recursively, skipping __pycache__) and
        confirm no file other than library.py imports anything from
        knowledge_os beyond Workspace/WorkspaceError."""

        offenders: dict[str, set[str]] = {}
        for path in sorted(READER_PACKAGE.rglob("*.py")):
            if path == LIBRARY_MODULE or "__pycache__" in path.parts:
                continue
            violations = non_adapter_violations(_parse(path))
            if violations:
                offenders[str(path.relative_to(REPOSITORY))] = violations
        self.assertEqual(offenders, {}, f"non-adapter modules reaching into knowledge_os: {offenders}")


class ForbiddenWritePathTests(unittest.TestCase):
    """None of capture/ingest/mutations/discovery/documentation_init, nor
    the five workspace write functions, nor the core's read-write search
    helpers, are reachable from anywhere in the reader package, except the
    adapter's named capture, update, and decision\r
    lifecycle entry points."""

    def test_the_adapter_allowance_does_not_admit_other_names(self) -> None:
        allowed = ADAPTER_WRITE_ENTRY_POINTS
        tree = ast.parse("from knowledge_os.mutations import update_record\n")
        self.assertIn(
            "from knowledge_os.mutations import update_record",
            forbidden_write_path_violations(tree, allowed),
        )
        tree = ast.parse("import knowledge_os.capture\n")
        self.assertIn("import knowledge_os.capture", forbidden_write_path_violations(tree, allowed))
        tree = ast.parse("from knowledge_os.capture import capture_record_text\n")
        self.assertEqual(forbidden_write_path_violations(tree, allowed), set())

    def test_no_file_in_the_reader_package_imports_a_forbidden_write_path(self) -> None:
        offenders: dict[str, set[str]] = {}
        for path in sorted(READER_PACKAGE.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            allowed = ADAPTER_WRITE_ENTRY_POINTS if path == LIBRARY_MODULE else None
            violations = forbidden_write_path_violations(_parse(path), allowed)
            if violations:
                offenders[str(path.relative_to(REPOSITORY))] = violations
        self.assertEqual(offenders, {}, f"forbidden write paths imported: {offenders}")

    def test_library_only_imports_validate_index_from_the_index_module(self) -> None:
        """The audit's specific concern: library.py must never import
        index.search_index (bare read-write sqlite3.connect) or
        index.rebuild_indexes; it issues its own mode=ro connection."""

        names = _names_imported_from(_parse(LIBRARY_MODULE), "knowledge_os.index")
        self.assertEqual(names, {"validate_index"})


# ---------------------------------------------------------------------------
# load_library must never cache across calls (acceptance criterion 8)
# ---------------------------------------------------------------------------


class LoadLibraryNoCachingTests(unittest.TestCase):
    def test_load_library_has_no_memoization_decorator(self) -> None:
        # functools.lru_cache/cache wrap the function with a cache_info()
        # method; a plain function has no such attribute. This is a cheap
        # introspection check alongside the functional proof below.
        self.assertFalse(hasattr(library.load_library, "cache_info"))
        self.assertNotIn("functools", _imported_modules(_parse(LIBRARY_MODULE)))

    def test_load_library_reflects_an_edit_made_between_two_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(
                root,
                "knowledge/plain.md",
                {
                    "id": "plain",
                    "title": "Plain",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "plain"}],
                },
                body="Original body.\n",
            )
            workspace = Workspace(root)
            first = library.load_library(workspace)
            self.assertIn("Original body.", first.records_by_id["plain"].body)

            path.write_text(
                path.read_text(encoding="utf-8").replace("Original body.", "Edited body."),
                encoding="utf-8",
            )

            second = library.load_library(workspace)
            self.assertIn("Edited body.", second.records_by_id["plain"].body)
            self.assertNotIn("Edited body.", first.records_by_id["plain"].body)


# ---------------------------------------------------------------------------
# Functional byte-identity: the adapter itself never mutates the workspace
# ---------------------------------------------------------------------------


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    """Map every file under root (recursively) to (content, mtime_ns)."""

    snapshot: dict[str, tuple[bytes, int]] = {}
    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            snapshot[path.relative_to(root).as_posix()] = (path.read_bytes(), stat.st_mtime_ns)
    return snapshot


def _knowledge_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "demo",
        "title": "Demo",
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "tags": ["xylophone"],
        "provenance": [{"kind": "fixture", "reference": "demo"}],
    }
    metadata.update(overrides)
    return metadata


class LibraryReadOnlyTests(unittest.TestCase):
    """Calling load_library and read_repo_document repeatedly, including on
    the broken/unresolved/unsafe paths, must never change a byte or an mtime
    anywhere under the workspace, and must never create a new file."""

    def test_repeated_load_library_leaves_the_workspace_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/good.md", _knowledge_metadata(id="good", related=["missing"]))
            (root / "knowledge" / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")
            (root / "NOTES.md").write_text("# Notes\n\nUnmanaged tier content.\n", encoding="utf-8")
            workspace = Workspace(root)

            before = _snapshot(root)
            for _ in range(3):
                library.load_library(workspace)
            after = _snapshot(root)

            self.assertEqual(before, after)

    def test_read_repo_document_on_every_kind_of_path_leaves_no_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "NOTES.md").write_text("# Notes\n\nBody.\n", encoding="utf-8")
            workspace = Workspace(root)

            before = _snapshot(root)
            # Existing file.
            library.read_repo_document(workspace, "NOTES.md")
            # Missing file: raises LibraryError, must still touch nothing.
            with self.assertRaises(library.LibraryError):
                library.read_repo_document(workspace, "missing.md")
            # Escape attempt: raises LibraryError via assert_safe_path.
            with self.assertRaises(library.LibraryError):
                library.read_repo_document(workspace, "../outside.md")
            after = _snapshot(root)

            self.assertEqual(before, after)
            self.assertEqual(set(before), set(after), "no new file may appear")


class SearchReadOnlyTests(unittest.TestCase):
    """library.search issues its own mode=ro SQLite connection; verify that
    in effect, not just by reading the source: no -journal/-wal/-shm file
    ever appears beside the catalog, and its bytes and mtime never move,
    across a spread of query shapes including ones likely to touch SQLite's
    write path if the connection were not truly read-only."""

    def test_repeated_search_never_creates_a_journal_or_moves_the_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain", title="Plain"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)  # test setup, not the reader, builds the index

            database = root / "indexes" / "catalog.sqlite3"
            self.assertTrue(database.is_file())
            before = _snapshot(root)

            queries = [
                "xylophone",  # no match
                "plain",  # a match
                '"quoted phrase"',  # already-quoted input
                'has "double" quotes',  # needs internal escaping
                "   ",  # blank after stripping
                "*",  # FTS syntax that could raise OperationalError
                "AND OR NOT",  # FTS boolean keywords with no operands
            ]
            for query in queries:
                library.search(workspace, query)

            after = _snapshot(root)
            self.assertEqual(before, after)
            sibling_files = {path.name for path in database.parent.iterdir()}
            self.assertEqual(
                sibling_files & {"catalog.sqlite3-journal", "catalog.sqlite3-wal", "catalog.sqlite3-shm"},
                set(),
                "search must never leave a rollback journal or WAL file beside the catalog",
            )

    def test_search_against_a_missing_or_corrupt_database_leaves_no_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _knowledge_metadata(id="plain"))
            workspace = Workspace(root)

            # No index built at all.
            before = _snapshot(root)
            self.assertEqual(library.search(workspace, "plain"), [])
            self.assertEqual(_snapshot(root), before)
            self.assertNotIn("indexes/catalog.sqlite3", before)
            self.assertEqual(set(_snapshot(root)), set(before))

            # A corrupt (non-SQLite) file at the catalog path.
            (root / "indexes" / "catalog.sqlite3").write_bytes(b"not a real sqlite database")
            before = _snapshot(root)
            self.assertEqual(library.search(workspace, "plain"), [])
            self.assertEqual(_snapshot(root), before)


# ---------------------------------------------------------------------------
# End to end: the real kos-read server, every route, whole-workspace diff
# ---------------------------------------------------------------------------


def _build_serving_workspace(root: Path) -> None:
    """A small but complete workspace exercising every route: a project with
    a governing decision and a proposed one, an ordinary knowledge record, a
    source, a skill, and one unmanaged repo-document file."""

    create_workspace(root)
    write_record(
        root,
        "projects/demo/README.md",
        {
            "id": "demo",
            "title": "Demo project",
            "type": "project",
            "status": "active",
            "scope": "project:demo",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": "demo"}],
        },
    )
    write_record(
        root,
        "projects/demo/decisions/accepted.md",
        {
            "id": "accepted",
            "title": "Accepted decision",
            "type": "project",
            "status": "active",
            "scope": "project:demo",
            "record_kind": "decision",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [
                {
                    "kind": "decision-acceptance",
                    "reference": "conversation:2026-08-30:accepted",
                    "captured": "2026-08-30T00:00:00Z",
                }
            ],
        },
    )
    write_record(
        root,
        "projects/demo/decisions/proposed.md",
        {
            "id": "proposed",
            "title": "Proposed decision",
            "type": "project",
            "status": "draft",
            "scope": "project:demo",
            "record_kind": "decision",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": "proposed"}],
        },
    )
    write_record(root, "knowledge/note.md", _knowledge_metadata(id="note", title="Note"))
    write_record(
        root,
        "sources/raw.md",
        {
            "id": "raw",
            "title": "Raw source",
            "type": "source",
            "status": "active",
            "scope": "general",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": "raw"}],
        },
    )
    skill_dir = root / "skills" / "demo-skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: A demo skill for the read-only e2e test.\n---\n\nBody.\n",
        encoding="utf-8",
    )
    (root / "SYSTEM.md").write_text("# Notes\n\nUnmanaged tier content.\n", encoding="utf-8")


def _git(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=cwd, text=True, capture_output=True, check=False)


class ServeReadOnlyTests(unittest.TestCase):
    """Start the real kos-read server, hit all nine routes, and confirm the
    workspace is untouched: byte-identical content and mtimes, a clean git
    status, and no new file anywhere under the root."""

    def test_serving_every_route_leaves_a_git_workspace_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _build_serving_workspace(root)

            init = _git("init", "-q", cwd=root)
            self.assertEqual(init.returncode, 0, init.stderr)
            _git("config", "user.email", "test@example.invalid", cwd=root)
            _git("config", "user.name", "Reader Test", cwd=root)
            add = _git("add", "-A", cwd=root)
            self.assertEqual(add.returncode, 0, add.stderr)
            commit = _git("commit", "-q", "-m", "initial", cwd=root)
            self.assertEqual(commit.returncode, 0, commit.stderr)

            status_before = _git("status", "--porcelain", cwd=root)
            self.assertEqual(status_before.stdout, "")

            # Snapshot everything except .git: git's own index cache can
            # legitimately refresh its stat cache (touching .git/index) when
            # `git status` runs, which is git's bookkeeping, not the
            # workspace the reader serves.
            def workspace_snapshot() -> dict[str, tuple[bytes, int]]:
                return {
                    path: value
                    for path, value in _snapshot(root).items()
                    if not path.startswith(".git/") and path != ".git"
                }

            before = workspace_snapshot()

            with serve(root, PORT) as base_url:
                routes = [
                    "/",
                    "/p/demo",
                    "/r/accepted",
                    "/r/accepted/compare",
                    "/s/demo-skill",
                    "/f/SYSTEM.md",
                    "/search?q=note",
                    "/everything",
                    "/api/session",
                    "/api/workspace",
                    "/api/nav",
                    "/api/home",
                    "/api/projects/demo",
                    "/api/records/accepted",
                    "/api/records/accepted/compare",
                    "/api/skills/demo-skill",
                    "/api/docs/SYSTEM.md",
                    "/api/search?q=note",
                    "/api/everything",
                ]
                for route in routes:
                    with self.subTest(route=route):
                        with urllib.request.urlopen(base_url + route, timeout=5) as response:
                            self.assertLess(
                                response.status,
                                500,
                                f"{route} must not 500",
                            )

            after = workspace_snapshot()
            self.assertEqual(set(before), set(after), "no new file may appear under the workspace")
            self.assertEqual(before, after, "every file must be byte-identical, including mtime")

            status_after = _git("status", "--porcelain", cwd=root)
            self.assertEqual(status_after.stdout, "", "git status must stay clean after serving")


if __name__ == "__main__":
    unittest.main()
