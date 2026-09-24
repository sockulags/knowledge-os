from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import knowledge_os.mutations as mutations_module
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


def write_record(path: Path, metadata: dict[str, object], body: str = "Durable body.\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\n{body}",
        encoding="utf-8",
    )


def metadata(path: Path) -> dict[str, object]:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_workspace(root: Path) -> None:
    (root / "knowledge-os.toml").write_text(
        '[workspace]\nname = "mutation-test"\nversion = 1\n',
        encoding="utf-8",
    )
    for directory in ("knowledge", "projects", "sources", "memory", "syntheses", "discoveries", "skills", "indexes"):
        (root / directory).mkdir()
    write_record(
        root / "projects" / "demo" / "README.md",
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
        "Demo project overview.\n",
    )


def index_workspace(root: Path) -> None:
    result = run_kos(root, "index")
    if result.returncode:
        raise AssertionError(result.stderr)


class MutationTests(unittest.TestCase):
    def test_update_uses_exact_hash_and_stale_writer_cannot_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            record = root / "knowledge" / "shared-note.md"
            base = {
                "id": "shared-note",
                "title": "Shared note",
                "type": "knowledge",
                "status": "active",
                "scope": "general",
                "created": "2026-08-29",
                "updated": "2026-08-29",
                "provenance": [{"kind": "fixture", "reference": "shared"}],
            }
            write_record(record, base, "Version zero.\n")
            index_workspace(root)
            original_hash = digest(record)

            first = root / "first.md"
            first_metadata = {**base, "updated": "2026-09-12"}
            write_record(first, first_metadata, "First writer.\n")
            updated = run_kos(root, "update", first.name, "--expected-sha256", original_hash, "--json")
            self.assertEqual(updated.returncode, 0, updated.stderr)
            self.assertEqual(json.loads(updated.stdout)["sha256"], digest(record))

            second = root / "second.md"
            write_record(second, first_metadata, "Stale second writer.\n")
            before = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            stale = run_kos(root, "update", second.name, "--expected-sha256", original_hash)
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("the record changed after it was read", stale.stderr)
            after = {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_decision_acceptance_and_editorial_update_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            decision = root / "projects" / "demo" / "delivery-policy.md"
            draft = {
                "id": "delivery-policy",
                "title": "Delivery policy",
                "type": "project",
                "record_kind": "decision",
                "status": "draft",
                "scope": "project:demo",
                "created": "2026-08-29",
                "updated": "2026-08-29",
                "provenance": [{"kind": "proposal", "reference": "proposal:delivery"}],
            }
            write_record(decision, draft, "Use the narrow delivery path.\n")
            index_workspace(root)

            accepted = run_kos(
                root,
                "decision",
                "accept",
                "delivery-policy",
                "--expected-sha256",
                digest(decision),
                "--acceptance-reference",
                "conversation:accepted",
                "--json",
            )
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            accepted_metadata = metadata(decision)
            self.assertEqual(accepted_metadata["status"], "active")
            self.assertIn("decision-acceptance", {item["kind"] for item in accepted_metadata["provenance"]})

            candidate = root / "editorial.md"
            write_record(candidate, accepted_metadata, "Use the narrow and reversible delivery path.\n")
            refused = run_kos(root, "update", candidate.name, "--expected-sha256", digest(decision))
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("requires --confirm-non-material", refused.stderr)
            missing_reference = run_kos(
                root,
                "update",
                candidate.name,
                "--expected-sha256",
                digest(decision),
                "--confirm-non-material",
            )
            self.assertNotEqual(missing_reference.returncode, 0)
            self.assertIn("--change-reference is required", missing_reference.stderr)
            edited = run_kos(
                root,
                "update",
                candidate.name,
                "--expected-sha256",
                digest(decision),
                "--confirm-non-material",
                "--change-reference",
                "conversation:editorial-approval",
            )
            self.assertEqual(edited.returncode, 0, edited.stderr)
            self.assertIn("editorial-update", {item["kind"] for item in metadata(decision)["provenance"]})

    def test_decision_withdraw_archives_draft_with_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            decision = root / "projects" / "demo" / "pivot-plan.md"
            draft = {
                "id": "pivot-plan",
                "title": "Pivot plan",
                "type": "project",
                "record_kind": "decision",
                "status": "draft",
                "scope": "project:demo",
                "created": "2026-08-29",
                "updated": "2026-08-29",
                "provenance": [{"kind": "proposal", "reference": "proposal:pivot"}],
            }
            write_record(decision, draft, "Pause the project and pivot.\n")
            index_workspace(root)

            withdrawn = run_kos(
                root,
                "decision",
                "withdraw",
                "pivot-plan",
                "--expected-sha256",
                digest(decision),
                "--reason",
                "The owner chose to keep building the standalone project instead.",
                "--json",
            )
            self.assertEqual(withdrawn.returncode, 0, withdrawn.stderr)
            withdrawn_metadata = metadata(decision)
            self.assertEqual(withdrawn_metadata["status"], "archived")
            withdrawal_entries = [
                item for item in withdrawn_metadata["provenance"] if item["kind"] == "decision-withdrawal"
            ]
            self.assertEqual(len(withdrawal_entries), 1)
            self.assertEqual(
                withdrawal_entries[0]["reference"],
                "The owner chose to keep building the standalone project instead.",
            )
            self.assertEqual(run_kos(root, "lint").returncode, 0)

            # An active decision cannot be withdrawn; retiring it is supersede's job.
            active_decision = root / "projects" / "demo" / "active-policy.md"
            write_record(
                active_decision,
                {
                    "id": "active-policy", "title": "Active", "type": "project", "record_kind": "decision",
                    "status": "active", "scope": "project:demo", "created": "2026-08-29", "updated": "2026-08-29",
                    "provenance": [{"kind": "decision-acceptance", "reference": "conversation:old"}],
                },
            )
            index_workspace(root)
            refused_active = run_kos(
                root,
                "decision",
                "withdraw",
                "active-policy",
                "--expected-sha256",
                digest(active_decision),
                "--reason",
                "no longer needed",
            )
            self.assertNotEqual(refused_active.returncode, 0)
            self.assertIn("must be draft before withdrawal", refused_active.stderr)

            # A non-decision record cannot be withdrawn.
            plain = root / "knowledge" / "plain-note.md"
            write_record(
                plain,
                {
                    "id": "plain-note", "title": "Plain", "type": "knowledge",
                    "status": "draft", "scope": "general", "created": "2026-08-29", "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "plain"}],
                },
            )
            index_workspace(root)
            refused_non_decision = run_kos(
                root,
                "decision",
                "withdraw",
                "plain-note",
                "--expected-sha256",
                digest(plain),
                "--reason",
                "no longer needed",
            )
            self.assertNotEqual(refused_non_decision.returncode, 0)
            self.assertIn("is not a decision", refused_non_decision.stderr)

    def test_decision_withdraw_without_a_reason_records_a_neutral_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            draft = {
                "id": "idea-one", "title": "Idea one", "type": "project", "record_kind": "decision",
                "status": "draft", "scope": "project:demo", "created": "2026-08-29", "updated": "2026-08-29",
                "provenance": [{"kind": "proposal", "reference": "proposal:idea"}],
            }
            first = root / "projects" / "demo" / "idea-one.md"
            second = root / "projects" / "demo" / "idea-two.md"
            write_record(first, draft)
            write_record(second, {**draft, "id": "idea-two", "title": "Idea two"})
            index_workspace(root)

            # The core: no reason and no reference records a "kos" stamp.
            result = mutations_module.withdraw_decision(
                Workspace(root), "idea-one", expected_sha256=digest(first), reason="   "
            )
            self.assertEqual(result.status, "archived")
            entry = [item for item in metadata(first)["provenance"] if item["kind"] == "decision-withdrawal"][0]
            self.assertRegex(entry["reference"], r"^kos:\d{4}-\d{2}-\d{2}T[0-9:]+Z:withdraw$")

            # The CLI: --reason is optional and a "cli" stamp is recorded.
            withdrawn = run_kos(root, "decision", "withdraw", "idea-two", "--expected-sha256", digest(second))
            self.assertEqual(withdrawn.returncode, 0, withdrawn.stderr)
            entry = [item for item in metadata(second)["provenance"] if item["kind"] == "decision-withdrawal"][0]
            self.assertRegex(entry["reference"], r"^cli:\d{4}-\d{2}-\d{2}T[0-9:]+Z:withdraw$")
            self.assertEqual(run_kos(root, "lint").returncode, 0)

    def test_decision_withdrawal_provenance_rejected_off_archived_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            hand_edited = root / "knowledge" / "hand-edited.md"
            write_record(
                hand_edited,
                {
                    "id": "hand-edited", "title": "Hand edited", "type": "knowledge",
                    "status": "active", "scope": "general", "created": "2026-08-29", "updated": "2026-08-29",
                    "provenance": [{"kind": "decision-withdrawal", "reference": "not a decision"}],
                },
            )
            result = run_kos(root, "lint")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("only allowed on archived decisions", result.stderr)

    def test_supersede_keeps_old_active_until_replacement_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            old = root / "projects" / "demo" / "old-policy.md"
            new = root / "projects" / "demo" / "new-policy.md"
            write_record(
                old,
                {
                    "id": "old-policy",
                    "title": "Old policy",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "decision-acceptance", "reference": "conversation:old"}],
                },
                "replacement-search-token old rule\n",
            )
            write_record(
                new,
                {
                    "id": "new-policy",
                    "title": "New policy",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "draft",
                    "scope": "project:demo",
                    "created": "2026-09-12",
                    "updated": "2026-09-12",
                    "provenance": [{"kind": "proposal", "reference": "proposal:new"}],
                    "supersedes": ["old-policy"],
                },
                "replacement-search-token new rule\n",
            )
            index_workspace(root)
            direct_accept = run_kos(
                root,
                "decision",
                "accept",
                "new-policy",
                "--expected-sha256",
                digest(new),
                "--acceptance-reference",
                "conversation:new",
            )
            self.assertNotEqual(direct_accept.returncode, 0)
            self.assertIn("use 'kos supersede'", direct_accept.stderr)
            self.assertEqual(metadata(old)["status"], "active")
            self.assertEqual(metadata(new)["status"], "draft")

            result = run_kos(
                root,
                "supersede",
                "old-policy",
                "new-policy",
                "--expected-old-sha256",
                digest(old),
                "--expected-new-sha256",
                digest(new),
                "--acceptance-reference",
                "conversation:new-accepted",
                "--json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(metadata(old)["status"], "superseded")
            self.assertEqual(metadata(new)["status"], "active")
            self.assertEqual(run_kos(root, "lint").returncode, 0)
            context = run_kos(
                root,
                "context",
                "--project",
                "demo",
                "--task",
                "replacement-search-token",
                "--budget",
                "12000",
            )
            self.assertEqual(context.returncode, 0, context.stderr)
            manifest = json.loads(context.stdout.split("```json\n", 1)[1].split("\n```", 1)[0])
            ids = {item["id"] for item in manifest["items"]}
            self.assertIn("new-policy", ids)
            self.assertNotIn("old-policy", ids)

            partial_new = metadata(new)
            partial_new["status"] = "draft"
            partial_new["provenance"] = [
                item for item in partial_new["provenance"] if item["kind"] != "decision-acceptance"
            ]
            write_record(new, partial_new, "replacement-search-token new rule\n")
            partial = run_kos(root, "lint")
            self.assertNotEqual(partial.returncode, 0)
            self.assertIn("must target an active decision", partial.stderr)
            self.assertIn("requires exactly one effective replacement", partial.stderr)

    def test_caught_supersede_write_failure_restores_both_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            old = root / "projects" / "demo" / "old-policy.md"
            new = root / "projects" / "demo" / "new-policy.md"
            write_record(
                old,
                {
                    "id": "old-policy", "title": "Old", "type": "project", "record_kind": "decision",
                    "status": "active", "scope": "project:demo", "created": "2026-08-29", "updated": "2026-08-29",
                    "provenance": [{"kind": "decision-acceptance", "reference": "conversation:old"}],
                },
            )
            write_record(
                new,
                {
                    "id": "new-policy", "title": "New", "type": "project", "record_kind": "decision",
                    "status": "draft", "scope": "project:demo", "created": "2026-09-12", "updated": "2026-09-12",
                    "provenance": [{"kind": "proposal", "reference": "proposal:new"}], "supersedes": ["old-policy"],
                },
            )
            index_workspace(root)
            old_before = old.read_bytes()
            new_before = new.read_bytes()
            real_atomic_write = mutations_module.atomic_write
            failed = False

            def fail_old_live_once(path: Path, content: bytes) -> None:
                nonlocal failed
                if path == old and not failed:
                    failed = True
                    raise OSError("injected pair failure")
                real_atomic_write(path, content)

            with (
                patch.object(mutations_module, "atomic_write", side_effect=fail_old_live_once),
                self.assertRaises(mutations_module.MutationError) as failure,
            ):
                mutations_module.supersede_decision(
                    Workspace(root),
                    "old-policy",
                    "new-policy",
                    expected_old_sha256=digest(old),
                    expected_new_sha256=digest(new),
                    acceptance_reference="conversation:new",
                )
            self.assertIn("original bytes were restored", str(failure.exception))
            self.assertEqual(old.read_bytes(), old_before)
            self.assertEqual(new.read_bytes(), new_before)


if __name__ == "__main__":
    unittest.main()
