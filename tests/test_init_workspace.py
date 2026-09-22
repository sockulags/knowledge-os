"""Tests for ``kos init``: creating a workspace outside this repository.

Covers issue #22: a new workspace passes ``kos lint``, every refusal case
leaves the filesystem untouched, and ``kos-read --root`` serves a freshly
created workspace in a temporary directory without reading any file from
this repository's own workspace.
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, serve

from knowledge_os.cli import main as kos_main
from knowledge_os.init_workspace import LAYOUT_DIRS, README_CONTENT, WorkspaceInitError, init_workspace
from knowledge_os.reader.app import STATIC_APP_DIR

#: This module's own end-to-end port, distinct from every other reader test
#: module's fixed port.
PORT = 8840


def _kos(*argv: str) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = kos_main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


def _snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes() if item.is_file() else b"<dir>"
        for item in sorted(path.rglob("*"))
    }


class InitWorkspaceTests(unittest.TestCase):
    def test_cli_creates_a_workspace_that_passes_lint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "outside-repo-kb"
            code, out, err = _kos("init", str(target), "--json")
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out), {"root": str(target.resolve())})

            self.assertEqual(
                (target / "knowledge-os.toml").read_text(encoding="utf-8"),
                '[workspace]\nname = "outside-repo-kb"\nversion = 1\n',
            )
            for directory in LAYOUT_DIRS:
                self.assertTrue((target / directory).is_dir(), f"missing {directory}/")
            self.assertIn("indexes/catalog.sqlite3", (target / ".gitignore").read_text(encoding="utf-8"))
            self.assertTrue((target / "indexes" / "catalog.sqlite3").is_file())
            self.assertTrue((target / "indexes" / "catalog.md").is_file())

            code, out, err = _kos("--root", str(target), "lint")
            self.assertEqual((code, err), (0, ""))
            self.assertIn("Lint OK: 0 managed record(s)", out)
            code, _out, err = _kos("--root", str(target), "index")
            self.assertEqual(code, 0, err)

    def test_readmes_match_this_repository(self) -> None:
        for directory, content in README_CONTENT.items():
            with self.subTest(directory=directory):
                repo_text = (REPOSITORY / directory / "README.md").read_text(encoding="utf-8")
                self.assertEqual(content, repo_text.replace("\r\n", "\n"))

    def test_creates_missing_parents_and_derives_the_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "My Personal KB"
            init_workspace(target)
            self.assertIn('name = "my-personal-kb"', (target / "knowledge-os.toml").read_text(encoding="utf-8"))

    def test_accepts_an_existing_empty_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            created = init_workspace(Path(tmp), name="empty-folder")
            self.assertTrue((created / "knowledge-os.toml").is_file())

    def test_refuses_a_non_empty_folder_without_touching_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "occupied"
            target.mkdir()
            (target / "existing-file.txt").write_text("hello", encoding="utf-8")
            before = _snapshot(target)
            code, _out, err = _kos("init", str(target))
            self.assertEqual(code, 1)
            self.assertIn("is not empty", err)
            self.assertEqual(_snapshot(target), before)

    def test_refuses_an_existing_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "already-a-workspace"
            init_workspace(target)
            before = _snapshot(target)
            with self.assertRaisesRegex(WorkspaceInitError, "already contains a Knowledge OS workspace"):
                init_workspace(target)
            self.assertEqual(_snapshot(target), before)

    def test_refuses_a_folder_inside_another_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outer = init_workspace(Path(tmp) / "outer")
            before = _snapshot(outer)
            with self.assertRaisesRegex(WorkspaceInitError, "inside the existing workspace"):
                init_workspace(outer / "knowledge" / "inner")
            self.assertEqual(_snapshot(outer), before)

    def test_refuses_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a-file"
            target.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(WorkspaceInitError, "not a directory"):
                init_workspace(target)

    def test_refuses_an_invalid_name_before_creating_anything(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "new-kb"
            with self.assertRaisesRegex(WorkspaceInitError, "kebab-case"):
                init_workspace(target, name='Bad "Name"')
            self.assertFalse(target.exists())


class ReaderServesNewWorkspaceTests(unittest.TestCase):
    def test_reader_serves_a_freshly_created_workspace_in_a_temp_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = init_workspace(Path(tmp) / "fresh-kb")

            # The child runs from the system temp directory, not from this
            # repository, so cwd discovery cannot reach the repository's own
            # knowledge-os.toml.
            with serve(root, PORT, cwd=Path(tempfile.gettempdir())) as base_url:
                with urllib.request.urlopen(f"{base_url}/api/workspace") as response:
                    workspace = json.loads(response.read())
                self.assertEqual(workspace["name"], "fresh-kb")
                self.assertTrue(workspace["health"]["lint_ok"])
                self.assertTrue(workspace["health"]["index_available"])
                self.assertFalse(workspace["health"]["search_disabled"])

                with urllib.request.urlopen(f"{base_url}/api/nav") as response:
                    nav = json.loads(response.read())
                self.assertEqual((nav["projects"], nav["skills"], nav["repo_docs"]), ([], [], []))
                self.assertEqual(nav["record_index"], [])

                # This repository's README.md is in the repository-document
                # tier; the new workspace has none, so it must not be served.
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(f"{base_url}/api/docs/README.md")
                self.assertEqual(caught.exception.code, 404)

                # The UI shell is the package's built bundle.
                with urllib.request.urlopen(f"{base_url}/") as response:
                    self.assertEqual(response.read(), (STATIC_APP_DIR / "index.html").read_bytes())


if __name__ == "__main__":
    unittest.main()
