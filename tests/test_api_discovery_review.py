"""Tests for ``POST /api/discoveries/{id}/retain``, ``/reject``, and
``/promote``: a person reviewing an observation in the app.

Each decision is made twice on identical copies of one fixture workspace,
once through ``kos discovery ... --json`` and once through the API, and the
resulting files and answers are compared: the app calls the same core
functions, so the Markdown must come out byte for byte the same. The API
copy is its own Git repository, so its commit is checked too; the CLI does
not commit.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
from pathlib import Path

from reader_support import create_workspace, write_record
from test_gitsync import GitTestCase, configure, git

from knowledge_os.cli import main as kos_main
from knowledge_os.index import rebuild_indexes
from knowledge_os.model import content_sha256
from knowledge_os.workspace import Workspace

TOKEN_HEADER = "X-KOS-Write-Token"
ORIGIN = "http://127.0.0.1"


def _fixture(root: Path) -> None:
    create_workspace(root)
    write_record(
        root,
        "projects/demo/README.md",
        {
            "id": "demo",
            "title": "Demo",
            "type": "project",
            "status": "active",
            "scope": "project:demo",
            "created": "2026-09-01",
            "updated": "2026-09-01",
            "provenance": [{"kind": "project-definition", "reference": "test:demo"}],
        },
        "Demo overview.\n",
    )
    write_record(
        root,
        "knowledge/deploy-freeze.md",
        {
            "id": "deploy-freeze",
            "title": "Deploy freeze on Fridays",
            "type": "knowledge",
            "status": "active",
            "scope": "general",
            "created": "2026-09-01",
            "updated": "2026-09-01",
            "provenance": [{"kind": "fixture", "reference": "test"}],
        },
        "Nobody deploys on Fridays.\n",
    )
    for record_id, title, body, scope in (
        ("friday-deploys", "Deploys fail on Fridays", "Friday deploys failed twice.\n", "project:demo"),
        ("slow-tests", "Tests are slow", "The suite takes ten minutes.\n", "project:demo"),
        ("general-note", "Quarterly zebra audit", "Zebras get audited quarterly.\n", "general"),
    ):
        write_record(
            root,
            f"discoveries/{record_id}.md",
            {
                "id": record_id,
                "title": title,
                "type": "discovery",
                "status": "proposed",
                "scope": scope,
                "created": "2026-09-10",
                "updated": "2026-09-10",
                "provenance": [{"kind": "agent-run", "reference": "run-1"}],
                "evidence": [{"kind": "record", "reference": "demo"}],
            },
            body,
        )
    rebuild_indexes(Workspace.discover(root))


@contextlib.contextmanager
def _client(root: Path):  # type: ignore[no-untyped-def]
    from starlette.testclient import TestClient

    from knowledge_os.reader.app import create_app

    app = create_app(Workspace.discover(root), refresh_index=False)
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        yield client


class DiscoveryReviewApiTests(GitTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cli_root = self.base / "cli"
        self.api_root = self.base / "api"
        self.cli_root.mkdir()
        _fixture(self.cli_root)
        shutil.copytree(self.cli_root, self.api_root)
        git(self.api_root, "init", "-q")
        configure(self.api_root, "Alice")
        git(self.api_root, "add", "--all")
        git(self.api_root, "commit", "-q", "-m", "Fixture")

    def kos_json(self, *arguments: str) -> dict:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kos_main([*arguments, "--root", str(self.cli_root), "--json"])
        self.assertEqual(code, 0, err.getvalue())
        return json.loads(out.getvalue())

    def post(self, path: str, payload: dict, *, token: bool = True, headers: dict | None = None):  # type: ignore[no-untyped-def]
        with _client(self.api_root) as client:
            sent = {"Origin": ORIGIN, **(headers or {})}
            if token:
                sent[TOKEN_HEADER] = client.get("/api/session").json()["write_token"]
            return client.post(path, json=payload, headers=sent)

    def sha(self, record_id: str) -> str:
        return content_sha256(self.api_root / "discoveries" / f"{record_id}.md")

    def assert_same_file(self, rel_path: str) -> None:
        cli = (self.cli_root / rel_path).read_bytes()
        api = (self.api_root / rel_path).read_bytes()
        self.assertEqual(api, cli, rel_path)

    def assert_answer_matches(self, api: dict, cli: dict) -> dict:
        committed = api.pop("commit")
        self.assertIsNone(api.pop("index_error"))
        self.assertEqual(api, cli)
        self.assertTrue(committed["committed"], committed)
        return committed

    def test_retain_matches_the_cli(self) -> None:
        cli = self.kos_json("discovery", "retain", "slow-tests", "--reason", "seen it")
        response = self.post(
            "/api/discoveries/slow-tests/retain", {"expected_sha256": self.sha("slow-tests"), "reason": "seen it"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        commit = self.assert_answer_matches(response.json(), cli)
        self.assertEqual(commit["message"], "Retain observation Tests are slow")
        self.assert_same_file("discoveries/slow-tests.md")
        self.assertEqual(git(self.api_root, "show", "--name-only", "--format=", "HEAD"), "discoveries/slow-tests.md")
        self.assertEqual(git(self.api_root, "status", "--porcelain", "--", "discoveries"), "")

    def test_reject_matches_the_cli_and_needs_a_reason(self) -> None:
        refused = self.post("/api/discoveries/slow-tests/reject", {"expected_sha256": self.sha("slow-tests")})
        self.assertEqual(refused.status_code, 400, refused.text)
        blank = self.post(
            "/api/discoveries/slow-tests/reject", {"expected_sha256": self.sha("slow-tests"), "reason": "  "}
        )
        self.assertEqual(blank.status_code, 422, blank.text)
        self.assertIn("--reason must not be empty", blank.json()["detail"])

        cli = self.kos_json("discovery", "reject", "slow-tests", "--reason", "not true")
        response = self.post(
            "/api/discoveries/slow-tests/reject", {"expected_sha256": self.sha("slow-tests"), "reason": "not true"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        commit = self.assert_answer_matches(response.json(), cli)
        self.assertEqual(commit["message"], "Reject observation Tests are slow")
        self.assert_same_file("discoveries/slow-tests.md")

    def test_promote_matches_the_cli_with_both_flags(self) -> None:
        arguments = ["--target-id", "friday-rule", "--title", "Friday rule", "--scope", "general"]
        cli = self.kos_json(
            "discovery", "promote", "friday-deploys", *arguments, "--acknowledge-related", "--allow-scope-broadening"
        )
        payload = {
            "expected_sha256": self.sha("friday-deploys"),
            "target_id": "friday-rule",
            "title": "Friday rule",
            "scope": "general",
        }
        # Each flag the CLI needs is needed here too, and nothing is written without it.
        before = self.sha("friday-deploys")
        missing_ack = self.post("/api/discoveries/friday-deploys/promote", {**payload, "allow_scope_broadening": True})
        self.assertEqual(missing_ack.status_code, 422, missing_ack.text)
        self.assertIn("--acknowledge-related", missing_ack.json()["detail"])
        missing_broaden = self.post("/api/discoveries/friday-deploys/promote", {**payload, "acknowledge_related": True})
        self.assertEqual(missing_broaden.status_code, 422, missing_broaden.text)
        self.assertIn("--allow-scope-broadening", missing_broaden.json()["detail"])
        self.assertEqual(self.sha("friday-deploys"), before)
        self.assertFalse((self.api_root / "knowledge" / "friday-rule.md").exists())

        response = self.post(
            "/api/discoveries/friday-deploys/promote",
            {**payload, "acknowledge_related": True, "allow_scope_broadening": True},
        )
        self.assertEqual(response.status_code, 200, response.text)
        commit = self.assert_answer_matches(response.json(), cli)
        self.assertEqual(commit["message"], "Promote observation Deploys fail on Fridays to Friday rule")
        self.assert_same_file("discoveries/friday-deploys.md")
        self.assert_same_file("knowledge/friday-rule.md")
        self.assertEqual(
            sorted(git(self.api_root, "show", "--name-only", "--format=", "HEAD").splitlines()),
            ["discoveries/friday-deploys.md", "knowledge/friday-rule.md"],
        )

    def test_core_refusals_are_the_cli_rules(self) -> None:
        general = self.post("/api/discoveries/general-note/retain", {"expected_sha256": self.sha("general-note")})
        self.assertEqual(general.status_code, 422, general.text)
        self.assertIn("retained discoveries require project scope", general.json()["detail"])
        missing = self.post("/api/discoveries/nope/retain", {"expected_sha256": "0" * 64})
        self.assertEqual(missing.status_code, 404, missing.text)
        not_discovery = self.post("/api/discoveries/demo/retain", {"expected_sha256": "0" * 64})
        self.assertEqual(not_discovery.status_code, 404, not_discovery.text)

    def test_a_changed_observation_is_not_reviewed(self) -> None:
        stale = "0" * 64
        response = self.post("/api/discoveries/slow-tests/retain", {"expected_sha256": stale})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["current_sha256"], self.sha("slow-tests"))
        self.assertIn("status: proposed", (self.api_root / "discoveries" / "slow-tests.md").read_text("utf-8"))

    def test_agent_labelled_requests_are_refused(self) -> None:
        before = self.sha("slow-tests")
        agent = {"client": "claude-code", "place": "repo"}
        for action, extra in (
            ("retain", {}),
            ("reject", {"reason": "no"}),
            ("promote", {"target_id": "x-page", "title": "X", "scope": "project:demo", "acknowledge_related": True}),
        ):
            response = self.post(
                f"/api/discoveries/slow-tests/{action}", {"expected_sha256": before, "agent": agent, **extra}
            )
            self.assertEqual(response.status_code, 403, (action, response.text))
            self.assertIn("Only a person", response.json()["detail"])
        self.assertEqual(self.sha("slow-tests"), before)
        self.assertEqual(git(self.api_root, "log", "--format=%s"), "Fixture")

    def test_missing_token_and_foreign_origin_are_refused(self) -> None:
        before = self.sha("slow-tests")
        payload = {"expected_sha256": before}
        no_token = self.post("/api/discoveries/slow-tests/retain", payload, token=False)
        self.assertEqual(no_token.status_code, 403, no_token.text)
        foreign = self.post("/api/discoveries/slow-tests/retain", payload, headers={"Origin": "https://evil.example"})
        self.assertEqual(foreign.status_code, 403, foreign.text)
        cross_site = self.post("/api/discoveries/slow-tests/retain", payload, headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(cross_site.status_code, 403, cross_site.text)
        with _client(self.api_root) as client:
            token = client.get("/api/session").json()["write_token"]
            not_json = client.post(
                "/api/discoveries/slow-tests/retain",
                content=json.dumps(payload),
                headers={TOKEN_HEADER: token, "Content-Type": "text/plain"},
            )
        self.assertEqual(not_json.status_code, 400, not_json.text)
        self.assertEqual(self.sha("slow-tests"), before)

    def test_a_review_whose_reindex_fails_is_still_committed(self) -> None:
        from unittest.mock import patch

        from knowledge_os.workspace import WorkspaceError

        with patch("knowledge_os.discovery.refresh_derived_indexes", side_effect=WorkspaceError("index is busy")):
            response = self.post(
                "/api/discoveries/slow-tests/reject", {"expected_sha256": self.sha("slow-tests"), "reason": "no"}
            )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual((body["status"], body["index_count"]), ("rejected", None))
        self.assertIn("index is busy", body["index_error"])
        self.assertTrue(body["commit"]["committed"], body["commit"])

    def test_pending_rows_carry_what_the_actions_need(self) -> None:
        with _client(self.api_root) as client:
            payload = client.get("/api/discoveries/pending").json()
        rows = {item["id"]: item for item in payload["items"]}
        friday = rows["friday-deploys"]
        self.assertEqual(friday["content_sha256"], self.sha("friday-deploys"))
        self.assertEqual(friday["scope"], "project:demo")
        self.assertTrue(friday["actions"]["retain"])
        self.assertEqual(
            friday["actions"]["promote"],
            {
                "target_id": "deploys-fail-on-fridays",
                "title": "Deploys fail on Fridays",
                "acknowledge_related": True,
                "allow_scope_broadening": True,
            },
        )
        general = rows["general-note"]["actions"]
        self.assertFalse(general["retain"])
        self.assertFalse(general["promote"]["acknowledge_related"])
        self.assertFalse(general["promote"]["allow_scope_broadening"])
        self.assertIn("undo", payload["notice_labels"])
