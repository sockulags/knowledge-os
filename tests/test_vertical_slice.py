from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

import yaml


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
    (root / "knowledge-os.toml").write_text('[workspace]\nname = "knowledge-os"\nversion = 1\n', encoding="utf-8")
    for directory in ("inbox", "knowledge", "projects", "sources", "memory", "syntheses", "skills", "indexes", "tooling"):
        (root / directory).mkdir()


def write_record(root: Path, directory: str, record_id: str, metadata: dict, body: str = "body\n") -> Path:
    path = root / directory / f"{record_id}.md"
    rendered = yaml.safe_dump(metadata, sort_keys=False)
    path.write_text(f"---\n{rendered}---\n\n{body}", encoding="utf-8")
    return path


class KnowledgeOsVerticalSliceTests(unittest.TestCase):
    def test_malformed_metadata_is_rejected_and_not_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                "bad-record",
                {
                    "id": "bad-record",
                    "title": "Bad",
                    "type": "knowledge",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "test", "reference": "fixture"}],
                    "titel": "typo",
                },
            )
            lint = run_kos(root, "lint")
            indexed = run_kos(root, "index")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("unknown top-level field", lint.stderr)
            self.assertNotEqual(indexed.returncode, 0)
            self.assertFalse((root / "indexes" / "catalog.sqlite3").exists())

    def test_ingest_preserves_provenance_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = root / "incoming.txt"
            input_path.write_bytes(b"A raw claim\r\nwith xylophone detail.\r\n")
            first = run_kos(root, "ingest", "incoming.txt")
            self.assertEqual(first.returncode, 0, first.stderr)
            record_id = re.search(r"Ingested ([a-z0-9-]+)", first.stdout).group(1)
            destination = root / "sources" / f"{record_id}.md"
            first_bytes = destination.read_bytes()
            second = run_kos(root, "ingest", "incoming.txt")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn(f"Already ingested {record_id}", second.stdout)
            self.assertEqual(first_bytes, destination.read_bytes())
            metadata = yaml.safe_load(destination.read_text(encoding="utf-8").split("---", 2)[1])
            provenance = metadata["provenance"][0]
            self.assertEqual(provenance["reference"], str(input_path.resolve()))
            self.assertEqual(provenance["sha256"], hashlib.sha256(input_path.read_bytes()).hexdigest())
            destination.write_bytes(first_bytes + b"tampered")
            divergent = run_kos(root, "ingest", "incoming.txt")
            self.assertNotEqual(divergent.returncode, 0)
            self.assertIn("divergent body", divergent.stderr)

    def test_index_fts_search_and_inspect_are_compact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "sample.md").write_text("# Sample\n\nThe body contains a rare xylophone token.\n", encoding="utf-8")
            ingested = run_kos(root, "ingest", "sample.md")
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            searched = run_kos(root, "search", "xylophone", "--json")
            self.assertEqual(searched.returncode, 0, searched.stderr)
            results = json.loads(searched.stdout)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["type"], "source")
            self.assertIn("xylophone", results[0]["snippet"])
            self.assertEqual(
                set(results[0]),
                {"id", "title", "type", "record_kind", "status", "scope", "path", "snippet"},
            )
            plain = run_kos(root, "search", "xylophone")
            self.assertEqual(plain.returncode, 0, plain.stderr)
            self.assertEqual(len(plain.stdout.splitlines()), 1)
            self.assertEqual(plain.stdout.split("\t")[5], "general")
            record_id = results[0]["id"]
            inspected = run_kos(root, "inspect", record_id)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            inspection = json.loads(inspected.stdout)
            self.assertIn("provenance", inspection)
            self.assertIn("excerpt", inspection)
            self.assertNotIn("content", inspection)

    def test_relationship_type_and_filename_invariants_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                "wrong-name",
                {
                    "id": "actual-id",
                    "title": "Mismatch",
                    "type": "knowledge",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "test", "reference": "fixture"}],
                },
            )
            write_record(
                root,
                "knowledge",
                "type-wrong",
                {
                    "id": "type-wrong",
                    "title": "Type mismatch",
                    "type": "source",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "test", "reference": "fixture"}],
                    "related": ["missing-id"],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("filename stem must equal id", lint.stderr)
            self.assertIn("does not match directory", lint.stderr)
            self.assertIn("unresolved relationship id", lint.stderr)

    def test_project_scope_and_verified_date_invariants_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects",
                "general-project",
                {
                    "id": "general-project",
                    "title": "Wrong scope",
                    "type": "project",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "test", "reference": "fixture"}],
                },
            )
            write_record(
                root,
                "knowledge",
                "bad-verification-date",
                {
                    "id": "bad-verification-date",
                    "title": "Wrong verification date",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "verified": "2026-08-30",
                    "provenance": [{"kind": "test", "reference": "fixture"}],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("project records require scope", lint.stderr)
            self.assertIn("verified must be between created and updated", lint.stderr)

    def test_ingest_refuses_to_mutate_an_invalid_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "broken.md").write_text("no frontmatter\n", encoding="utf-8")
            (root / "incoming.txt").write_text("raw source\n", encoding="utf-8")
            ingested = run_kos(root, "ingest", "incoming.txt")
            self.assertNotEqual(ingested.returncode, 0)
            self.assertIn("cannot ingest into invalid corpus", ingested.stderr)
            self.assertEqual(list((root / "sources").glob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
