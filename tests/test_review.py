"""Configurable review (issue #86): the rules in ``knowledge-os.toml``,
proposed changes in ``proposals/``, the local API that holds writes back and
applies or drops them, and what an MCP agent is told."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from test_agent_mcp import CALLER, GIT, PORT as _MCP_PORT, IsolatedTestCase, _session_token, git, write_runtime_file
from test_api_write import TOKEN_HEADER, _request

from knowledge_os.agent_access.tools import call_tool
from knowledge_os.init_workspace import init_workspace
from knowledge_os.model import render_document
from knowledge_os.mutations import StaleRevisionError
from knowledge_os.review import (
    ReviewError,
    ReviewPolicyError,
    Writer,
    accept_proposal,
    discard_proposal,
    list_proposals,
    load_policy,
    needs_review,
    propose,
)
from knowledge_os.structure import create_folder, create_project
from knowledge_os.workspace import Workspace
from reader_support import serve

PORT = 8883
MCP_PORT = _MCP_PORT + 30
PROVENANCE = [{"kind": "fixture", "reference": "test:review"}]
AGENT = {"kind": "agent-authored", "reference": "agent:claude-code:repo"}

RULES = """
[[review.rule]]
folder = "drafts"
action = "direct"

[[review.rule]]
writer = "agent"
project = "acme"

[[review.rule]]
writer = "referat"
writes = "create"
"""


def _page(record_id: str, body: str = "Text.\n", **extra: object) -> str:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": record_id.replace("-", " ").capitalize(),
        "type": "project",
        "status": "active",
        "scope": "project:acme",
        "created": "2026-09-27",
        "updated": "2026-09-27",
        "provenance": [AGENT],
    }
    metadata.update(extra)
    return render_document(metadata, body).decode("utf-8")


class PolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")
        self.workspace = Workspace(self.root)

    def write_rules(self, text: str) -> None:
        with (self.root / "knowledge-os.toml").open("a", encoding="utf-8") as handle:
            handle.write(text)

    def test_without_rules_everything_is_direct(self) -> None:
        self.assertEqual(load_policy(self.workspace), ())
        self.assertIsNone(
            needs_review((), writer=Writer("agent", "claude-code"), project="acme", folder="", write="create")
        )

    def test_the_first_matching_rule_decides(self) -> None:
        self.write_rules(RULES)
        rules = load_policy(self.workspace)

        def review(kind: str, project: str | None, folder: str = "", write: str = "create", client: str | None = None):
            return needs_review(rules, writer=Writer(kind, client), project=project, folder=folder, write=write)

        self.assertEqual(review("agent", "acme", client="codex").number, 2)
        self.assertIsNone(review("agent", "acme", "drafts/june"))  # rule 1: direct
        self.assertIsNone(review("agent", "beta"))
        self.assertIsNone(review("person", "acme"))
        self.assertEqual(review("referat", "beta").number, 3)
        self.assertIsNone(review("referat", "beta", write="edit"))
        self.assertIsNone(review("agent", None))
        self.assertIn("agents in project acme", rules[1].describe())

    def test_one_agent_and_general_knowledge(self) -> None:
        self.write_rules('[[review.rule]]\nwriter = "agent:codex-mcp-client"\nproject = "general"\n')
        rules = load_policy(self.workspace)
        self.assertIsNotNone(
            needs_review(rules, writer=Writer("agent", "codex-mcp-client"), project=None, folder="", write="edit")
        )
        self.assertIsNone(
            needs_review(rules, writer=Writer("agent", "claude-code"), project=None, folder="", write="edit")
        )

    def test_rules_that_cannot_be_used_are_refused(self) -> None:
        cases = [
            '[[review.rule]]\nwriter = "robot"\n',
            '[[review.rule]]\naction = "maybe"\n',
            '[[review.rule]]\nwrites = "delete"\n',
            '[[review.rule]]\nproject = "Not An Id"\n',
            '[[review.rule]]\nfolder = "../x"\n',
            '[[review.rule]]\nproject = "general"\nfolder = "x"\n',
            '[[review.rule]]\ncolour = "blue"\n',
            '[review]\nrules = []\n',
            '[[review.rule]]\nwriter = 3\n',
        ]
        original = (self.root / "knowledge-os.toml").read_text(encoding="utf-8")
        for text in cases:
            with self.subTest(text=text):
                (self.root / "knowledge-os.toml").write_text(original + text, encoding="utf-8")
                with self.assertRaises(ReviewPolicyError):
                    load_policy(self.workspace)


class ProposalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")
        self.workspace = Workspace(self.root)
        create_project(self.workspace, "acme", title="Acme", provenance=PROVENANCE)
        create_folder(self.workspace, "acme", "notes", title="Notes", provenance=PROVENANCE)

    def sha(self, relative: str) -> str:
        return hashlib.sha256((self.root / relative).read_bytes()).hexdigest()

    def test_a_new_page_waits_until_accepted(self) -> None:
        proposal = propose(
            self.workspace, action="create", text=_page("plan"), proposed_by=AGENT, rule="r", project_path="notes/plan.md"
        )
        self.assertFalse((self.root / "projects/acme/notes/plan.md").exists())
        self.assertEqual([item.id for item in list_proposals(self.workspace)[0]], [proposal.id])

        result = accept_proposal(self.workspace, proposal.id, expected_sha256=proposal.sha256)
        self.assertEqual(result.path, "projects/acme/notes/plan.md")
        self.assertEqual(list_proposals(self.workspace), ([], []))
        self.assertFalse((self.root / "proposals").exists())

    def test_a_proposal_that_could_never_be_accepted_is_refused_now(self) -> None:
        with self.assertRaises(Exception):
            propose(self.workspace, action="create", text=_page("acme"), proposed_by=AGENT, rule="r")  # duplicate id
        with self.assertRaises(Exception):
            propose(self.workspace, action="create", text=_page("bad", related=["missing"]), proposed_by=AGENT, rule="r")
        with self.assertRaises(ReviewError):
            propose(self.workspace, action="edit", text=_page("notes"), proposed_by=AGENT, rule="r")
        self.assertFalse((self.root / "proposals").exists())

    def test_an_edit_applies_only_to_the_revision_it_was_made_against(self) -> None:
        relative = "projects/acme/notes/README.md"
        base = self.sha(relative)
        current = (self.root / relative).read_text(encoding="utf-8")
        edited = current.replace("# Notes", "# Notes\n\nMore.")
        first = propose(self.workspace, action="edit", text=edited, proposed_by=AGENT, rule="r", base_sha256=base)
        second = propose(
            self.workspace, action="edit", text=current + "Other.\n", proposed_by=AGENT, rule="r", base_sha256=base
        )

        accept_proposal(self.workspace, first.id)
        self.assertIn("More.", (self.root / relative).read_text(encoding="utf-8"))
        with self.assertRaises(StaleRevisionError):
            accept_proposal(self.workspace, second.id)
        self.assertEqual(len(list_proposals(self.workspace)[0]), 1)

        discard_proposal(self.workspace, second.id)
        self.assertEqual(list_proposals(self.workspace), ([], []))

    def test_a_proposal_edited_since_it_was_shown_is_refused(self) -> None:
        proposal = propose(self.workspace, action="create", text=_page("plan"), proposed_by=AGENT, rule="r")
        with self.assertRaises(StaleRevisionError):
            discard_proposal(self.workspace, proposal.id, expected_sha256="0" * 64)
        self.assertEqual(len(list_proposals(self.workspace)[0]), 1)


class ReviewApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory()
        cls.root = init_workspace(Path(cls._temp.name) / "kb")
        workspace = Workspace(cls.root)
        create_project(workspace, "acme", title="Acme", provenance=PROVENANCE)
        create_project(workspace, "beta", title="Beta", provenance=PROVENANCE)
        with (cls.root / "knowledge-os.toml").open("a", encoding="utf-8") as handle:
            handle.write(RULES)
        cls._server = serve(cls.root, PORT)
        cls.base_url = cls._server.__enter__()
        status, session = _request(cls.base_url, "GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.__exit__(None, None, None)
        cls._temp.cleanup()

    def write(self, method: str, path: str, payload: object) -> tuple[int, dict]:
        return _request(self.base_url, method, path, payload, headers={TOKEN_HEADER: self.token})

    def create(self, record_id: str, project: str, agent: bool = True, **extra: object) -> tuple[int, dict]:
        metadata = {
            "id": record_id,
            "title": record_id.replace("-", " ").capitalize(),
            "type": "project",
            "status": "active",
            "scope": f"project:{project}",
            "provenance": [{"kind": "fixture", "reference": "test"}],
            **extra,
        }
        payload: dict[str, object] = {"metadata": metadata, "body": "Body.\n"}
        if agent:
            payload["agent"] = {"client": "claude-code", "place": "repo"}
        return self.write("POST", "/api/records", payload)

    def test_agent_note_waits_in_decide_and_accepting_writes_it(self) -> None:
        status, result = self.create("held-note", "acme")
        self.assertEqual(status, 202, result)
        self.assertEqual(result["status"], "proposed")
        self.assertIn("agents in project acme", result["proposal"]["rule"])
        self.assertFalse((self.root / "projects/acme/held-note.md").exists())

        status, listing = _request(self.base_url, "GET", "/api/changes")
        row = next(item for item in listing["items"] if item["record"]["id"] == "held-note")
        self.assertEqual(row["proposed_by"]["label"], "Proposed by Claude Code in repo")
        status, nav = _request(self.base_url, "GET", "/api/nav")
        self.assertGreaterEqual(nav["decide"]["count"], 1)

        status, accepted = self.write("POST", f"/api/changes/{row['id']}/accept", {"expected_sha256": row["content_sha256"]})
        self.assertEqual(status, 200, accepted)
        self.assertEqual(accepted["path"], "projects/acme/held-note.md")
        self.assertTrue((self.root / "projects/acme/held-note.md").exists())
        status, _missing = _request(self.base_url, "GET", f"/api/changes/{row['id']}")
        self.assertEqual(status, 404)

    def test_the_same_write_elsewhere_or_by_a_person_lands_directly(self) -> None:
        self.assertEqual(self.create("beta-note", "beta")[0], 201)
        self.assertEqual(self.create("person-note", "acme", agent=False)[0], 201)
        status, result = self.create("draft-note", "acme")
        self.assertEqual(status, 202)  # no drafts/ folder in the path
        status, created = self.write(
            "POST", "/api/projects/acme/folders", {"path": "drafts", "title": "Drafts"}
        )
        self.assertEqual(status, 201, created)
        status, result = self.write(
            "POST",
            "/api/records",
            {
                "metadata": {
                    "id": "in-drafts",
                    "title": "In drafts",
                    "type": "project",
                    "status": "active",
                    "scope": "project:acme",
                    "provenance": [{"kind": "fixture", "reference": "test"}],
                },
                "body": "Body.\n",
                "project_path": "drafts/in-drafts.md",
                "agent": {"client": "claude-code"},
            },
        )
        self.assertEqual(status, 201, result)

    def test_decisions_are_never_held_back(self) -> None:
        status, result = self.create("agent-decision", "acme", record_kind="decision", status="draft")
        self.assertEqual(status, 201, result)

    def test_agent_edit_shows_a_diff_and_discarding_drops_it(self) -> None:
        self.assertEqual(self.create("edited-page", "acme", agent=False)[0], 201)
        status, page = _request(self.base_url, "GET", "/api/records/edited-page")
        status, result = self.write(
            "PATCH",
            "/api/records/edited-page",
            {
                "expected_sha256": page["editing"]["content_sha256"],
                "metadata": {"tags": ["ops"]},
                "body": "Body.\n\nAdded.\n",
                "agent": {"client": "codex-mcp-client"},
            },
        )
        self.assertEqual(status, 202, result)
        change_id = result["proposal"]["id"]
        status, detail = _request(self.base_url, "GET", f"/api/changes/{change_id}")
        self.assertEqual(status, 200, detail)
        self.assertEqual(detail["metadata_changes"], [{"field": "tags", "before": [], "after": ["ops"]}])
        self.assertIn("added", [block["kind"] for block in detail["blocks"]])
        self.assertFalse(detail["stale"])

        status, discarded = self.write("POST", f"/api/changes/{change_id}/discard", {})
        self.assertEqual(status, 200, discarded)
        self.assertNotIn("Added.", (self.root / "projects/acme/edited-page.md").read_text(encoding="utf-8"))

    def test_review_check_answers_without_writing(self) -> None:
        status, answer = _request(self.base_url, "GET", "/api/review/check?writer=referat&project=beta&folder=meetings")
        self.assertEqual((status, answer["review"]), (200, True))
        status, answer = _request(self.base_url, "GET", "/api/review/check?writer=person&project=acme")
        self.assertEqual((status, answer["review"]), (200, False))


@unittest.skipIf(GIT is None, "git is not installed")
class McpReviewTests(IsolatedTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.root = init_workspace(self.base / "kb")
        workspace = Workspace(self.root)
        create_project(workspace, "acme", title="Acme", provenance=PROVENANCE)
        with (self.root / "knowledge-os.toml").open("a", encoding="utf-8") as handle:
            handle.write(RULES)
        git(self.root, "init", "--quiet", "-b", "main")
        git(self.root, "config", "user.name", "Alice")
        git(self.root, "config", "user.email", "alice@example.invalid")
        git(self.root, "add", "-A")
        git(self.root, "commit", "--quiet", "-m", "Initial knowledge base")
        self.server = serve(self.root, MCP_PORT)
        base_url = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        write_runtime_file(self.runtime_path, port=MCP_PORT, token=_session_token(base_url), root=self.root)

    def test_write_note_says_the_change_waits_for_review(self) -> None:
        result = call_tool("write_note", {"title": "Agent plan", "content": "Plan.\n", "project": "acme"}, CALLER)
        self.assertFalse(result.is_error, result.data)
        self.assertEqual(result.data["action"], "waiting_for_review")
        self.assertFalse(result.data["written"])
        self.assertIn("Decide", result.data["next_step"])
        self.assertFalse((self.root / "projects/acme/agent-plan.md").exists())
        self.assertEqual(
            git(self.root, "log", "-1", "--format=%s").strip(), "Claude Code: Propose Agent plan"
        )
        self.assertIn("proposals/", git(self.root, "show", "--stat", "--format=", "HEAD"))


if __name__ == "__main__":
    unittest.main()
