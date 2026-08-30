from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

import knowledge_os.capture as capture_module
import knowledge_os.index as index_module
from knowledge_os.cli import main as cli_main
from knowledge_os.workspace import Workspace


REPOSITORY = Path(__file__).resolve().parents[1]


def run_kos(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "knowledge_os", *arguments],
        cwd=workspace,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def create_workspace(root: Path) -> None:
    (root / "knowledge-os.toml").write_text(
        '[workspace]\nname = "capture-test"\nversion = 1\n',
        encoding="utf-8",
    )
    for directory in (
        "inbox",
        "knowledge",
        "projects",
        "sources",
        "memory",
        "syntheses",
        "discoveries",
        "skills",
        "indexes",
        "tooling",
    ):
        (root / directory).mkdir()
    write_candidate(
        root / "project-overview.md",
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
        "The exact project overview.\n",
    )
    result = run_kos(root, "capture", "project-overview.md")
    assert result.returncode == 0, result.stderr


def write_candidate(path: Path, metadata: dict[str, object], body: str = "Durable body.\n") -> None:
    rendered = yaml.safe_dump(metadata, sort_keys=False)
    path.write_text(f"---\n{rendered}---\n\n{body}", encoding="utf-8")


def managed_snapshot(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for directory in ("knowledge", "projects", "memory", "indexes"):
        for path in sorted((root / directory).rglob("*")):
            if path.is_file():
                snapshot[path.relative_to(root).as_posix()] = path.read_bytes()
    return snapshot


class CaptureTests(unittest.TestCase):
    def test_capture_creates_project_knowledge_and_memory_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            cases = (
                (
                    "project-note",
                    "project",
                    "project:demo",
                    "projects/project-note.md",
                ),
                ("general-lesson", "knowledge", "general", "knowledge/general-lesson.md"),
                ("user-preference", "memory", "project:demo", "memory/user-preference.md"),
            )
            external = root.parent / f"{root.name}-external"
            external.mkdir()
            try:
                for record_id, record_type, scope, relative_path in cases:
                    candidate_dir = external if record_id == "user-preference" else root
                    candidate = candidate_dir / f"candidate-{record_id}.md"
                    write_candidate(
                        candidate,
                        {
                            "id": record_id,
                            "title": record_id,
                            "type": record_type,
                            "status": "draft",
                            "scope": scope,
                            "created": "2026-08-30",
                            "updated": "2026-08-30",
                            "provenance": [{"kind": "conversation", "reference": f"conversation:{record_id}"}],
                        },
                        f"Retain {record_id}.\n",
                    )
                    result = run_kos(root, "--root", str(root), "capture", str(candidate), "--json")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        json.loads(result.stdout),
                        {
                            "id": record_id,
                            "path": relative_path,
                            "scope": scope,
                            "status": "draft",
                            "type": record_type,
                        },
                    )
                    self.assertTrue((root / relative_path).is_file())
            finally:
                shutil.rmtree(external)

            indexed = run_kos(root, "lint")
            self.assertEqual(indexed.returncode, 0, indexed.stderr)
            catalog = (root / "indexes" / "catalog.md").read_text(encoding="utf-8")
            for record_id, _, _, _ in cases:
                self.assertIn(record_id, catalog)

    def test_capture_rejects_unsafe_candidates_without_canonical_or_index_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            index = run_kos(root, "index")
            self.assertEqual(index.returncode, 0, index.stderr)

            cases = (
                (
                    "duplicate",
                    {
                        "id": "demo",
                        "title": "Duplicate",
                        "type": "project",
                        "status": "draft",
                        "scope": "project:demo",
                        "created": "2026-08-30",
                        "updated": "2026-08-30",
                        "provenance": [{"kind": "conversation", "reference": "duplicate"}],
                    },
                    "duplicate capture id",
                ),
                (
                    "unsupported",
                    {
                        "id": "unsupported",
                        "title": "Unsupported",
                        "type": "source",
                        "status": "active",
                        "scope": "general",
                        "created": "2026-08-30",
                        "updated": "2026-08-30",
                        "provenance": [{"kind": "conversation", "reference": "unsupported"}],
                    },
                    "only type: knowledge, project, or memory",
                ),
                (
                    "verified",
                    {
                        "id": "verified",
                        "title": "Verified claim",
                        "type": "knowledge",
                        "status": "active",
                        "scope": "general",
                        "created": "2026-08-30",
                        "updated": "2026-08-30",
                        "verified": "2026-08-30",
                        "provenance": [{"kind": "conversation", "reference": "verified"}],
                    },
                    "must not include verified",
                ),
                (
                    "unknown-provenance",
                    {
                        "id": "unknown-provenance",
                        "title": "Unknown provenance field",
                        "type": "knowledge",
                        "status": "draft",
                        "scope": "general",
                        "created": "2026-08-30",
                        "updated": "2026-08-30",
                        "provenance": [
                            {
                                "kind": "conversation",
                                "reference": "unknown-provenance",
                                "digest": "0" * 64,
                            }
                        ],
                    },
                    "provenance[0] has unknown field(s): digest",
                ),
                (
                    "out-of-scope",
                    {
                        "id": "out-of-scope",
                        "title": "Other project note",
                        "type": "project",
                        "status": "draft",
                        "scope": "project:other",
                        "created": "2026-08-30",
                        "updated": "2026-08-30",
                        "provenance": [{"kind": "conversation", "reference": "out-of-scope"}],
                    },
                    "requires exactly one valid project overview",
                ),
            )
            for record_id, metadata, expected_error in cases:
                candidate = root / f"candidate-{record_id}.md"
                write_candidate(candidate, metadata)
                before = managed_snapshot(root)
                result = run_kos(root, "capture", candidate.name)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected_error, result.stderr)
                self.assertEqual(managed_snapshot(root), before)
                self.assertFalse((root / "knowledge" / f"{record_id}.md").exists())
                self.assertFalse((root / "projects" / f"{record_id}.md").exists())
                self.assertFalse((root / "memory" / f"{record_id}.md").exists())

    def test_final_exclusive_create_refuses_overwrite_and_preserves_competing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            candidate = root / "candidate-race.md"
            write_candidate(
                candidate,
                {
                    "id": "race-winner",
                    "title": "Race winner",
                    "type": "knowledge",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-30",
                    "updated": "2026-08-30",
                    "provenance": [{"kind": "conversation", "reference": "race"}],
                },
            )
            destination = root / "knowledge" / "race-winner.md"
            competing_content = b"competing writer content\n"

            def create_competing_file(path: Path, _: bytes) -> None:
                path.write_bytes(competing_content)
                raise FileExistsError

            with patch.object(
                capture_module,
                "exclusive_write",
                side_effect=create_competing_file,
            ) as exclusive_create:
                with self.assertRaises(capture_module.CaptureError) as failure:
                    capture_module.capture_record(Workspace(root), candidate)

            exclusive_create.assert_called_once()
            self.assertIn("created by another writer; refusing overwrite", str(failure.exception))
            self.assertEqual(destination.read_bytes(), competing_content)

    def test_index_refresh_failure_keeps_canonical_record_and_cli_reports_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            candidate = root / "candidate-index-failure.md"
            write_candidate(
                candidate,
                {
                    "id": "index-failure",
                    "title": "Index failure",
                    "type": "memory",
                    "status": "draft",
                    "scope": "project:demo",
                    "created": "2026-08-30",
                    "updated": "2026-08-30",
                    "provenance": [{"kind": "conversation", "reference": "index-failure"}],
                },
            )
            stdout = StringIO()
            stderr = StringIO()
            with patch.object(
                index_module,
                "_rebuild_indexes_locked",
                side_effect=OSError("injected index failure"),
            ):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    exit_code = cli_main(
                        ["--root", str(root), "capture", str(candidate), "--json"]
                    )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("canonical corpus is authoritative", stderr.getvalue())
            self.assertIn("run 'kos lint' and then 'kos index' to recover", stderr.getvalue())
            destination = root / "memory" / "index-failure.md"
            self.assertTrue(destination.is_file())

            lint = run_kos(root, "lint")
            self.assertEqual(lint.returncode, 0, lint.stderr)
            index = run_kos(root, "index")
            self.assertEqual(index.returncode, 0, index.stderr)
            self.assertIn(
                "index-failure",
                (root / "indexes" / "catalog.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
