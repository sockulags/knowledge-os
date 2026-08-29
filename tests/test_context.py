from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / "examples" / "context-workspace"


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


def run_kos_bytes(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "knowledge_os", *arguments],
        cwd=workspace,
        capture_output=True,
        env=environment,
        check=False,
    )


def copy_fixture() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name) / "workspace"
    shutil.copytree(FIXTURE, root)
    return temporary, root


def manifest(output: str) -> dict:
    block = output.split("```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)


def index_fixture(root: Path) -> None:
    indexed = run_kos(root, "index")
    if indexed.returncode:
        raise AssertionError(indexed.stderr)


def write_record(root: Path, directory: str, metadata: dict, body: str) -> None:
    path = root / directory / f"{metadata['id']}.md"
    path.write_text(
        f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
        encoding="utf-8",
    )


class ContextExportTests(unittest.TestCase):
    def test_retrieves_project_general_and_skill_context_but_excludes_irrelevant_items(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            index_fixture(root)
            result = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "Add URL ingestion while preserving provenance",
                "--work-item",
                "retain source security evidence",
                "--budget",
                "12000",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            package = manifest(result.stdout)
            ordered_ids = [item["id"] for item in package["items"]]
            item_ids = set(ordered_ids)
            self.assertEqual(
                ordered_ids,
                ["knowledge-os", "url-ingestion-provenance", "provenance-boundaries", "ingest-source"],
            )
            self.assertIn("knowledge-os", item_ids)
            self.assertIn("url-ingestion-provenance", item_ids)
            self.assertIn("provenance-boundaries", item_ids)
            self.assertIn("ingest-source", item_ids)
            self.assertNotIn("irrelevant-general", item_ids)
            self.assertNotIn("irrelevant-project", item_ids)
            self.assertNotIn("other-project-url-notes", item_ids)
            self.assertIn("project:knowledge-os", {item["scope"] for item in package["items"]})
            skill = next(item for item in package["items"] if item["id"] == "ingest-source")
            self.assertEqual(skill["type"], "skill")
            self.assertEqual(skill["provenance"], [{"kind": "skill-file", "reference": "skills/ingest-source/SKILL.md"}])
            overview = package["items"][0]
            self.assertEqual(overview["selection_mode"], "mandatory")
            self.assertTrue(all(item["selection_mode"] == "ranked" for item in package["items"][1:]))
            self.assertTrue(all(isinstance(item["score"], int) for item in package["items"]))
            general = next(item for item in package["items"] if item["id"] == "provenance-boundaries")
            self.assertEqual(
                general["provenance"],
                [{"kind": "fixture", "reference": "examples/context-workspace/knowledge/provenance-boundaries.md"}],
            )
            project_decision = next(item for item in package["items"] if item["id"] == "url-ingestion-provenance")
            self.assertEqual(project_decision["relationship_to"], "knowledge-os")
            self.assertIn("explicit-one-hop-relationship", project_decision["discovery"])
            self.assertIn("original URL", result.stdout)
            self.assertIn("security boundaries", result.stdout)

    def test_output_is_byte_deterministic_and_budget_estimate_is_hard(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            index_fixture(root)
            arguments = (
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "Add URL ingestion while preserving provenance",
                "--budget",
                "12000",
            )
            first = run_kos(root, *arguments)
            second = run_kos(root, *arguments)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            package = manifest(first.stdout)
            self.assertLessEqual(math.ceil(len(first.stdout) / 4), 12000)
            self.assertEqual(package["budget"]["used_tokens"], math.ceil(len(first.stdout) / 4))

            raw = run_kos_bytes(root, *arguments)
            self.assertEqual(raw.returncode, 0, raw.stderr.decode("utf-8", errors="replace"))
            self.assertNotIn(b"\r\n", raw.stdout)
            raw_output = raw.stdout.decode("utf-8")
            raw_package = manifest(raw_output)
            self.assertEqual(raw_package["budget"]["used_tokens"], math.ceil(len(raw_output) / 4))
            self.assertLessEqual(raw_package["budget"]["used_tokens"], 12000)

            (root / "projects" / "other-project-url-notes.md").unlink()
            index_fixture(root)
            without_other_project = run_kos(root, *arguments)
            self.assertEqual(without_other_project.returncode, 0, without_other_project.stderr)
            self.assertEqual(first.stdout, without_other_project.stdout)

    def test_fts_metadata_match_is_explained(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            metadata = {
                "id": "metadataonly-record",
                "title": "Record with an unrelated title",
                "type": "knowledge",
                "status": "active",
                "scope": "general",
                "created": "2026-08-29",
                "updated": "2026-08-29",
                "provenance": [{"kind": "fixture", "reference": "metadataonly-record.md"}],
            }
            (root / "knowledge" / "metadataonly-record.md").write_text(
                f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\nThe body uses unrelated words.\n",
                encoding="utf-8",
            )
            index_fixture(root)
            result = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "metadataonly",
                "--budget",
                "12000",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            item = next(item for item in manifest(result.stdout)["items"] if item["id"] == "metadataonly-record")
            self.assertEqual(item["matched_terms"], ["metadataonly"])
            self.assertIn("metadataonly", item["selection_reason"])

            write_record(
                root,
                "knowledge",
                {
                    "id": "accented-note",
                    "title": "Café note",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "accented-note.md"}],
                },
                "The body uses unrelated words.\n",
            )
            index_fixture(root)
            accented = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "cafe",
                "--budget",
                "12000",
            )
            self.assertEqual(accented.returncode, 0, accented.stderr)
            accented_item = next(item for item in manifest(accented.stdout)["items"] if item["id"] == "accented-note")
            self.assertEqual(accented_item["matched_terms"], ["cafe"])

    def test_out_of_scope_corpus_does_not_change_eligible_fts_rank(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            common = {
                "type": "knowledge",
                "status": "active",
                "scope": "general",
                "created": "2026-08-29",
                "updated": "2026-08-29",
            }
            write_record(
                root,
                "knowledge",
                {
                    **common,
                    "id": "alpha-context",
                    "title": "Alpha context",
                    "provenance": [{"kind": "fixture", "reference": "alpha-context.md"}],
                },
                "alpha\n",
            )
            write_record(
                root,
                "knowledge",
                {
                    **common,
                    "id": "beta-context",
                    "title": "Beta context",
                    "provenance": [{"kind": "fixture", "reference": "beta-context.md"}],
                },
                "beta\n",
            )
            index_fixture(root)
            arguments = (
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "alpha beta",
                "--budget",
                "12000",
            )
            baseline = run_kos(root, *arguments)
            self.assertEqual(baseline.returncode, 0, baseline.stderr)

            for number in range(20):
                record_id = f"other-alpha-noise-{number:02d}"
                write_record(
                    root,
                    "projects",
                    {
                        "id": record_id,
                        "title": f"Other alpha noise {number}",
                        "type": "project",
                        "status": "active",
                        "scope": "project:other-project",
                        "created": "2026-08-29",
                        "updated": "2026-08-29",
                        "provenance": [{"kind": "fixture", "reference": f"{record_id}.md"}],
                    },
                    ("alpha " * 100) + "\n",
                )
            index_fixture(root)
            with_noise = run_kos(root, *arguments)
            self.assertEqual(with_noise.returncode, 0, with_noise.stderr)
            self.assertEqual(baseline.stdout, with_noise.stdout)

    def test_budget_omits_whole_items_and_too_small_mandatory_context_fails(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            body = "URL ingestion provenance security detail. " * 500
            metadata = {
                "id": "large-url-context",
                "title": "Large URL ingestion context",
                "type": "knowledge",
                "status": "active",
                "scope": "general",
                "created": "2026-08-29",
                "updated": "2026-08-29",
                "provenance": [{"kind": "fixture", "reference": "large-url-context.md"}],
            }
            (root / "knowledge" / "large-url-context.md").write_text(
                f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}", encoding="utf-8"
            )
            index_fixture(root)
            bounded = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "Add URL ingestion while preserving provenance",
                "--budget",
                "500",
            )
            self.assertEqual(bounded.returncode, 0, bounded.stderr)
            bounded_manifest = manifest(bounded.stdout)
            self.assertGreater(bounded_manifest["selection"]["budget_excluded"], 0)
            self.assertLessEqual(bounded_manifest["budget"]["used_tokens"], 500)
            self.assertNotIn("large-url-context", {item["id"] for item in bounded_manifest["items"]})

            too_small = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "URL provenance",
                "--budget",
                "1",
            )
            self.assertNotEqual(too_small.returncode, 0)
            self.assertIn("mandatory project context envelope", too_small.stderr)
            self.assertIn("requires at least", too_small.stderr)

    def test_context_is_read_only_and_nested_workspace_discovery_works(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            absent = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "URL ingestion provenance",
                "--budget",
                "12000",
            )
            self.assertNotEqual(absent.returncode, 0)
            self.assertIn("search index is absent; run 'kos index' first", absent.stderr)
            self.assertFalse((root / "indexes" / "catalog.sqlite3").exists())

            index_fixture(root)
            stale_record = root / "knowledge" / "provenance-boundaries.md"
            original_record = stale_record.read_bytes()
            sqlite_path = root / "indexes" / "catalog.sqlite3"
            original_index = sqlite_path.read_bytes()
            stale_record.write_bytes(original_record + b"\nA valid unindexed change.\n")
            stale = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "URL ingestion provenance",
                "--budget",
                "12000",
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("search index is stale; run 'kos index' first", stale.stderr)
            self.assertEqual(sqlite_path.read_bytes(), original_index)
            stale_record.write_bytes(original_record)

            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            nested = root / "nested" / "directory"
            nested.mkdir(parents=True)
            result = run_kos(
                nested,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "URL ingestion provenance",
                "--budget",
                "12000",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_missing_project_no_usable_context_malformed_corpus_and_budget_errors_are_clear(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            index_fixture(root)
            missing = run_kos(root, "context", "--project", "missing", "--task", "URL provenance", "--budget", "12000")
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("project 'missing' was not found", missing.stderr)

            for path in (root / "projects").glob("*.md"):
                text = path.read_text(encoding="utf-8")
                text = text.replace("status: active", "status: archived").replace("status: draft", "status: archived")
                path.write_text(text, encoding="utf-8")
            index_fixture(root)
            no_usable = run_kos(root, "context", "--project", "knowledge-os", "--task", "URL provenance", "--budget", "12000")
            self.assertNotEqual(no_usable.returncode, 0)
            self.assertIn("project 'knowledge-os' has no usable context", no_usable.stderr)

            (root / "knowledge" / "bad.md").write_text("not metadata\n", encoding="utf-8")
            malformed = run_kos(root, "context", "--project", "knowledge-os", "--task", "URL provenance", "--budget", "12000")
            self.assertNotEqual(malformed.returncode, 0)
            self.assertIn("cannot generate context from invalid corpus", malformed.stderr)
            self.assertIn("missing YAML frontmatter", malformed.stderr)

            missing_budget = run_kos(root, "context", "--project", "knowledge-os", "--task", "URL provenance")
            self.assertNotEqual(missing_budget.returncode, 0)
            self.assertIn("--budget", missing_budget.stderr)

            invalid_budget = run_kos(
                root, "context", "--project", "knowledge-os", "--task", "URL provenance", "--budget", "0"
            )
            self.assertNotEqual(invalid_budget.returncode, 0)
            self.assertIn("--budget must be at least 1", invalid_budget.stderr)

    def test_malformed_skill_metadata_fails_clearly(self) -> None:
        temporary, root = copy_fixture()
        with temporary:
            skill = root / "skills" / "ingest-source" / "SKILL.md"
            skill.write_text("---\nname: ingest-source\n---\n\n# Ingest source\n", encoding="utf-8")
            index_fixture(root)
            result = run_kos(
                root,
                "context",
                "--project",
                "knowledge-os",
                "--task",
                "URL ingestion provenance",
                "--budget",
                "12000",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires a non-empty description", result.stderr)


if __name__ == "__main__":
    unittest.main()
