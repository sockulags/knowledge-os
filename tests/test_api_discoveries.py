"""Tests for ``GET /api/discoveries/pending``: the observations waiting for
review that Decide lists, each with its review packet and related pages.

Runs in-process with Starlette's TestClient from a loopback peer address
(the host guard refuses any other), against temporary workspaces.
"""

from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path

from reader_support import create_workspace, write_record

from knowledge_os.discovery import reject_discovery, retain_discovery
from knowledge_os.index import rebuild_indexes
from knowledge_os.workspace import Workspace


def _project(root: Path) -> None:
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


def _discovery(root: Path, record_id: str, title: str, body: str, *, created: str, scope: str = "project:demo") -> None:
    write_record(
        root,
        f"discoveries/{record_id}.md",
        {
            "id": record_id,
            "title": title,
            "type": "discovery",
            "status": "proposed",
            "scope": scope,
            "created": created,
            "updated": created,
            "provenance": [{"kind": "agent-run", "reference": "run-1"}],
            "evidence": [{"kind": "record", "reference": "demo"}],
        },
        body,
    )


class PendingDiscoveriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._stack = ExitStack()
        self.root = Path(self._stack.enter_context(tempfile.TemporaryDirectory()))
        create_workspace(self.root)
        _project(self.root)

    def tearDown(self) -> None:
        self._stack.close()

    def _get(self) -> dict:
        from starlette.testclient import TestClient

        from knowledge_os.reader.app import create_app

        workspace = Workspace.discover(self.root)
        rebuild_indexes(workspace)
        app = create_app(workspace, refresh_index=False)
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            response = client.get("/api/discoveries/pending")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_none_pending(self) -> None:
        payload = self._get()
        self.assertEqual(payload["count"], 0)
        self.assertIsNone(payload["count_label"])
        self.assertEqual(payload["items"], [])
        self.assertIsNone(payload["error"])

    def test_lists_pending_with_packet_and_excludes_reviewed(self) -> None:
        write_record(
            self.root,
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
        _discovery(self.root, "friday-deploys", "Deploys fail on Fridays", "Friday deploys failed twice.\n", created="2026-09-10")
        _discovery(self.root, "slow-tests", "Tests are slow", "The suite takes ten minutes.\n", created="2026-09-12")
        _discovery(self.root, "general-note", "General note", "Applies everywhere.\n", created="2026-09-05", scope="general")
        _discovery(self.root, "kept-note", "Kept note", "Kept.\n", created="2026-09-11")
        _discovery(self.root, "dropped-note", "Dropped note", "Dropped.\n", created="2026-09-11")
        workspace = Workspace.discover(self.root)
        rebuild_indexes(workspace)
        retain_discovery(workspace, "kept-note")
        reject_discovery(workspace, "dropped-note", reason="not true")

        payload = self._get()

        self.assertEqual(payload["count"], 3)
        self.assertEqual(payload["count_label"], "3 observations are waiting for review.")
        self.assertIsNone(payload["error"])
        ids = [item["id"] for item in payload["items"]]
        self.assertEqual(ids, ["slow-tests", "friday-deploys", "general-note"])

        friday = payload["items"][1]
        self.assertEqual(friday["title"], "Deploys fail on Fridays")
        self.assertEqual(friday["trust"], "Observation — not knowledge")
        self.assertEqual(friday["project"], {"id": "demo", "title": "Demo"})
        self.assertIn("Discovery review packet", friday["packet_html"])
        self.assertIn("Friday deploys failed twice.", friday["packet_html"])
        self.assertIn("deploy-freeze", [item["id"] for item in friday["related"]])
        self.assertIn("friday-deploys", friday["agent_phrase"])
        actions = {item["action"]: item["command"] for item in friday["commands"]}
        self.assertEqual(set(actions), {"retain", "reject", "promote"})
        self.assertIn(f'--root "{workspace.root}" discovery retain friday-deploys', actions["retain"])
        self.assertIn("--acknowledge-related", actions["promote"])

        general = payload["items"][2]
        self.assertNotIn("retain", [item["action"] for item in general["commands"]])

    def test_lists_pending_without_packets_when_the_index_is_stale(self) -> None:
        _discovery(self.root, "slow-tests", "Tests are slow", "The suite takes ten minutes.\n", created="2026-09-12")
        from starlette.testclient import TestClient

        from knowledge_os.reader.app import create_app

        # No index at all: the packets cannot be made, the count still shows.
        app = create_app(Workspace.discover(self.root), refresh_index=False)
        with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
            payload = client.get("/api/discoveries/pending").json()
        self.assertEqual(payload["count"], 1)
        self.assertIn("search index", payload["error"])
        self.assertIsNone(payload["items"][0]["packet_html"])
        self.assertIsNone(payload["items"][0]["related"])


if __name__ == "__main__":
    unittest.main()
