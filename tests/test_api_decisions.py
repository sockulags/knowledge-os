"""End-to-end tests for the editor's read fields and the decision lifecycle
endpoints: ``POST /api/records/{id}/accept``, ``/withdraw``, ``/supersede``,
plus ``POST /api/preview``.

One real ``kos-read`` server serves one temporary workspace for the whole
class; every test creates its own decisions through the write API so the
tests stay independent. The supersede reindex-failure path runs in process
against the adapter, since it needs the core's index refresh to fail.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import yaml
from reader_support import FIXTURE_GOVERNING_IDS, FIXTURE_PROJECT_ID, serve, write_decision_fixture
from test_api_write import TOKEN_HEADER, _note, _request

from knowledge_os import mutations as mutations_module
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace, WorkspaceError, validate_workspace

PORT = 8843
SCOPE = f"project:{FIXTURE_PROJECT_ID}"


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---\n")[1])


def _draft_decision(record_id: str, **overrides: object) -> dict[str, object]:
    return _note(record_id, type="project", scope=SCOPE, record_kind="decision", status="draft", **overrides)


class DecisionApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        directory = cls._stack.enter_context(tempfile.TemporaryDirectory())
        cls.root = Path(directory)
        write_decision_fixture(cls.root)
        cls.base_url = cls._stack.enter_context(serve(cls.root, PORT))
        status, session = _request(cls.base_url, "GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def write(self, method: str, path: str, payload: object, **headers: str) -> tuple[int, dict]:
        return _request(self.base_url, method, path, payload, headers={TOKEN_HEADER: self.token, **headers})

    def create(self, metadata: dict[str, object], body: str = "Decision body.\n") -> dict:
        status, result = self.write("POST", "/api/records", {"metadata": metadata, "body": body})
        self.assertEqual(status, 201, result)
        return result

    def path(self, relative: str) -> Path:
        return self.root / relative

    def sha(self, relative: str) -> str:
        return hashlib.sha256(self.path(relative).read_bytes()).hexdigest()

    def get(self, record_id: str) -> dict:
        status, data = _request(self.base_url, "GET", f"/api/records/{record_id}")
        self.assertEqual(status, 200, data)
        return data

    def assert_workspace_valid(self) -> None:
        _documents, issues = validate_workspace(Workspace(self.root))
        self.assertEqual(issues, [])

    # -- read fields ------------------------------------------------------------

    def test_record_payload_carries_the_editable_source_and_its_hash(self) -> None:
        created = self.create(_note("editable-read-note", tags=["alpha"]), "# Heading\n\nRaw *body*.\n")

        editing = self.get("editable-read-note")["editing"]

        self.assertTrue(editing["editable"])
        self.assertEqual(editing["raw_body"], "# Heading\n\nRaw *body*.\n")
        self.assertEqual(editing["content_sha256"], created["content_sha256"])
        self.assertEqual(editing["content_sha256"], self.sha(created["path"]))
        self.assertEqual(
            editing["metadata"],
            {"title": "Editable read note", "tags": ["alpha"], "related": [], "sources": []},
        )
        self.assertIsNone(editing["decision_actions"])
        self.assertFalse(editing["body_change_needs_confirmation"])

    def test_decision_actions_follow_the_decision_state(self) -> None:
        self.create(_draft_decision("actions-plain-draft"))
        self.create(_draft_decision("actions-replacement-draft", supersedes=[FIXTURE_GOVERNING_IDS[2]]))

        plain = self.get("actions-plain-draft")["editing"]
        actions = plain["decision_actions"]
        self.assertEqual(
            {key: actions[key] for key in ("accept", "withdraw", "supersede", "propose_replacement")},
            {"accept": True, "withdraw": True, "supersede": None, "propose_replacement": False},
        )
        self.assertEqual(set(actions["dialogs"]), {"accept", "withdraw"})
        self.assertEqual(plain["project_id"], FIXTURE_PROJECT_ID)

        replacement = self.get("actions-replacement-draft")["editing"]["decision_actions"]
        self.assertFalse(replacement["accept"])
        self.assertTrue(replacement["withdraw"])
        target = f"projects/{FIXTURE_PROJECT_ID}/{FIXTURE_GOVERNING_IDS[2]}.md"
        self.assertEqual(replacement["supersede"]["id"], FIXTURE_GOVERNING_IDS[2])
        self.assertEqual(replacement["supersede"]["content_sha256"], self.sha(target))

        active = self.get(FIXTURE_GOVERNING_IDS[2])["editing"]
        self.assertTrue(active["decision_actions"]["propose_replacement"])
        self.assertFalse(active["decision_actions"]["accept"])
        self.assertTrue(active["body_change_needs_confirmation"])

        # Leave the governing decision without a competing replacement.
        status, _ = self.write(
            "POST",
            "/api/records/actions-replacement-draft/withdraw",
            {"expected_sha256": self.sha(f"projects/{FIXTURE_PROJECT_ID}/actions-replacement-draft.md"), "reason": "test"},
        )
        self.assertEqual(status, 200)

    # -- accept -----------------------------------------------------------------

    def test_accept_activates_a_draft_with_an_interface_reference(self) -> None:
        created = self.create(_draft_decision("accepted-decision"))

        status, result = self.write(
            "POST", "/api/records/accepted-decision/accept", {"expected_sha256": created["content_sha256"]}
        )

        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["content_sha256"], self.sha(created["path"]))
        self.assertTrue(result["index"]["refreshed"])
        acceptance = [
            item for item in _frontmatter(self.path(created["path"]))["provenance"]
            if item["kind"] == "decision-acceptance"
        ]
        self.assertEqual(len(acceptance), 1)
        self.assertRegex(acceptance[0]["reference"], r"^interface:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ:accept$")
        self.assert_workspace_valid()

    def test_accept_with_a_stale_hash_is_a_conflict(self) -> None:
        created = self.create(_draft_decision("stale-accept-decision"))
        before = self.sha(created["path"])

        status, result = self.write(
            "POST", "/api/records/stale-accept-decision/accept", {"expected_sha256": "0" * 64}
        )

        self.assertEqual(status, 409, result)
        self.assertEqual(result["error"], "conflict")
        self.assertEqual(result["current_sha256"], before)
        self.assertEqual(self.sha(created["path"]), before)

    def test_accept_refuses_a_decision_that_is_not_draft(self) -> None:
        relative = f"projects/{FIXTURE_PROJECT_ID}/{FIXTURE_GOVERNING_IDS[0]}.md"
        status, result = self.write(
            "POST", f"/api/records/{FIXTURE_GOVERNING_IDS[0]}/accept", {"expected_sha256": self.sha(relative)}
        )
        self.assertEqual(status, 422, result)
        self.assertIn("must be draft before acceptance", result["detail"])

    def test_accept_refuses_an_ordinary_record(self) -> None:
        created = self.create(_note("ordinary-accept-note"))
        status, result = self.write(
            "POST", "/api/records/ordinary-accept-note/accept", {"expected_sha256": created["content_sha256"]}
        )
        self.assertEqual(status, 422, result)
        self.assertIn("is not a decision", result["detail"])

    # -- withdraw ---------------------------------------------------------------

    def test_withdraw_archives_a_draft_with_the_reason(self) -> None:
        created = self.create(_draft_decision("withdrawn-decision"))

        status, result = self.write(
            "POST",
            "/api/records/withdrawn-decision/withdraw",
            {"expected_sha256": created["content_sha256"], "reason": "Overtaken by events"},
        )

        self.assertEqual(status, 200, result)
        self.assertEqual(result["status"], "archived")
        provenance = _frontmatter(self.path(created["path"]))["provenance"]
        self.assertIn({"kind": "decision-withdrawal", "reference": "Overtaken by events"},
                      [{k: item[k] for k in ("kind", "reference")} for item in provenance])
        self.assert_workspace_valid()

    def test_withdraw_requires_a_reason_and_a_draft(self) -> None:
        created = self.create(_draft_decision("reasonless-decision"))
        status, result = self.write(
            "POST", "/api/records/reasonless-decision/withdraw", {"expected_sha256": created["content_sha256"]}
        )
        self.assertEqual(status, 400, result)
        status, result = self.write(
            "POST",
            "/api/records/reasonless-decision/withdraw",
            {"expected_sha256": created["content_sha256"], "reason": "   "},
        )
        self.assertEqual(status, 400, result)

        relative = f"projects/{FIXTURE_PROJECT_ID}/{FIXTURE_GOVERNING_IDS[0]}.md"
        status, result = self.write(
            "POST",
            f"/api/records/{FIXTURE_GOVERNING_IDS[0]}/withdraw",
            {"expected_sha256": self.sha(relative), "reason": "no"},
        )
        self.assertEqual(status, 422, result)
        self.assertIn("must be draft before withdrawal", result["detail"])

    def test_withdraw_with_a_stale_hash_is_a_conflict(self) -> None:
        created = self.create(_draft_decision("stale-withdraw-decision"))
        status, result = self.write(
            "POST",
            "/api/records/stale-withdraw-decision/withdraw",
            {"expected_sha256": "f" * 64, "reason": "late"},
        )
        self.assertEqual(status, 409, result)
        self.assertEqual(result["current_sha256"], created["content_sha256"])

    # -- supersede --------------------------------------------------------------

    def test_supersede_activates_the_replacement_and_retires_the_old_decision(self) -> None:
        old_id = FIXTURE_GOVERNING_IDS[1]
        old_relative = f"projects/{FIXTURE_PROJECT_ID}/{old_id}.md"
        created = self.create(_draft_decision("beta-replacement", supersedes=[old_id]))

        status, result = self.write(
            "POST",
            "/api/records/beta-replacement/supersede",
            {
                "expected_sha256": created["content_sha256"],
                "old_id": old_id,
                "old_expected_sha256": self.sha(old_relative),
            },
        )

        self.assertEqual(status, 200, result)
        self.assertEqual(result["id"], "beta-replacement")
        self.assertEqual(result["status"], "active")
        self.assertEqual(result["content_sha256"], self.sha(created["path"]))
        self.assertEqual(result["replaced"]["id"], old_id)
        self.assertEqual(result["replaced"]["status"], "superseded")
        self.assertEqual(result["replaced"]["path"], old_relative)
        self.assertEqual(result["replaced"]["content_sha256"], self.sha(old_relative))
        self.assertTrue(result["index"]["refreshed"])
        acceptance = [
            item for item in _frontmatter(self.path(created["path"]))["provenance"]
            if item["kind"] == "decision-acceptance"
        ]
        self.assertTrue(acceptance[0]["reference"].endswith(":supersede"))
        self.assertEqual(_frontmatter(self.path(old_relative))["status"], "superseded")
        self.assert_workspace_valid()

    def test_supersede_with_a_stale_old_hash_is_a_conflict_and_writes_nothing(self) -> None:
        old_id = FIXTURE_GOVERNING_IDS[0]
        old_relative = f"projects/{FIXTURE_PROJECT_ID}/{old_id}.md"
        created = self.create(_draft_decision("alpha-stale-replacement", supersedes=[old_id]))
        old_before = self.sha(old_relative)

        status, result = self.write(
            "POST",
            "/api/records/alpha-stale-replacement/supersede",
            {"expected_sha256": created["content_sha256"], "old_id": old_id, "old_expected_sha256": "a" * 64},
        )

        self.assertEqual(status, 409, result)
        self.assertEqual(result["current_sha256"], old_before)
        self.assertEqual(self.sha(old_relative), old_before)
        self.assertEqual(self.sha(created["path"]), created["content_sha256"])
        # Clean up so later tests see no competing replacement for alpha.
        status, _ = self.write(
            "POST",
            "/api/records/alpha-stale-replacement/withdraw",
            {"expected_sha256": created["content_sha256"], "reason": "test cleanup"},
        )
        self.assertEqual(status, 200)

    def test_supersede_refuses_a_draft_that_does_not_declare_the_old_decision(self) -> None:
        old_id = FIXTURE_GOVERNING_IDS[0]
        old_relative = f"projects/{FIXTURE_PROJECT_ID}/{old_id}.md"
        created = self.create(_draft_decision("undeclared-replacement"))

        status, result = self.write(
            "POST",
            "/api/records/undeclared-replacement/supersede",
            {
                "expected_sha256": created["content_sha256"],
                "old_id": old_id,
                "old_expected_sha256": self.sha(old_relative),
            },
        )

        self.assertEqual(status, 422, result)
        self.assertIn("must declare supersedes", result["detail"])

    def test_supersede_requires_both_hashes_and_the_old_id(self) -> None:
        status, result = self.write(
            "POST", "/api/records/whatever/supersede", {"expected_sha256": "0" * 64, "old_id": "x"}
        )
        self.assertEqual(status, 400, result)
        self.assertIn("old_expected_sha256", result["detail"])

    # -- guard ------------------------------------------------------------------

    def test_lifecycle_actions_and_preview_without_the_token_are_refused(self) -> None:
        created = self.create(_draft_decision("tokenless-decision"))
        payloads = {
            "/api/records/tokenless-decision/accept": {"expected_sha256": created["content_sha256"]},
            "/api/records/tokenless-decision/withdraw": {"expected_sha256": created["content_sha256"], "reason": "x"},
            "/api/records/tokenless-decision/supersede": {
                "expected_sha256": created["content_sha256"],
                "old_id": FIXTURE_GOVERNING_IDS[0],
                "old_expected_sha256": "0" * 64,
            },
            "/api/preview": {"body": "x"},
        }
        for path, payload in payloads.items():
            with self.subTest(path=path):
                status, result = _request(self.base_url, "POST", path, payload)
                self.assertEqual(status, 403, result)
                status, result = self.write("POST", path, payload, Origin="https://evil.example")
                self.assertEqual(status, 403, result)
        self.assertEqual(self.sha(created["path"]), created["content_sha256"])

    # -- preview ----------------------------------------------------------------

    def test_preview_renders_like_the_record_page(self) -> None:
        status, result = self.write("POST", "/api/preview", {"body": "# Title\n\nSome **bold** text.\n"})
        self.assertEqual(status, 200, result)
        self.assertNotIn("<h1", result["html"])
        self.assertIn("<strong>bold</strong>", result["html"])


class SupersedeReindexFailureTests(unittest.TestCase):
    def test_supersede_reports_an_index_failure_with_both_new_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_decision_fixture(root)
            workspace = Workspace(root)
            old_id = FIXTURE_GOVERNING_IDS[0]
            old_path = root / "projects" / FIXTURE_PROJECT_ID / f"{old_id}.md"
            created = library.create_record(
                workspace, metadata=_draft_decision("index-failure-replacement", supersedes=[old_id]), body="x\n"
            )
            new_path = root / created.path

            broken = WorkspaceError("derived indexes could not be rebuilt")
            with patch.object(mutations_module, "refresh_derived_indexes", side_effect=broken):
                result = library.supersede_record(
                    workspace,
                    "index-failure-replacement",
                    expected_sha256=created.content_sha256,
                    old_id=old_id,
                    old_expected_sha256=hashlib.sha256(old_path.read_bytes()).hexdigest(),
                )

            self.assertFalse(result.replacement.index_refreshed)
            self.assertIn("could not be rebuilt", result.replacement.index_error)
            self.assertEqual(result.replacement.status, "active")
            self.assertEqual(result.replaced.status, "superseded")
            self.assertEqual(result.replacement.content_sha256, hashlib.sha256(new_path.read_bytes()).hexdigest())
            self.assertEqual(result.replaced.content_sha256, hashlib.sha256(old_path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
