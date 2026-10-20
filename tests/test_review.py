"""Configurable review (issue #86): the rules in ``knowledge-os.toml``,
proposed changes in ``proposals/``, the local API that holds writes back and
applies or drops them, and what an MCP agent is told."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit

from test_agent_mcp import CALLER, GIT, IsolatedTestCase, _session_token, git, write_runtime_file
from test_api_write import TOKEN_HEADER, _request

from knowledge_os.agent_access.tools import call_tool
from knowledge_os.cli import main as cli_main
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
    agent_writer,
    needs_review,
    propose,
    write_place,
)
from knowledge_os.structure import create_folder, create_project
from knowledge_os.workspace import Workspace
from reader_support import serve

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

    def test_memory_pages_are_general_and_folders_come_from_the_project_path(self) -> None:
        self.assertEqual(write_place({"type": "memory", "scope": "project:acme"}, "notes/x.md"), (None, ""))
        self.assertEqual(write_place({"type": "knowledge", "scope": "general"}, None), (None, ""))
        self.assertEqual(write_place({"type": "project", "scope": "project:acme"}, "a/b/x.md"), ("acme", "a/b"))
        self.assertEqual(write_place({"type": "project", "scope": "project:acme"}, None), ("acme", ""))

    def test_the_command_line_writer_is_an_agent(self) -> None:
        self.assertEqual(agent_writer("agent"), Writer("agent"))
        self.assertEqual(agent_writer("agent:codex"), Writer("agent", "codex"))
        for value in ("person", "agent:", "agent:Not ok!", "referat"):
            with self.subTest(value=value), self.assertRaises(ReviewError):
                agent_writer(value)

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
        cls._server = serve(cls.root)
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

    def test_agents_cannot_edit_a_decision(self) -> None:
        status, created = self.create("in-force", "beta", agent=False, record_kind="decision", status="draft")
        self.assertEqual(status, 201, created)
        status, accepted = self.write(
            "POST", "/api/records/in-force/accept", {"expected_sha256": created["content_sha256"]}
        )
        self.assertEqual(status, 200, accepted)
        before = (self.root / accepted["path"]).read_bytes()
        status, result = self.write(
            "PATCH",
            "/api/records/in-force",
            {
                "expected_sha256": accepted["content_sha256"],
                "body": "Body.\n\nChanged.\n",
                "confirm_non_material": True,
                "agent": {"client": "claude-code"},
            },
        )
        self.assertEqual(status, 403, result)
        self.assertIn("agents cannot edit decisions", result["detail"])
        self.assertEqual((self.root / accepted["path"]).read_bytes(), before)

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
        self.server = serve(self.root)
        base_url = self.server.__enter__()
        self.addCleanup(self.server.__exit__, None, None, None)
        port = urlsplit(base_url).port
        write_runtime_file(self.runtime_path, port=port, token=_session_token(base_url), root=self.root)

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

    def test_memory_follows_the_rules_for_general_knowledge(self) -> None:
        arguments = {"title": "Prefers short replies", "content": "Keep replies short.\n", "destination": "memory"}
        result = call_tool("write_note", arguments, CALLER)
        self.assertFalse(result.is_error, result.data)
        self.assertEqual((result.data["action"], result.data["path"]), ("created", "memory/prefers-short-replies.md"))

        with (self.root / "knowledge-os.toml").open("a", encoding="utf-8") as handle:
            handle.write('\n[[review.rule]]\nwriter = "agent"\nproject = "general"\n')
        result = call_tool("write_note", {**arguments, "title": "Prefers tables", "project": "acme"}, CALLER)
        self.assertFalse(result.is_error, result.data)
        self.assertEqual(result.data["action"], "waiting_for_review")
        self.assertFalse((self.root / "memory/prefers-tables.md").exists())
        (proposal,) = list_proposals(Workspace(self.root))[0]
        self.assertEqual((proposal.record_id, proposal.metadata["type"]), ("prefers-tables", "memory"))

        refused = call_tool("write_note", {**arguments, "title": "In a folder", "project": "acme", "folder": "x"}, CALLER)
        self.assertTrue(refused.is_error)


class CliReviewTests(unittest.TestCase):
    """``--writer agent`` on ``kos capture`` and ``kos update``, and ``kos lint``."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = init_workspace(Path(self._temp.name) / "kb")
        self.workspace = Workspace(self.root)
        create_project(self.workspace, "acme", title="Acme", provenance=PROVENANCE)
        self.config = (self.root / "knowledge-os.toml").read_text(encoding="utf-8")
        self.candidates = Path(self._temp.name) / "candidates"
        self.candidates.mkdir()

    def rules(self, text: str) -> None:
        (self.root / "knowledge-os.toml").write_text(self.config + text, encoding="utf-8")

    def kos(self, *arguments: str) -> tuple[int, str, str]:
        stdout, stderr = StringIO(), StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli_main([*arguments, "--root", str(self.root)])
        return code, stdout.getvalue(), stderr.getvalue()

    def candidate(self, record_id: str, text: str) -> Path:
        path = self.candidates / f"{record_id}.md"
        path.write_text(text, encoding="utf-8")
        return path

    def memory(self, record_id: str) -> str:
        return render_document(
            {
                "id": record_id,
                "title": "Prefers short replies",
                "type": "memory",
                "status": "draft",
                "scope": "general",
                "created": "2026-10-21",
                "updated": "2026-10-21",
                "provenance": PROVENANCE,
            },
            "Keep replies short.\n",
        ).decode("utf-8")

    def test_an_agent_capture_a_rule_holds_back_becomes_a_proposal(self) -> None:
        self.rules('\n[[review.rule]]\nwriter = "agent"\nproject = "general"\n')
        path = self.candidate("short-replies", self.memory("short-replies"))

        code, out, err = self.kos("capture", str(path), "--writer", "agent", "--json")
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        self.assertEqual((result["action"], result["id"]), ("waiting_for_review", "short-replies"))
        self.assertIn("agents in general knowledge", result["rule"])
        self.assertFalse((self.root / "memory/short-replies.md").exists())
        (proposal,) = list_proposals(self.workspace)[0]
        self.assertEqual(proposal.id, result["proposal"])
        self.assertEqual(proposal.proposed_by["reference"], "agent")

        code, out, err = self.kos("capture", str(path), "--json")  # a person in the terminal
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["path"], "memory/short-replies.md")

    def test_an_agent_update_follows_its_clients_rule(self) -> None:
        self.rules('\n[[review.rule]]\nwriter = "agent:codex"\nproject = "acme"\nwrites = "edit"\n')
        page = self.root / "projects/acme/README.md"
        base = hashlib.sha256(page.read_bytes()).hexdigest()
        edited = self.candidate("acme", page.read_text(encoding="utf-8") + "\nMore.\n")

        code, out, err = self.kos(
            "update", str(edited), "--expected-sha256", base, "--writer", "agent:claude-code", "--json"
        )
        self.assertEqual(code, 0, err)  # another client: no rule, written directly
        self.assertNotIn("action", json.loads(out))
        base = hashlib.sha256(page.read_bytes()).hexdigest()
        edited.write_text(page.read_text(encoding="utf-8") + "\nEven more.\n", encoding="utf-8")

        code, out, err = self.kos("update", str(edited), "--expected-sha256", base, "--writer", "agent:codex")
        self.assertEqual(code, 0, err)
        self.assertIn("Waiting for review", out)
        self.assertNotIn("Even more.", page.read_text(encoding="utf-8"))
        (proposal,) = list_proposals(self.workspace)[0]
        self.assertEqual((proposal.action, proposal.base_sha256), ("edit", base))
        self.assertEqual(proposal.proposed_by["reference"], "agent:codex")

    def test_an_agent_cannot_update_a_decision(self) -> None:
        decision = render_document(
            {
                "id": "use-postgres",
                "title": "Use Postgres",
                "type": "project",
                "record_kind": "decision",
                "status": "draft",
                "scope": "project:acme",
                "created": "2026-10-21",
                "updated": "2026-10-21",
                "provenance": PROVENANCE,
            },
            "We use Postgres.\n",
        ).decode("utf-8")
        code, out, err = self.kos("capture", str(self.candidate("use-postgres", decision)), "--writer", "agent", "--json")
        self.assertEqual(code, 0, err)
        page = self.root / json.loads(out)["path"]
        base = hashlib.sha256(page.read_bytes()).hexdigest()
        edited = self.candidate("use-postgres", page.read_text(encoding="utf-8") + "\nMore.\n")

        code, _out, err = self.kos("update", str(edited), "--expected-sha256", base, "--writer", "agent")
        self.assertEqual(code, 1)
        self.assertIn("agents cannot edit decisions", err)
        self.assertEqual(hashlib.sha256(page.read_bytes()).hexdigest(), base)

    def test_a_writer_that_is_not_an_agent_is_refused(self) -> None:
        path = self.candidate("short-replies", self.memory("short-replies"))
        code, _out, err = self.kos("capture", str(path), "--writer", "person")
        self.assertEqual(code, 1)
        self.assertIn("--writer must be agent", err)
        self.assertFalse((self.root / "memory/short-replies.md").exists())

    def test_lint_reports_review_rules_that_cannot_be_used(self) -> None:
        code, out, err = self.kos("lint")
        self.assertEqual(code, 0, err)
        self.rules('\n[[review.rule]]\nwriter = "robot"\n')
        code, out, err = self.kos("lint")
        self.assertEqual(code, 1, out)
        self.assertIn("ERROR knowledge-os.toml: review rule 1: writer must be agent", err)
        self.assertIn("Lint failed: 1 issue(s)", err)


if __name__ == "__main__":
    unittest.main()
