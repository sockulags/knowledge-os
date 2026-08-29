from __future__ import annotations

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

import knowledge_os.discovery as discovery_module
from knowledge_os.context_policy import (
    ACTIVE_DURABLE_TRUST_LABEL,
    DRAFT_DURABLE_TRUST_LABEL,
    RAW_SOURCE_TRUST_LABEL,
    VERIFIED_DURABLE_TRUST_LABEL,
    trust_label,
)
from knowledge_os.model import parse_document_text
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


def create_workspace(root: Path, *, project: str = "demo") -> None:
    (root / "knowledge-os.toml").write_text(
        '[workspace]\nname = "contract-test"\nversion = 1\n',
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
    write_record(
        root,
        "projects",
        {
            "id": project,
            "title": f"{project} project overview",
            "type": "project",
            "status": "active",
            "scope": f"project:{project}",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": project}],
        },
        "The exact project overview.\n",
    )


def write_record(root: Path, directory: str, metadata: dict, body: str = "body\n") -> Path:
    path = root / directory / f"{metadata['id']}.md"
    path.write_text(
        f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
        encoding="utf-8",
    )
    return path


def discovery_metadata(record_id: str, *, scope: str = "project:demo", status: str = "proposed", **extra: object) -> dict:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": f"Observation {record_id}",
        "type": "discovery",
        "status": status,
        "scope": scope,
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "agent-run", "reference": "run-1"}],
        "evidence": [{"kind": "record", "reference": scope.removeprefix("project:")}],
    }
    metadata.update(extra)
    return metadata


def _write_root_file(root: Path, name: str, metadata: dict, body: str) -> Path:
    path = root / name
    path.write_text(
        f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
        encoding="utf-8",
    )
    return path


def manifest(output: str) -> dict:
    return json.loads(output.split("```json\n", 1)[1].split("\n```", 1)[0])


def index_workspace(root: Path) -> None:
    result = run_kos(root, "index")
    if result.returncode:
        raise AssertionError(result.stderr)


class V001ContractTests(unittest.TestCase):
    def test_raw_source_task_match_is_excluded_and_included_states_are_labeled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                {
                    "id": "draft-fact",
                    "title": "Draft fact",
                    "type": "knowledge",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "draft"}],
                },
                "draft-secret-token\n",
            )
            write_record(
                root,
                "knowledge",
                {
                    "id": "active-fact",
                    "title": "Active fact",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "active"}],
                },
                "active-secret-token\n",
            )
            write_record(
                root,
                "knowledge",
                {
                    "id": "verified-fact",
                    "title": "Verified fact",
                    "type": "knowledge",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "verified": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "verified"}],
                },
                "verified-secret-token\n",
            )
            source = root / "raw.txt"
            source.write_text("raw-secret-token\n", encoding="utf-8")
            ingested = run_kos(root, "ingest", source.name)
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            source_id = ingested.stdout.splitlines()[0].split()[-1]
            source_document = parse_document_text(
                Path("source.md"),
                "---\n"
                "id: source\n"
                "title: Source\n"
                "type: source\n"
                "status: active\n"
                "scope: general\n"
                "created: 2026-08-29\n"
                "updated: 2026-08-29\n"
                "provenance:\n"
                "  - kind: fixture\n"
                "    reference: source\n"
                "---\n\nraw\n",
            )
            self.assertEqual(trust_label(source_document), RAW_SOURCE_TRUST_LABEL)
            index_workspace(root)
            context = run_kos(
                root,
                "context",
                "--project",
                "demo",
                "--task",
                "raw-secret-token draft-secret-token active-secret-token verified-secret-token",
                "--budget",
                "12000",
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            package = manifest(context.stdout)
            items = {item["id"]: item for item in package["items"]}
            self.assertNotIn(source_id, items)
            self.assertEqual(items["draft-fact"]["trust"], DRAFT_DURABLE_TRUST_LABEL)
            self.assertEqual(items["active-fact"]["trust"], ACTIVE_DURABLE_TRUST_LABEL)
            self.assertEqual(items["verified-fact"]["trust"], VERIFIED_DURABLE_TRUST_LABEL)
            self.assertEqual(items["verified-fact"]["verified"], "2026-08-29")
            self.assertEqual(package["eligibility"]["sources"], "excluded from default context")

    def test_project_identity_has_no_fallback_and_is_exactly_usable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "projects" / "demo.md").unlink()
            write_record(
                root,
                "projects",
                {
                    "id": "unrelated-note",
                    "title": "Unrelated note",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "note"}],
                },
                "This must not become the overview.\n",
            )
            invalid_scope = run_kos(root, "lint")
            self.assertNotEqual(invalid_scope.returncode, 0)
            self.assertIn("requires exactly one valid project overview", invalid_scope.stderr)
            result = run_kos(root, "context", "--project", "demo", "--task", "overview", "--budget", "12000")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires exactly one valid project overview", result.stderr)

            write_record(
                root,
                "projects",
                {
                    "id": "demo",
                    "title": "Archived overview",
                    "type": "project",
                    "status": "archived",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "archived"}],
                },
                "Archived.\n",
            )
            archived_lint = run_kos(root, "lint")
            self.assertNotEqual(archived_lint.returncode, 0)
            self.assertIn("is not usable", archived_lint.stderr)
            archived = run_kos(root, "context", "--project", "demo", "--task", "overview", "--budget", "12000")
            self.assertNotEqual(archived.returncode, 0)
            self.assertIn("is not usable", archived.stderr)

            # The global ID invariant makes a literal duplicate identity invalid;
            # context must fail closed rather than choose one.
            write_record(
                root,
                "knowledge",
                {
                    "id": "demo",
                    "title": "Duplicate ID",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "duplicate"}],
                },
                "Duplicate.\n",
            )
            duplicate = run_kos(root, "context", "--project", "demo", "--task", "overview", "--budget", "12000")
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("duplicate id 'demo'", duplicate.stderr)

    def test_scope_policy_blocks_direct_and_relationship_cross_project_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects",
                {
                    "id": "demo-note",
                    "title": "Demo note",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo-note"}],
                    "related": ["other-secret"],
                },
                "The task names scope-leak-token.\n",
            )
            write_record(
                root,
                "projects",
                {
                    "id": "other",
                    "title": "Other project overview",
                    "type": "project",
                    "status": "active",
                    "scope": "project:other",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "other"}],
                },
                "Other overview.\n",
            )
            write_record(
                root,
                "projects",
                {
                    "id": "other-secret",
                    "title": "Other project secret",
                    "type": "project",
                    "status": "active",
                    "scope": "project:other",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "other"}],
                },
                "scope-leak-token other-private-content\n",
            )
            index_workspace(root)
            result = run_kos(root, "context", "--project", "demo", "--task", "scope-leak-token other-private-content", "--budget", "12000")
            self.assertEqual(result.returncode, 0, result.stderr)
            ids = {item["id"] for item in manifest(result.stdout)["items"]}
            self.assertIn("demo-note", ids)
            self.assertNotIn("other-secret", ids)
            self.assertNotIn("project:other", {item["scope"] for item in manifest(result.stdout)["items"]})

    def test_record_kind_status_and_scope_contract_is_strict_and_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                {
                    "id": "architecture-decision",
                    "title": "Architecture decision",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "record_kind": "decision",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "decision"}],
                },
                "decision-index-token\n",
            )
            index_workspace(root)
            search = run_kos(root, "search", "decision", "--json")
            self.assertEqual(search.returncode, 0, search.stderr)
            value = json.loads(search.stdout)
            decision = next(item for item in value if item["id"] == "architecture-decision")
            self.assertEqual(decision["record_kind"], "decision")
            context = run_kos(root, "context", "--project", "demo", "--task", "decision-index-token", "--budget", "12000")
            self.assertEqual(context.returncode, 0, context.stderr)
            item = next(item for item in manifest(context.stdout)["items"] if item["id"] == "architecture-decision")
            self.assertEqual(item["record_kind"], "decision")

            cases = (
                ("verified", "status for type 'knowledge'"),
                ("scope: project:demo", "knowledge records require scope general"),
            )
            for index, (line, message) in enumerate(cases):
                metadata = {
                    "id": f"invalid-contract-{index}",
                    "title": "Invalid contract",
                    "type": "knowledge",
                    "status": "draft",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "invalid"}],
                }
                if line == "verified":
                    metadata["status"] = line
                else:
                    metadata["scope"] = "project:demo"
                write_record(root, "knowledge", metadata)
                lint = run_kos(root, "lint")
                self.assertNotEqual(lint.returncode, 0)
                self.assertIn(message, lint.stderr)
                (root / "knowledge" / f"{metadata['id']}.md").unlink()

            write_record(
                root,
                "sources",
                {
                    "id": "source-kind-invalid",
                    "title": "Source",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "record_kind": "decision",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "source"}],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("record_kind is only allowed", lint.stderr)
            (root / "sources" / "source-kind-invalid.md").unlink()
            write_record(
                root,
                "knowledge",
                {
                    "id": "unknown-record-kind",
                    "title": "Unknown kind",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "record_kind": "speculation",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "unknown"}],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("record_kind must be one of", lint.stderr)

    def test_lineage_is_minimal_and_integrity_checks_cover_partial_states(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = _write_root_file(
                root,
                "promotion.md",
                discovery_metadata("promotion-signal"),
                "promotion-lineage-token\n",
            )
            added = run_kos(root, "discovery", "add", input_path.name)
            self.assertEqual(added.returncode, 0, added.stderr)
            promoted = run_kos(
                root,
                "discovery",
                "promote",
                "promotion-signal",
                "--target-id",
                "promotion-target",
                "--title",
                "Promotion target",
                "--scope",
                "project:demo",
            )
            self.assertEqual(promoted.returncode, 0, promoted.stderr)
            target = yaml.safe_load((root / "projects" / "promotion-target.md").read_text(encoding="utf-8").split("---", 2)[1])
            self.assertEqual(target["provenance"], [{"kind": "discovery", "reference": "promotion-signal"}])
            self.assertNotIn("sources", target)
            discovery = yaml.safe_load((root / "discoveries" / "promotion-signal.md").read_text(encoding="utf-8").split("---", 2)[1])
            self.assertEqual(discovery["reviews"][-1]["target"], "promotion-target")
            self.assertNotIn("related", discovery)

            # The frozen contract rejects only the two legacy duplicate edges;
            # unrelated ordinary relationships remain valid.
            target["sources"] = ["promotion-signal", "demo"]
            discovery["related"] = ["promotion-target", "demo"]
            write_record(root, "projects", target, "promotion-lineage-token\n")
            write_record(root, "discoveries", discovery, "promotion-lineage-token\n")
            legacy = run_kos(root, "lint")
            self.assertNotEqual(legacy.returncode, 0)
            self.assertIn("redundant legacy promotion lineage", legacy.stderr)
            self.assertIn("in sources", legacy.stderr)
            self.assertIn("in related", legacy.stderr)

            target["sources"] = ["demo"]
            discovery["related"] = ["demo"]
            write_record(root, "projects", target, "promotion-lineage-token\n")
            write_record(root, "discoveries", discovery, "promotion-lineage-token\n")
            unrelated = run_kos(root, "lint")
            self.assertEqual(unrelated.returncode, 0, unrelated.stderr)

            target["provenance"] = [{"kind": "fixture", "reference": "broken-lineage"}]
            write_record(root, "projects", target, "promotion-lineage-token\n")
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("provenance must include discovery reference", lint.stderr)

            target["provenance"] = [{"kind": "discovery", "reference": "promotion-signal"}]
            discovery["status"] = "proposed"
            discovery["reviews"] = []
            write_record(root, "projects", target, "promotion-lineage-token\n")
            write_record(root, "discoveries", discovery, "promotion-lineage-token\n")
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("discovery provenance 'promotion-signal'", lint.stderr)

            discovery["status"] = "promoted"
            discovery["reviews"] = [{"decision": "promote", "date": "2026-08-29", "target": "missing-target"}]
            write_record(root, "discoveries", discovery, "promotion-lineage-token\n")
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("promoted discovery target 'missing-target' does not exist", lint.stderr)

    def test_self_lineage_and_supersession_cycles_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                {
                    "id": "self-source",
                    "title": "Self source",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "self"}],
                    "sources": ["self-source"],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("self-source relationship", lint.stderr)
            (root / "knowledge" / "self-source.md").unlink()

            write_record(
                root,
                "knowledge",
                {
                    "id": "self-supersedes",
                    "title": "Self supersedes",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "self"}],
                    "supersedes": ["self-supersedes"],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("self-supersedes relationship", lint.stderr)
            (root / "knowledge" / "self-supersedes.md").unlink()

            for record_id, supersedes in (("cycle-a", ["cycle-b"]), ("cycle-b", ["cycle-a"])):
                write_record(
                    root,
                    "knowledge",
                    {
                        "id": record_id,
                        "title": record_id,
                        "type": "knowledge",
                        "status": "active",
                        "scope": "general",
                        "created": "2026-08-29",
                        "updated": "2026-08-29",
                        "provenance": [{"kind": "fixture", "reference": record_id}],
                        "supersedes": supersedes,
                    },
                )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("supersedes cycle detected", lint.stderr)

    def test_canonical_provenance_and_workspace_version_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                {
                    "id": "bad-provenance",
                    "title": "Bad provenance",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "record", "reference": "missing-record"}],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("unresolved canonical provenance", lint.stderr)
            (root / "knowledge" / "bad-provenance.md").unlink()

            write_record(
                root,
                "knowledge",
                {
                    "id": "wrong-provenance-kind",
                    "title": "Wrong provenance kind",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "discovery", "reference": "demo"}],
                },
            )
            lint = run_kos(root, "lint")
            self.assertNotEqual(lint.returncode, 0)
            self.assertIn("must point to a discovery record", lint.stderr)
            (root / "knowledge" / "wrong-provenance-kind.md").unlink()

            (root / "knowledge-os.toml").write_text('[workspace]\nname = "contract-test"\nversion = 2\n', encoding="utf-8")
            unsupported = run_kos(root, "lint")
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("unsupported workspace version 2", unsupported.stderr)

    def test_disposable_indexes_can_be_deleted_and_rebuilt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                {
                    "id": "rebuildable",
                    "title": "Rebuildable",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "rebuildable"}],
                },
                "rebuildable-token\n",
            )
            index_workspace(root)
            (root / "indexes" / "catalog.md").unlink()
            (root / "indexes" / "catalog.sqlite3").unlink()
            lint = run_kos(root, "lint")
            self.assertEqual(lint.returncode, 0, lint.stderr)
            rebuilt = run_kos(root, "index")
            self.assertEqual(rebuilt.returncode, 0, rebuilt.stderr)
            search = run_kos(root, "search", "rebuildable-token", "--json")
            self.assertEqual(search.returncode, 0, search.stderr)

    def test_lint_validates_skills_and_rejects_managed_symlinks_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            skill = root / "skills" / "safe-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: safe-skill\ndescription: A safe skill\ntags:\n  - safe\n---\n\n# Safe\n",
                encoding="utf-8",
            )
            lint = run_kos(root, "lint")
            self.assertEqual(lint.returncode, 0, lint.stderr)
            (skill / "SKILL.md").write_text(
                "---\nname: safe-skill\ndescription: A safe skill\ntags:\n  - 'Not Safe'\n---\n\n# Safe\n",
                encoding="utf-8",
            )
            invalid_tag = run_kos(root, "lint")
            self.assertNotEqual(invalid_tag.returncode, 0)
            self.assertIn("tag 'Not Safe' must be lowercase kebab-case", invalid_tag.stderr)
            wrong_directory = root / "skills" / "wrong-directory"
            wrong_directory.mkdir()
            (wrong_directory / "SKILL.md").write_text(
                "---\nname: another-skill\ndescription: Another skill\n---\n\n# Another\n",
                encoding="utf-8",
            )
            wrong_name = run_kos(root, "lint")
            self.assertNotEqual(wrong_name.returncode, 0)
            self.assertIn("directory name 'wrong-directory' must match", wrong_name.stderr)
            (skill / "SKILL.md").write_text("---\nname: safe-skill\ndescription: A safe skill\n---\n\n", encoding="utf-8")
            malformed = run_kos(root, "lint")
            self.assertNotEqual(malformed.returncode, 0)
            self.assertIn("body must be non-empty", malformed.stderr)
            (skill / "SKILL.md").write_text(
                "---\nname: safe-skill\ndescription: Select by metadata\n---\n\nbody-only-trigger\n",
                encoding="utf-8",
            )
            shutil.rmtree(wrong_directory)
            index_workspace(root)
            body_only = run_kos(root, "context", "--project", "demo", "--task", "body-only-trigger", "--budget", "12000")
            self.assertEqual(body_only.returncode, 0, body_only.stderr)
            self.assertNotIn("safe-skill", {item["id"] for item in manifest(body_only.stdout)["items"]})

            external = Path(directory).parent / f"{Path(directory).name}-external"
            external.mkdir()
            try:
                try:
                    (root / "knowledge" / "outside.md").symlink_to(external / "outside.md")
                except (OSError, NotImplementedError):
                    self.skipTest("symlinks are unavailable on this platform")
                unsafe = run_kos(root, "lint")
                self.assertNotEqual(unsafe.returncode, 0)
                self.assertIn("must not be a symlink", unsafe.stderr)
            finally:
                shutil.rmtree(external)

    def test_shared_lock_is_used_for_index_and_mutations_and_index_failure_keeps_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            workspace = Workspace(root)
            with patch("knowledge_os.index.workspace_mutation_lock") as index_lock:
                # The public index operation owns the shared lock at the index boundary.
                index_lock.return_value.__enter__.return_value = None
                index_lock.return_value.__exit__.return_value = None
                from knowledge_os.index import rebuild_indexes

                rebuild_indexes(workspace)
                index_lock.assert_called_once_with(workspace)

            input_path = _write_root_file(
                root,
                "lock-discovery.md",
                discovery_metadata("lock-discovery"),
                "lock-token\n",
            )
            added = run_kos(root, "discovery", "add", input_path.name)
            self.assertEqual(added.returncode, 0, added.stderr)
            with patch.object(
                discovery_module,
                "refresh_derived_indexes",
                side_effect=discovery_module.DiscoveryError("canonical corpus is authoritative; run 'kos lint' and then 'kos index'"),
            ):
                with self.assertRaises(discovery_module.DiscoveryError) as failure:
                    discovery_module.promote_discovery(
                        Workspace(root),
                        "lock-discovery",
                        target_id="lock-target",
                        title="Lock target",
                        scope="project:demo",
                    )
            self.assertIn("kos lint", str(failure.exception))
            self.assertTrue((root / "projects" / "lock-target.md").is_file())
            self.assertEqual(run_kos(root, "lint").returncode, 0)


if __name__ == "__main__":
    unittest.main()
