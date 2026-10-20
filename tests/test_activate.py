"""Making a draft active: the core's ``activate_draft``, ``kos activate``, and
``POST /api/records/{id}/activate``.

A draft promoted from an observation, or a note an agent saved, becomes
knowledge only when a person makes it active; decisions are accepted instead.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

import yaml
from reader_support import FIXTURE_GOVERNING_IDS, FIXTURE_PROJECT_ID, serve, write_decision_fixture
from test_api_write import TOKEN_HEADER, _note, _request
from test_discovery import create_workspace, promote_fixture, run_kos

from knowledge_os.mutations import MutationError, StaleRevisionError, activate_draft
from knowledge_os.workspace import Workspace, validate_workspace

PROMOTED = Path("projects") / "demo" / "promoted-project-fact.md"


def _metadata(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ActivateDraftTests(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        create_workspace(self.root)
        promote_fixture(self.root)
        self.workspace = Workspace(self.root)
        self.target = self.root / PROMOTED

    def test_a_promoted_draft_becomes_active_with_activation_provenance(self) -> None:
        self.assertEqual(_metadata(self.target)["status"], "draft")

        result = activate_draft(
            self.workspace,
            "promoted-project-fact",
            expected_sha256=_sha(self.target),
            activation_reference="person:lucas",
        )

        self.assertEqual(result.status, "active")
        self.assertEqual(result.sha256, _sha(self.target))
        metadata = _metadata(self.target)
        self.assertEqual(metadata["status"], "active")
        self.assertEqual(metadata["provenance"][0], {"kind": "discovery", "reference": "promotable-signal"})
        activation = metadata["provenance"][-1]
        self.assertEqual(activation["kind"], "draft-activation")
        self.assertEqual(activation["reference"], "person:lucas")
        self.assertIn("captured", activation)
        self.assertEqual(validate_workspace(self.workspace)[1], [])

    def test_an_active_record_is_refused(self) -> None:
        activate_draft(
            self.workspace, "promoted-project-fact", expected_sha256=_sha(self.target), activation_reference="a"
        )
        before = self.target.read_bytes()
        with self.assertRaisesRegex(MutationError, "must be draft before activation"):
            activate_draft(
                self.workspace, "promoted-project-fact", expected_sha256=_sha(self.target), activation_reference="b"
            )
        self.assertEqual(self.target.read_bytes(), before)

    def test_a_decision_is_refused(self) -> None:
        decision = self.root / "projects" / "demo" / "draft-policy.md"
        decision.write_text(
            "---\n"
            + yaml.safe_dump(
                {
                    "id": "draft-policy",
                    "title": "Draft policy",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "draft",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "proposal", "reference": "proposal:policy"}],
                },
                sort_keys=False,
            )
            + "---\n\nPolicy.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(MutationError, "use 'kos decision accept'"):
            activate_draft(self.workspace, "draft-policy", expected_sha256=_sha(decision), activation_reference="a")
        self.assertEqual(_metadata(decision)["status"], "draft")

    def test_a_stale_hash_writes_nothing(self) -> None:
        before = self.target.read_bytes()
        with self.assertRaises(StaleRevisionError):
            activate_draft(
                self.workspace, "promoted-project-fact", expected_sha256="0" * 64, activation_reference="a"
            )
        self.assertEqual(self.target.read_bytes(), before)

    def test_an_update_cannot_remove_the_activation(self) -> None:
        activate_draft(
            self.workspace, "promoted-project-fact", expected_sha256=_sha(self.target), activation_reference="a"
        )
        metadata = _metadata(self.target)
        metadata["provenance"] = metadata["provenance"][:-1]
        candidate = self.root / "candidate.md"
        candidate.write_text(f"---\n{yaml.safe_dump(metadata, sort_keys=False)}---\n\nBody.\n", encoding="utf-8")
        refused = run_kos(self.root, "update", candidate.name, "--expected-sha256", _sha(self.target))
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("draft-activation", refused.stderr)

    def test_cli_activates_with_a_neutral_reference_and_reports_json(self) -> None:
        activated = run_kos(
            self.root, "activate", "promoted-project-fact", "--expected-sha256", _sha(self.target), "--json"
        )

        self.assertEqual(activated.returncode, 0, activated.stderr)
        payload = json.loads(activated.stdout)
        self.assertEqual(payload["status"], "active")
        self.assertEqual(payload["sha256"], _sha(self.target))
        activation = _metadata(self.target)["provenance"][-1]
        self.assertEqual(activation["kind"], "draft-activation")
        self.assertRegex(activation["reference"], r"^cli:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ:activate$")

        again = run_kos(self.root, "activate", "promoted-project-fact", "--expected-sha256", _sha(self.target))
        self.assertEqual(again.returncode, 1)
        self.assertIn("must be draft before activation", again.stderr)


class ActivateApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        directory = cls._stack.enter_context(tempfile.TemporaryDirectory())
        cls.root = Path(directory)
        write_decision_fixture(cls.root)
        cls.base_url = cls._stack.enter_context(serve(cls.root))
        status, session = _request(cls.base_url, "GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def write(self, method: str, path: str, payload: object) -> tuple[int, dict]:
        return _request(self.base_url, method, path, payload, headers={TOKEN_HEADER: self.token})

    def create_draft(self, record_id: str) -> dict:
        status, result = self.write(
            "POST", "/api/records", {"metadata": _note(record_id, status="draft"), "body": "Note body.\n"}
        )
        self.assertEqual(status, 201, result)
        return result

    def test_the_record_page_offers_make_active_only_on_a_draft_that_is_not_a_decision(self) -> None:
        self.create_draft("offered-draft-note")

        status, data = _request(self.base_url, "GET", "/api/records/offered-draft-note")
        self.assertEqual(status, 200, data)
        activation = data["editing"]["draft_activation"]
        self.assertEqual(activation["label"], "Make active")
        self.assertIn("Undo", activation["labels"].values())
        self.assertEqual(activation["outcome"]["status"]["value"], "Current")
        self.assertIn("Offered draft note", activation["outcome"]["notice"])

        governing = _request(self.base_url, "GET", f"/api/records/{FIXTURE_GOVERNING_IDS[0]}")[1]
        self.assertIsNone(governing["editing"]["draft_activation"])

    def test_activate_makes_the_draft_active_with_an_interface_reference(self) -> None:
        created = self.create_draft("activated-draft-note")

        status, result = self.write(
            "POST", "/api/records/activated-draft-note/activate", {"expected_sha256": created["content_sha256"]}
        )

        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "active")
        path = self.root / created["path"]
        self.assertEqual(result["content_sha256"], _sha(path))
        activation = _metadata(path)["provenance"][-1]
        self.assertEqual(activation["kind"], "draft-activation")
        self.assertRegex(activation["reference"], r"^interface:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ:activate$")
        self.assertEqual(validate_workspace(Workspace(self.root))[1], [])

        page = _request(self.base_url, "GET", "/api/records/activated-draft-note")[1]
        self.assertIsNone(page["editing"]["draft_activation"])

    def test_an_agent_labelled_request_is_forbidden(self) -> None:
        created = self.create_draft("agent-activation-note")
        before = (self.root / created["path"]).read_bytes()

        status, result = self.write(
            "POST",
            "/api/records/agent-activation-note/activate",
            {"expected_sha256": created["content_sha256"], "agent": {"client": "claude-code"}},
        )

        self.assertEqual(status, 403, result)
        self.assertEqual(result["error"], "forbidden")
        self.assertEqual((self.root / created["path"]).read_bytes(), before)

    def test_a_stale_hash_is_a_conflict_and_a_decision_is_refused(self) -> None:
        created = self.create_draft("stale-activation-note")
        status, result = self.write(
            "POST", "/api/records/stale-activation-note/activate", {"expected_sha256": "0" * 64}
        )
        self.assertEqual(status, 409, result)
        self.assertEqual(result["current_sha256"], created["content_sha256"])

        relative = f"projects/{FIXTURE_PROJECT_ID}/{FIXTURE_GOVERNING_IDS[0]}.md"
        status, result = self.write(
            "POST",
            f"/api/records/{FIXTURE_GOVERNING_IDS[0]}/activate",
            {"expected_sha256": _sha(self.root / relative)},
        )
        self.assertEqual(status, 422, result)
        self.assertIn("is a decision", result["detail"])


if __name__ == "__main__":
    unittest.main()
