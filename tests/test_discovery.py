from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

import knowledge_os.discovery as discovery_module
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
        '[workspace]\nname = "discovery-test"\nversion = 1\n',
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
            "id": "demo",
            "title": "Demo",
            "type": "project",
            "status": "active",
            "scope": "project:demo",
            "created": "2026-08-29",
            "updated": "2026-08-29",
            "provenance": [{"kind": "fixture", "reference": "demo"}],
        },
        "Overview.\n",
    )


def write_record(root: Path, directory: str, metadata: dict, body: str) -> Path:
    path = root / directory / f"{metadata['id']}.md"
    path.write_text(
        f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
        encoding="utf-8",
    )
    return path


def discovery_metadata(
    record_id: str,
    *,
    scope: str = "project:demo",
    status: str = "proposed",
    evidence: list[dict] | None = None,
    **extra: object,
) -> dict:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": f"Observation {record_id}",
        "type": "discovery",
        "status": status,
        "scope": scope,
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "agent-run", "reference": "run-1"}],
        "evidence": evidence if evidence is not None else [{"kind": "record", "reference": "demo"}],
    }
    metadata.update(extra)
    return metadata


def write_input(root: Path, metadata: dict, body: str, name: str = "candidate.md") -> Path:
    path = root / name
    path.write_text(
        f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
        encoding="utf-8",
    )
    return path


def snapshot_files(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def context_manifest(output: str) -> dict:
    block = output.split("```json\n", 1)[1].split("\n```", 1)[0]
    return json.loads(block)


def promote_fixture(root: Path, discovery_id: str = "promotable-signal", target_id: str = "promoted-project-fact") -> None:
    input_path = write_input(
        root,
        discovery_metadata(discovery_id),
        "A unique promotable signal.\n",
    )
    added = run_kos(root, "discovery", "add", input_path.name)
    if added.returncode:
        raise AssertionError(added.stderr)
    promoted = run_kos(
        root,
        "discovery",
        "promote",
        discovery_id,
        "--target-id",
        target_id,
        "--title",
        "Promoted project fact",
        "--scope",
        "project:demo",
    )
    if promoted.returncode:
        raise AssertionError(promoted.stderr)


class DiscoveryWorkflowTests(unittest.TestCase):
    def test_add_preserves_evidence_provenance_and_is_globally_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = write_input(
                root,
                discovery_metadata(
                    "observed-signal",
                    origin={"project": "demo", "work_item": "work-7", "run": "run-1"},
                    confidence="medium",
                    evidence=[
                        {"kind": "record", "reference": "demo"},
                        {"kind": "log", "reference": "opaque-run-log", "sha256": "a" * 64},
                    ],
                ),
                "The external agent observed a rare signal.\n",
                name="arbitrary-input-name.md",
            )
            added = run_kos(root, "discovery", "add", input_path.name)
            self.assertEqual(added.returncode, 0, added.stderr)
            self.assertTrue((root / "discoveries" / "observed-signal.md").is_file())

            inspected = run_kos(root, "discovery", "inspect", "observed-signal")
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            value = json.loads(inspected.stdout)
            self.assertEqual(value["status"], "proposed")
            self.assertEqual(value["origin"]["project"], "demo")
            self.assertEqual(value["evidence"][1]["sha256"], "a" * 64)
            self.assertEqual(value["provenance"][0]["reference"], "run-1")
            self.assertEqual(value["body"], "The external agent observed a rare signal.\n")

            searched = run_kos(root, "search", "rare", "--json")
            self.assertEqual(searched.returncode, 0, searched.stderr)
            self.assertEqual(json.loads(searched.stdout)[0]["id"], "observed-signal")

            generic = run_kos(root, "inspect", "observed-signal")
            self.assertEqual(generic.returncode, 0, generic.stderr)
            generic_value = json.loads(generic.stdout)
            self.assertNotIn("evidence", generic_value)
            self.assertNotIn("body", generic_value)

            duplicate = run_kos(root, "discovery", "add", input_path.name)
            self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
            self.assertIn("Already present discovery observed-signal", duplicate.stdout)

    def test_invalid_discovery_input_and_record_evidence_are_rejected_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            invalid = write_input(
                root,
                discovery_metadata("rejected-input", status="rejected", reviews=[{"decision": "reject", "date": "2026-08-29", "reason": "no"}]),
                "Rejected input.\n",
            )
            before = snapshot_files(root)
            result = run_kos(root, "discovery", "add", invalid.name)
            self.assertEqual(result.returncode, 1)
            self.assertIn("status: proposed", result.stderr)
            self.assertEqual(before, snapshot_files(root))

            missing_record = write_input(
                root,
                discovery_metadata("missing-evidence", evidence=[{"kind": "record", "reference": "missing"}]),
                "Evidence points at a missing ID.\n",
            )
            before = snapshot_files(root)
            result = run_kos(root, "discovery", "add", missing_record.name)
            self.assertEqual(result.returncode, 1)
            self.assertIn("unresolved evidence record id", result.stderr)
            self.assertEqual(before, snapshot_files(root))

            empty_body = write_input(root, discovery_metadata("empty-body"), "\n")
            result = run_kos(root, "discovery", "add", empty_body.name)
            self.assertEqual(result.returncode, 1)
            self.assertIn("discovery body must be non-empty", result.stderr)

    def test_review_is_read_only_and_surfaces_related_records_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge",
                {
                    "id": "existing-boundary",
                    "title": "Existing provenance boundary",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "existing"}],
                },
                "The existing record describes a provenance boundary.\n",
            )
            input_path = write_input(
                root,
                discovery_metadata("related-observation", related=["existing-boundary"]),
                "The external agent observed a provenance boundary.\n",
            )
            self.assertEqual(run_kos(root, "discovery", "add", input_path.name).returncode, 0)
            before = snapshot_files(root)
            first = run_kos(root, "discovery", "review", "related-observation")
            second = run_kos(root, "discovery", "review", "related-observation")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout, second.stdout)
            self.assertIn("existing-boundary", first.stdout)
            self.assertIn("knowledge/existing-boundary.md", first.stdout)
            self.assertIn("potential overlaps or conflicts", first.stdout)
            self.assertIn("not semantic contradiction detection", first.stdout)
            self.assertIn("--acknowledge-related", first.stdout)
            self.assertEqual(before, snapshot_files(root))

            failed = run_kos(
                root,
                "discovery",
                "promote",
                "related-observation",
                "--target-id",
                "new-record",
                "--title",
                "New record",
                "--scope",
                "project:demo",
            )
            self.assertEqual(failed.returncode, 1)
            self.assertIn("existing-boundary", failed.stderr)
            self.assertEqual(before, snapshot_files(root))

    def test_retain_reject_lifecycle_and_context_trust_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            retained_input = write_input(
                root,
                discovery_metadata("retained-signal"),
                "A retained signal for the project context.\n",
                name="retained.md",
            )
            rejected_input = write_input(
                root,
                discovery_metadata("rejected-signal"),
                "A rejected signal for the project context.\n",
                name="rejected.md",
            )
            general_input = write_input(
                root,
                discovery_metadata("general-signal", scope="general"),
                "A general signal cannot be retained.\n",
                name="general.md",
            )
            for path in (retained_input, rejected_input, general_input):
                self.assertEqual(run_kos(root, "discovery", "add", path.name).returncode, 0)

            retained = run_kos(root, "discovery", "retain", "retained-signal", "--reviewer", "human")
            self.assertEqual(retained.returncode, 0, retained.stderr)
            rejected = run_kos(
                root,
                "discovery",
                "reject",
                "rejected-signal",
                "--reason",
                "The observation was not reproducible.",
            )
            self.assertEqual(rejected.returncode, 0, rejected.stderr)
            general_retain = run_kos(root, "discovery", "retain", "general-signal")
            self.assertEqual(general_retain.returncode, 1)
            self.assertIn("require project scope", general_retain.stderr)

            context = run_kos(
                root,
                "context",
                "--project",
                "demo",
                "--task",
                "retained signal rejected signal",
                "--budget",
                "12000",
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            items = context_manifest(context.stdout)["items"]
            retained_item = next(item for item in items if item["id"] == "retained-signal")
            self.assertEqual(retained_item["status"], "retained")
            self.assertEqual(retained_item["trust"], "reviewed observation; not established knowledge")
            self.assertNotIn("rejected-signal", {item["id"] for item in items})
            self.assertNotIn("general-signal", {item["id"] for item in items})

            invalid_transition = run_kos(root, "discovery", "retain", "rejected-signal")
            self.assertEqual(invalid_transition.returncode, 1)
            self.assertIn("invalid discovery transition rejected -> retained", invalid_transition.stderr)

    def test_promotion_creates_new_target_links_discovery_and_keeps_target_context_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = write_input(
                root,
                discovery_metadata("promotable-signal"),
                "A unique promotable signal.\n",
            )
            self.assertEqual(run_kos(root, "discovery", "add", input_path.name).returncode, 0)
            promoted = run_kos(
                root,
                "discovery",
                "promote",
                "promotable-signal",
                "--target-id",
                "promoted-project-fact",
                "--title",
                "Promoted project fact",
                "--scope",
                "project:demo",
            )
            self.assertEqual(promoted.returncode, 0, promoted.stderr)
            target = root / "projects" / "promoted-project-fact.md"
            self.assertTrue(target.is_file())
            target_metadata = yaml.safe_load(target.read_text(encoding="utf-8").split("---", 2)[1])
            self.assertEqual(target_metadata["status"], "draft")
            self.assertEqual(target_metadata["type"], "project")
            self.assertEqual(target_metadata["sources"], ["promotable-signal"])
            self.assertEqual(target_metadata["provenance"], [{"kind": "discovery", "reference": "promotable-signal"}])
            self.assertEqual(target.read_text(encoding="utf-8").split("---", 2)[2].lstrip("\n"), "A unique promotable signal.\n")

            discovery = json.loads(run_kos(root, "discovery", "inspect", "promotable-signal").stdout)
            self.assertEqual(discovery["status"], "promoted")
            self.assertEqual(discovery["reviews"][-1]["target"], "promoted-project-fact")
            self.assertIn("promoted-project-fact", discovery["relationships"]["related"])

            context = run_kos(
                root,
                "context",
                "--project",
                "demo",
                "--task",
                "unique promotable signal",
                "--budget",
                "12000",
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            ids = {item["id"] for item in context_manifest(context.stdout)["items"]}
            self.assertIn("promoted-project-fact", ids)
            self.assertNotIn("promotable-signal", ids)

    def test_scope_promotion_guards_and_failed_operations_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            broadening_input = write_input(
                root,
                discovery_metadata("broadening-signal"),
                "A unique scope broadening signal.\n",
                name="broadening.md",
            )
            cross_project_input = write_input(
                root,
                discovery_metadata("cross-project-signal"),
                "A unique cross project signal.\n",
                name="cross-project.md",
            )
            self.assertEqual(run_kos(root, "discovery", "add", broadening_input.name).returncode, 0)
            self.assertEqual(run_kos(root, "discovery", "add", cross_project_input.name).returncode, 0)

            before = snapshot_files(root)
            broadening = run_kos(
                root,
                "discovery",
                "promote",
                "broadening-signal",
                "--target-id",
                "general-fact",
                "--title",
                "General fact",
                "--scope",
                "general",
            )
            self.assertEqual(broadening.returncode, 1)
            self.assertIn("--allow-scope-broadening", broadening.stderr)
            self.assertEqual(before, snapshot_files(root))

            cross_project = run_kos(
                root,
                "discovery",
                "promote",
                "cross-project-signal",
                "--target-id",
                "other-project-fact",
                "--title",
                "Other project fact",
                "--scope",
                "project:other",
            )
            self.assertEqual(cross_project.returncode, 1)
            self.assertIn("cross-project promotion is not supported", cross_project.stderr)
            self.assertEqual(before, snapshot_files(root))

            allowed = run_kos(
                root,
                "discovery",
                "promote",
                "broadening-signal",
                "--target-id",
                "general-fact",
                "--title",
                "General fact",
                "--scope",
                "general",
                "--allow-scope-broadening",
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)

    def test_duplicate_ids_and_origin_scope_are_rejected_by_workspace_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            duplicate = write_input(root, discovery_metadata("demo"), "Duplicate global ID.\n")
            before = snapshot_files(root)
            result = run_kos(root, "discovery", "add", duplicate.name)
            self.assertEqual(result.returncode, 1)
            self.assertIn("duplicate discovery id", result.stderr)
            self.assertEqual(before, snapshot_files(root))

            mismatched = write_input(
                root,
                discovery_metadata("wrong-origin", origin={"project": "other"}),
                "Wrong origin scope.\n",
            )
            result = run_kos(root, "discovery", "add", mismatched.name)
            self.assertEqual(result.returncode, 1)
            self.assertIn("matching project scope", result.stderr)

    def test_review_dates_are_ordered_bounded_and_track_updated(self) -> None:
        cases = (
            (
                "review dates must be nondecreasing",
                {
                    "status": "rejected",
                    "created": "2026-08-28",
                    "updated": "2026-08-29",
                    "reviews": [
                        {"decision": "retain", "date": "2026-08-29"},
                        {"decision": "reject", "date": "2026-08-28", "reason": "Not reproducible."},
                    ],
                },
            ),
            (
                "between created and updated",
                {
                    "status": "retained",
                    "updated": "2026-08-29",
                    "reviews": [{"decision": "retain", "date": "2026-08-28"}],
                },
            ),
            (
                "between created and updated",
                {
                    "status": "retained",
                    "updated": "2026-08-29",
                    "reviews": [{"decision": "retain", "date": "2026-08-30"}],
                },
            ),
            (
                "latest review date must equal updated",
                {
                    "status": "retained",
                    "updated": "2026-08-30",
                    "reviews": [{"decision": "retain", "date": "2026-08-29"}],
                },
            ),
        )
        for index, (message, overrides) in enumerate(cases):
            with self.subTest(case=index):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    create_workspace(root)
                    metadata = discovery_metadata(f"bad-review-{index}", **overrides)
                    write_record(root, "discoveries", metadata, "Review date test.\n")
                    lint = run_kos(root, "lint")
                    self.assertNotEqual(lint.returncode, 0)
                    self.assertIn(message, lint.stderr)

    def test_promoted_lineage_invariants_reject_orphaned_and_mismatched_records(self) -> None:
        cases = (
            (
                "self target",
                lambda discovery, target: discovery.update(
                    reviews=[{"decision": "promote", "date": "2026-08-29", "target": discovery["id"]}]
                ),
                "must not reference itself",
            ),
            (
                "orphan target",
                lambda discovery, target: discovery.update(
                    reviews=[{"decision": "promote", "date": "2026-08-29", "target": "missing-target"}]
                ),
                "does not exist",
            ),
            (
                "target type",
                lambda discovery, target: target.update(type="knowledge"),
                "must have type 'project'",
            ),
            (
                "project scope",
                lambda discovery, target: target.update(scope="project:other"),
                "different project scope",
            ),
            (
                "reciprocal related",
                lambda discovery, target: discovery.update(related=[]),
                "related must contain target",
            ),
            (
                "target sources",
                lambda discovery, target: target.pop("sources"),
                "sources must contain discovery id",
            ),
            (
                "target provenance",
                lambda discovery, target: target.update(
                    provenance=[{"kind": "fixture", "reference": "not-the-discovery"}]
                ),
                "provenance must include discovery reference",
            ),
        )
        for index, (name, mutate, message) in enumerate(cases):
            with self.subTest(case=name):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    create_workspace(root)
                    discovery_id = f"lineage-discovery-{index}"
                    target_id = f"lineage-target-{index}"
                    promote_fixture(root, discovery_id, target_id)
                    discovery_path = root / "discoveries" / f"{discovery_id}.md"
                    target_path = root / "projects" / f"{target_id}.md"
                    discovery = yaml.safe_load(discovery_path.read_text(encoding="utf-8").split("---", 2)[1])
                    target = yaml.safe_load(target_path.read_text(encoding="utf-8").split("---", 2)[1])
                    mutate(discovery, target)
                    write_record(root, "discoveries", discovery, "A unique promotable signal.\n")
                    write_record(root, "projects", target, "A unique promotable signal.\n")
                    lint = run_kos(root, "lint")
                    self.assertNotEqual(lint.returncode, 0)
                    self.assertIn(message, lint.stderr)

    def test_promotion_fault_rolls_back_exact_canonical_and_index_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = write_input(
                root,
                discovery_metadata("faulted-promotion"),
                "A unique fault-injected promotion.\n",
            )
            self.assertEqual(run_kos(root, "discovery", "add", input_path.name).returncode, 0)
            before = snapshot_files(root)
            original_atomic_write = discovery_module.atomic_write
            failure_injected = False

            def fail_after_discovery_write(path: Path, content: bytes) -> None:
                nonlocal failure_injected
                original_atomic_write(path, content)
                if path == root / "discoveries" / "faulted-promotion.md" and not failure_injected:
                    failure_injected = True
                    raise OSError("injected live commit failure")

            with patch.object(discovery_module, "atomic_write", side_effect=fail_after_discovery_write):
                with self.assertRaises(discovery_module.DiscoveryError) as failure:
                    discovery_module.promote_discovery(
                        Workspace(root),
                        "faulted-promotion",
                        target_id="faulted-target",
                        title="Faulted target",
                        scope="project:demo",
                    )
            self.assertIn("canonical corpus and indexes were restored", str(failure.exception))
            self.assertEqual(before, snapshot_files(root))

    def test_exclusive_create_fsync_failure_removes_partial_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = write_input(
                root,
                discovery_metadata("exclusive-create-failure"),
                "A unique exclusive-create failure.\n",
            )
            self.assertEqual(run_kos(root, "discovery", "add", input_path.name).returncode, 0)
            before = snapshot_files(root)
            original_stage_and_verify = discovery_module._stage_and_verify
            original_fsync = discovery_module.os.fsync
            stage_complete = False

            def mark_stage_complete(stage: Workspace) -> tuple[list[object], int]:
                nonlocal stage_complete
                result = original_stage_and_verify(stage)
                stage_complete = True
                return result

            def fail_live_fsync(file_descriptor: int) -> None:
                if stage_complete:
                    raise OSError("injected exclusive-create fsync failure")
                original_fsync(file_descriptor)

            with (
                patch.object(discovery_module, "_stage_and_verify", side_effect=mark_stage_complete),
                patch.object(discovery_module.os, "fsync", side_effect=fail_live_fsync),
            ):
                with self.assertRaises(discovery_module.DiscoveryError) as failure:
                    discovery_module.promote_discovery(
                        Workspace(root),
                        "exclusive-create-failure",
                        target_id="exclusive-create-target",
                        title="Exclusive create target",
                        scope="project:demo",
                    )
            self.assertIn("canonical corpus and indexes were restored", str(failure.exception))
            self.assertEqual(before, snapshot_files(root))

    def test_newly_appeared_promotion_target_is_not_overwritten_or_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            input_path = write_input(
                root,
                discovery_metadata("appeared-target"),
                "A unique newly appeared target.\n",
            )
            self.assertEqual(run_kos(root, "discovery", "add", input_path.name).returncode, 0)
            before = snapshot_files(root)
            target_path = root / "projects" / "appeared-target-record.md"
            appeared_bytes = b"external writer bytes\n"
            original_stage_and_verify = discovery_module._stage_and_verify

            def appear_after_stage(stage: Workspace) -> tuple[list[object], int]:
                result = original_stage_and_verify(stage)
                target_path.write_bytes(appeared_bytes)
                return result

            with patch.object(discovery_module, "_stage_and_verify", side_effect=appear_after_stage):
                with self.assertRaises(discovery_module.DiscoveryError) as failure:
                    discovery_module.promote_discovery(
                        Workspace(root),
                        "appeared-target",
                        target_id="appeared-target-record",
                        title="Appeared target",
                        scope="project:demo",
                    )
            self.assertIn("expected projects/appeared-target-record.md to remain absent", str(failure.exception))
            self.assertEqual(snapshot_files(root), {**before, Path("projects/appeared-target-record.md"): appeared_bytes})


if __name__ == "__main__":
    unittest.main()
