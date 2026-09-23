"""End-to-end tests for the Decide inbox, ``GET /api/decisions/proposed``,
and the sidebar count in ``GET /api/nav`` (issue #53).

One real ``kos-read`` server serves one temporary workspace with proposed
decisions in two projects and one that applies everywhere: a plain
proposal, a replacement for a decision in force, one imported from a
Referat meeting, one written by an agent, one from an unknown source, and
one from a request. Tests that accept or withdraw create their own
decisions so the fixed rows stay put.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

from reader_support import create_workspace, serve, write_record
from test_api_write import TOKEN_HEADER, _request

from knowledge_os.index import rebuild_indexes
from knowledge_os.workspace import Workspace

PORT = 8847
EMPTY_PORT = 8848

#: Contract words that must not reach the reading path (issue #54).
CONTRACT_WORDS = re.compile(
    r"\b(records?|provenance|supersedes?|superseded|supersession|draft|active|archived|lineage)\b", re.IGNORECASE
)


def _overview(root: Path, project_id: str, title: str) -> None:
    write_record(
        root,
        f"projects/{project_id}/README.md",
        {
            "id": project_id,
            "title": f"{title} project overview",
            "type": "project",
            "status": "active",
            "scope": f"project:{project_id}",
            "created": "2026-09-01",
            "updated": "2026-09-01",
            "provenance": [{"kind": "project-definition", "reference": f"test:{project_id}"}],
        },
        f"{title} overview.\n",
    )


def _decision(
    root: Path,
    project_id: str | None,
    record_id: str,
    title: str,
    provenance: list[dict[str, str]],
    *,
    status: str = "draft",
    created: str = "2026-09-10",
    body: str = "## Decision\n\nWe do the thing.\n",
    **extra: object,
) -> None:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": title,
        "type": "project" if project_id else "knowledge",
        "record_kind": "decision",
        "status": status,
        "scope": f"project:{project_id}" if project_id else "general",
        "created": created,
        "updated": created,
        "provenance": provenance,
        **extra,
    }
    folder = f"projects/{project_id}/decisions" if project_id else "knowledge"
    write_record(root, f"{folder}/{record_id}.md", metadata, body)


def _build(root: Path) -> None:
    create_workspace(root)
    _overview(root, "alpha", "Alpha")
    _overview(root, "beta", "Beta")
    _decision(
        root,
        "alpha",
        "alpha-in-force",
        "Alpha rule in force",
        [
            {"kind": "user-approved-conversation", "reference": "conversation:2026-09-01:alpha", "captured": "2026-09-01T09:00:00Z"},
            {"kind": "decision-acceptance", "reference": "conversation:2026-09-01:accepted", "captured": "2026-09-01T10:00:00Z"},
        ],
        status="active",
        created="2026-09-01",
    )
    _decision(
        root,
        "alpha",
        "alpha-plain",
        "Alpha plain proposal",
        [{"kind": "interface-authored", "reference": "interface:2026-09-20T10:00:00Z:create", "captured": "2026-09-20T10:00:00Z"}],
        created="2026-09-20",
        body="# Alpha plain proposal\n\n## Decision\n\nUse **short** names for [folders](../README.md).\n\nSecond paragraph.\n",
    )
    _decision(
        root,
        "alpha",
        "alpha-replacement",
        "Alpha replacement",
        [{"kind": "user-approved-conversation", "reference": "conversation:2026-09-21:alpha-replacement", "captured": "2026-09-21T10:00:00Z"}],
        created="2026-09-21",
        supersedes=["alpha-in-force"],
    )
    _decision(
        root,
        "beta",
        "beta-referat",
        "Beta meeting outcome",
        [{"kind": "referat-meeting", "reference": "referat:20260918093000-ab12cd", "captured": "2026-09-22T08:00:00Z"}],
        created="2026-09-22",
    )
    _decision(
        root,
        "beta",
        "beta-agent",
        "Beta agent proposal",
        [{"kind": "agent-authored", "reference": "agent:codex:some-repo", "captured": "2026-09-23T08:00:00Z"}],
        created="2026-09-23",
    )
    _decision(
        root,
        "beta",
        "beta-unknown",
        "Beta unknown source",
        [{"kind": "mystery-kind", "reference": "somewhere/else.md", "captured": "2026-09-19T08:00:00Z"}],
        created="2026-09-19",
    )
    _decision(
        root,
        None,
        "general-request",
        "General request",
        [{"kind": "user-request", "reference": "conversation:2026-09-17:general"}],
        created="2026-09-17",
    )
    rebuild_indexes(Workspace(root))


def _visible_strings(value: object, *, skip: frozenset[str]) -> list[str]:
    """Every string value in a payload, except under keys that hold data
    rather than words (ids, hashes, raw kinds, timestamps)."""

    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key not in skip:
                found.extend(_visible_strings(item, skip=skip))
    elif isinstance(value, list):
        for item in value:
            found.extend(_visible_strings(item, skip=skip))
    elif isinstance(value, str):
        found.append(value)
    return found


_DATA_KEYS = frozenset({"id", "kind", "source", "content_sha256", "proposed_at", "project", "status", "tone", "key"})


class DecideApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        directory = cls._stack.enter_context(tempfile.TemporaryDirectory())
        cls.root = Path(directory)
        _build(cls.root)
        cls.base_url = cls._stack.enter_context(serve(cls.root, PORT))
        status, session = _request(cls.base_url, "GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def get(self, path: str) -> dict:
        status, data = _request(self.base_url, "GET", path)
        self.assertEqual(status, 200, data)
        return data

    def post(self, path: str, payload: dict) -> tuple[int, dict]:
        return _request(self.base_url, "POST", path, payload, headers={TOKEN_HEADER: self.token})

    def fixed_rows(self, data: dict) -> dict[str, dict]:
        return {row["id"]: row for row in data["items"] if not row["id"].startswith("temp-")}

    def test_lists_every_proposal_newest_first_with_project_counts(self) -> None:
        data = self.get("/api/decisions/proposed")

        ids = [row["id"] for row in data["items"] if not row["id"].startswith("temp-")]
        self.assertEqual(
            ids,
            ["beta-agent", "beta-referat", "alpha-replacement", "alpha-plain", "beta-unknown", "general-request"],
        )
        self.assertNotIn("alpha-in-force", ids)
        self.assertEqual(data["count"], len(data["items"]))
        projects = {entry["id"]: entry for entry in data["projects"]}
        self.assertEqual(projects["alpha"]["title"], "Alpha")
        self.assertEqual(projects["general"]["title"], "Applies everywhere")
        self.assertEqual(sum(entry["count"] for entry in data["projects"]), data["count"])
        self.assertEqual(data["title"], "Decide")
        self.assertIn("How decisions work", data["language"]["guide"]["title"])

    def test_proposer_is_derived_from_provenance_for_each_kind(self) -> None:
        rows = self.fixed_rows(self.get("/api/decisions/proposed"))

        expected = {
            "alpha-plain": ("you", "Proposed by you in this app"),
            "alpha-replacement": ("conversation", "Proposed in a conversation you approved"),
            "beta-referat": ("meeting", "Proposed in a Referat meeting on 18 September 2026"),
            "beta-agent": ("agent", "Proposed by Codex in some-repo"),
            "beta-unknown": ("other", "Proposed from a source this app does not describe yet"),
            "general-request": ("you", "Proposed at your request"),
        }
        for record_id, (source, label) in expected.items():
            with self.subTest(record_id=record_id):
                self.assertEqual(rows[record_id]["proposed_by"]["source"], source)
                self.assertEqual(rows[record_id]["proposed_by"]["label"], label)
        self.assertEqual(rows["beta-unknown"]["proposed_by"]["kind"], "mystery-kind")
        self.assertEqual(rows["beta-referat"]["proposed_at"], "2026-09-22T08:00:00Z")
        self.assertEqual(rows["beta-referat"]["proposed_exact"], "22 September 2026")
        # No captured timestamp: the decision's own created date stands in.
        self.assertEqual(rows["general-request"]["proposed_at"], "2026-09-17")

    def test_row_says_what_accepting_changes_and_names_the_replaced_decision(self) -> None:
        rows = self.fixed_rows(self.get("/api/decisions/proposed"))

        plain = rows["alpha-plain"]
        self.assertIsNone(plain["replaces"])
        self.assertEqual(plain["effect"], "Accepting puts it in force for Alpha.")
        self.assertEqual(plain["excerpt"], "Use short names for folders. Second paragraph.")
        self.assertTrue(plain["actions"]["accept"])
        self.assertEqual(set(plain["actions"]["dialogs"]), {"accept", "withdraw"})
        self.assertEqual(plain["project"], {"id": "alpha", "title": "Alpha"})

        replacement = rows["alpha-replacement"]
        self.assertEqual(replacement["replaces"]["id"], "alpha-in-force")
        self.assertEqual(replacement["replaces"]["title"], "Alpha rule in force")
        self.assertEqual(replacement["effect"], "Accepting puts it in force and replaces “Alpha rule in force”.")
        self.assertFalse(replacement["actions"]["accept"])
        target = self.root / "projects/alpha/decisions/alpha-in-force.md"
        self.assertEqual(
            replacement["actions"]["supersede"]["content_sha256"], hashlib.sha256(target.read_bytes()).hexdigest()
        )
        self.assertEqual(set(replacement["actions"]["dialogs"]), {"supersede", "withdraw"})
        source = self.root / "projects/alpha/decisions/alpha-replacement.md"
        self.assertEqual(replacement["content_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_project_filter(self) -> None:
        beta = self.get("/api/decisions/proposed?project=beta")
        self.assertEqual({row["project"]["id"] for row in beta["items"]}, {"beta"})
        self.assertEqual(beta["project"], "beta")

        general = self.get("/api/decisions/proposed?project=general")
        self.assertEqual([row["id"] for row in general["items"]], ["general-request"])

        unknown = self.get("/api/decisions/proposed?project=no-such-project")
        self.assertEqual(unknown["items"], [])
        self.assertGreater(unknown["count"], 0)
        self.assertEqual(unknown["empty"]["body"], "No proposed decision is waiting in this project.")

    def test_accept_and_withdraw_update_the_list_and_the_sidebar_count(self) -> None:
        for record_id in ("temp-accept", "temp-withdraw"):
            _decision(
                self.root,
                "alpha",
                record_id,
                record_id.replace("-", " ").capitalize(),
                [{"kind": "interface-authored", "reference": f"interface:2026-09-23T12:00:00Z:{record_id}", "captured": "2026-09-23T12:00:00Z"}],
                created="2026-09-23",
            )
        before = self.get("/api/decisions/proposed")
        self.assertEqual(self.get("/api/nav")["decide"], {"label": "Decide", "count": before["count"]})
        rows = {row["id"]: row for row in before["items"]}

        status, result = self.post("/api/records/temp-accept/accept", {"expected_sha256": rows["temp-accept"]["content_sha256"]})
        self.assertEqual(status, 200, result)
        self.assertEqual(self.get("/api/nav")["decide"]["count"], before["count"] - 1)

        status, result = self.post(
            "/api/records/temp-withdraw/withdraw",
            {"expected_sha256": rows["temp-withdraw"]["content_sha256"], "reason": "Not needed."},
        )
        self.assertEqual(status, 200, result)
        after = self.get("/api/decisions/proposed")
        self.assertEqual(after["count"], before["count"] - 2)
        self.assertNotIn("temp-accept", {row["id"] for row in after["items"]})
        self.assertNotIn("temp-withdraw", {row["id"] for row in after["items"]})
        self.assertEqual(self.get("/api/nav")["decide"]["count"], after["count"])

        withdrawn = self.get("/api/records/temp-withdraw")
        self.assertEqual(withdrawn["properties"]["status"]["pill"]["label"], "Withdrawn")
        self.assertTrue(withdrawn["properties"]["status"]["value"].startswith("Withdrawn on "))

    def test_inbox_words_carry_no_contract_vocabulary(self) -> None:
        data = self.get("/api/decisions/proposed")
        for text in _visible_strings(data, skip=_DATA_KEYS):
            with self.subTest(text=text):
                self.assertIsNone(CONTRACT_WORDS.search(text))

    def test_decision_page_dialogs_and_guide_carry_no_contract_vocabulary(self) -> None:
        for record_id in ("alpha-plain", "alpha-replacement", "alpha-in-force"):
            data = self.get(f"/api/records/{record_id}")
            payload = {
                "status_row": data["properties"]["status"],
                "lineage": [callout["text"] for callout in data["lineage"]],
                "actions": data["editing"]["decision_actions"],
                "language": data["decision_language"],
            }
            for text in _visible_strings(payload, skip=_DATA_KEYS):
                with self.subTest(record_id=record_id, text=text):
                    self.assertIsNone(CONTRACT_WORDS.search(text))

    def test_decision_page_offers_the_guide_and_a_dialog_sentence_per_action(self) -> None:
        data = self.get("/api/records/alpha-replacement")
        self.assertEqual(data["lineage"][0]["text"], "Would replace Alpha rule in force once accepted.")
        dialogs = data["editing"]["decision_actions"]["dialogs"]
        self.assertIn("no undo button", dialogs["supersede"]["body"])
        self.assertIn("cannot be undone", dialogs["withdraw"]["body"])
        self.assertEqual(
            dialogs["supersede"]["changes"][1],
            {"subject": "Alpha rule in force", "from": "In force", "to": "Replaced by “Alpha replacement”"},
        )
        states = [state["label"] for state in data["decision_language"]["guide"]["states"]]
        self.assertEqual(states, ["Proposed", "In force", "Replaced", "Withdrawn"])
        self.assertIsNone(self.get("/api/records/alpha")["decision_language"])


class EmptyInboxTests(unittest.TestCase):
    def test_empty_state_says_nothing_is_waiting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            _overview(root, "alpha", "Alpha")
            rebuild_indexes(Workspace(root))
            with serve(root, EMPTY_PORT) as base_url:
                status, data = _request(base_url, "GET", "/api/decisions/proposed")
                _nav_status, nav = _request(base_url, "GET", "/api/nav")
        self.assertEqual(status, 200)
        self.assertEqual(data["items"], [])
        self.assertEqual(data["count"], 0)
        self.assertIsNone(data["count_label"])
        self.assertEqual(data["empty"]["title"], "Nothing is waiting on you")
        self.assertEqual(nav["decide"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
