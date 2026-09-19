"""Structural acceptance tests for the Knowledge OS Reader (unit 11).

Covers the acceptance criteria from ``docs/plans/reader-v1.md`` Sec.8 that
are structural rather than view-specific:

- Criterion 1: ``kos-read --root .`` serves the real workspace this
  repository is, and the workspace is byte-identical afterwards, including
  every route and a clean ``git status``.
- Criterion 12: ``kos lint`` and the core package work unchanged, and a
  plain ``pip install -e .`` (no ``[reader]`` extra) neither pulls in the
  reader's dependencies nor leaves ``kos-read`` raising a raw
  ``ImportError`` when its dependencies are missing.

Criteria 2-11 are view-specific and belong to the units that own those
views; they are not duplicated here. Follows the repository's convention:
unittest only, workspaces built on disk in a ``tempfile.TemporaryDirectory()``,
never a mutation of the real workspace this suite runs from.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
import venv
from pathlib import Path

from reader_support import serve

from knowledge_os.reader.cli import MISSING_EXTRA

REPOSITORY = Path(__file__).resolve().parents[1]

#: This unit's assigned end-to-end port (see the batch brief: ten sibling
#: agents each own a distinct port; this one is 8822).
PORT = 8822

#: Tooling/environment artifacts that are not part of "the workspace" a
#: person reads: bytecode caches and editable-install metadata are a
#: side effect of running Python at all (via `kos lint`, `kos-read`, or this
#: very test process importing knowledge_os), not of the reader's request
#: handling, and are already git-ignored (see .gitignore). Any scratch venv
#: this suite itself creates is excluded the same way.
_ARTIFACT_DIR_NAMES = {".git", "__pycache__", "knowledge_os.egg-info", ".venv-reader", ".venv", ".pytest_cache"}


def _workspace_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    """Map every real-workspace file under root to (content, mtime_ns),
    skipping tooling/environment artifacts (see _ARTIFACT_DIR_NAMES)."""

    snapshot: dict[str, tuple[bytes, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _ARTIFACT_DIR_NAMES & set(relative.parts):
            continue
        stat = path.stat()
        snapshot[relative.as_posix()] = (path.read_bytes(), stat.st_mtime_ns)
    return snapshot


def _git(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], cwd=cwd, text=True, capture_output=True, check=False)


def _run_kos(*arguments: str, cwd: Path = REPOSITORY, python: str | None = None) -> subprocess.CompletedProcess[str]:
    executable = python or sys.executable
    return subprocess.run(
        [executable, "-m", "knowledge_os", *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


class ServeRealWorkspaceByteIdenticalTests(unittest.TestCase):
    """Acceptance criterion 1: `kos-read --root .` serves the library, every
    route answers, and the workspace this repository is stays byte-identical
    afterwards with a clean `git status`."""

    def test_kos_read_serves_the_repository_and_leaves_it_untouched(self) -> None:
        status_before = _git("status", "--porcelain", cwd=REPOSITORY)
        self.assertEqual(status_before.returncode, 0, status_before.stderr)
        # This worktree is expected to start clean (only this suite's own
        # untracked test files, which the byte-identity check below is
        # indifferent to since it compares before/after, not against zero).
        before = _workspace_snapshot(REPOSITORY)

        with serve(REPOSITORY, PORT) as base_url:
            routes = [
                "/",
                "/p/knowledge-os",
                "/r/knowledge-os-reader",
                "/r/knowledge-os-reader/compare",
                "/s/ingest-source",
                "/f/README.md",
                "/search?q=reader",
                "/everything",
                "/api/workspace",
                "/api/nav",
                "/api/home",
                "/api/projects/knowledge-os",
                "/api/records/knowledge-os-reader",
                "/api/records/knowledge-os-reader/compare",
                "/api/skills/ingest-source",
                "/api/docs/README.md",
                "/api/search?q=reader",
                "/api/everything",
            ]
            self.assertEqual(len(routes), 18, "nine client routes plus their nine JSON API counterparts")
            for route in routes:
                with self.subTest(route=route):
                    with urllib.request.urlopen(base_url + route, timeout=5) as response:
                        self.assertLess(response.status, 500, f"{route} must not 500")

        after = _workspace_snapshot(REPOSITORY)
        new_files = set(after) - set(before)
        missing_files = set(before) - set(after)
        self.assertEqual(new_files, set(), "no new file may appear anywhere under the workspace")
        self.assertEqual(missing_files, set(), "no file may disappear")
        changed = {path for path in before if before[path] != after.get(path)}
        self.assertEqual(changed, set(), "every file must be byte-identical, including mtime")

        status_after = _git("status", "--porcelain", cwd=REPOSITORY)
        self.assertEqual(status_after.stdout, status_before.stdout, "git status must be unchanged by serving")


class CoreUnaffectedByTheReaderTests(unittest.TestCase):
    """Acceptance criterion 12, first half: `kos lint` (and by extension the
    core) keeps working exactly as before the reader package was added."""

    def test_kos_lint_passes_on_the_real_workspace(self) -> None:
        result = _run_kos("lint", cwd=REPOSITORY)
        self.assertEqual(result.returncode, 0, result.stderr)
        # The corpus is 13 managed records as of this batch (all under
        # projects/knowledge-os/); if a future change grows the corpus this
        # assertion should move with it, not be loosened to a regex that
        # would silently stop verifying the number at all.
        self.assertEqual(result.stdout.strip(), "Lint OK: 13 managed record(s)")


class PlainInstallExcludesTheReaderTests(unittest.TestCase):
    """Acceptance criterion 12, second half: a plain `pip install -e .`
    installs `kos-read` (the console script is unconditional — see
    pyproject.toml [project.scripts]) but not the reader's dependencies, and
    running it without them reports what to install instead of raising a
    raw ImportError.

    Builds one throwaway venv for the whole class (expensive: a fresh
    interpreter plus an editable install), shared by both assertions.
    """

    scratch_dir: tempfile.TemporaryDirectory
    scratch_root: Path
    scratch_python: Path
    #: Set when the scratch venv was built with `uv` (pip-less venv; package
    #: listing must go through `uv pip list` rather than `python -m pip`).
    uv_executable: str | None

    @classmethod
    def setUpClass(cls) -> None:
        cls.scratch_dir = tempfile.TemporaryDirectory(prefix="kos-plain-install-")
        cls.scratch_root = Path(cls.scratch_dir.name)
        cls.scratch_python, cls.uv_executable = cls._build_scratch_venv(cls.scratch_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.scratch_dir.cleanup()

    @staticmethod
    def _build_scratch_venv(root: Path) -> tuple[Path, str | None]:
        uv = shutil.which("uv") or (
            r"C:\Users\lucas\.local\bin\uv" if Path(r"C:\Users\lucas\.local\bin\uv").is_file() else None
        )
        venv_dir = root / "venv"
        if uv is not None:
            created = subprocess.run(
                [uv, "venv", str(venv_dir), "--python", "3.11"],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                raise RuntimeError(f"uv venv failed: {created.stderr}")
            python = venv_dir / "Scripts" / "python.exe"
            if not python.is_file():
                python = venv_dir / "bin" / "python"
            installed = subprocess.run(
                [uv, "pip", "install", "--python", str(python), "-e", "."],
                cwd=REPOSITORY,
                text=True,
                capture_output=True,
                check=False,
            )
            if installed.returncode != 0:
                raise RuntimeError(f"uv pip install failed: {installed.stderr}")
            return python, uv
        # Fallback: stdlib venv + its bundled pip, per the unit brief.
        venv.EnvBuilder(with_pip=True).create(str(venv_dir))
        python = venv_dir / "Scripts" / "python.exe"
        if not python.is_file():
            python = venv_dir / "bin" / "python"
        installed = subprocess.run(
            [str(python), "-m", "pip", "install", "-e", "."],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
        )
        if installed.returncode != 0:
            raise RuntimeError(f"pip install failed: {installed.stderr}")
        return python, None

    def test_plain_install_pulls_in_only_pyyaml(self) -> None:
        if self.uv_executable is not None:
            # uv-created venvs have no pip module installed inside them
            # (uv itself performs installs); list packages the same way.
            listing = subprocess.run(
                [self.uv_executable, "pip", "list", "--python", str(self.scratch_python), "--format=json"],
                text=True,
                capture_output=True,
                check=False,
            )
        else:
            listing = subprocess.run(
                [str(self.scratch_python), "-m", "pip", "list", "--format=json"],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(listing.returncode, 0, listing.stderr)
        names = {entry["name"].lower() for entry in json.loads(listing.stdout)}
        self.assertIn("knowledge-os", names)
        self.assertIn("pyyaml", names)
        reader_only_deps = {"starlette", "uvicorn", "jinja2", "markdown-it-py", "markdown_it_py", "pygments"}
        self.assertEqual(names & reader_only_deps, set(), f"plain install must not pull reader deps: {names}")

    def test_kos_lint_still_works_from_a_plain_install(self) -> None:
        result = _run_kos("lint", cwd=REPOSITORY, python=str(self.scratch_python))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "Lint OK: 13 managed record(s)")

    def test_kos_read_command_exists_but_reports_missing_dependencies_cleanly(self) -> None:
        script = self.scratch_python.parent / "kos-read.exe"
        if not script.is_file():
            script = self.scratch_python.parent / "kos-read"
        self.assertTrue(
            script.is_file(),
            "kos-read must be installed by a plain `pip install -e .` "
            "([project.scripts] installs it unconditionally); its "
            "dependencies, not the command itself, are what's missing",
        )
        result = subprocess.run(
            [str(script), "--root", str(REPOSITORY), "--port", "8829"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn(MISSING_EXTRA, result.stderr)
        self.assertNotIn("Traceback", result.stderr, "must report the gap, not a raw ImportError stack trace")


if __name__ == "__main__":
    unittest.main()
