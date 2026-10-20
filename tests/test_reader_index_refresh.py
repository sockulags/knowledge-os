"""Tests for the reader's background search-index rebuild,
knowledge_os/reader/index_refresh.py: a stale or missing index is rebuilt
through ``kos index``'s own code path without blocking a request, at most one
rebuild runs at a time, and a rebuild that did not help is not repeated until
the corpus changes.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.reader import strings
from knowledge_os.reader.index_refresh import IndexRefresher
from knowledge_os.reader.library import load_library
from knowledge_os.workspace import Workspace


def _metadata(record_id: str, **overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": record_id.title(),
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": record_id}],
    }
    metadata.update(overrides)
    return metadata


class _CountingRebuild:
    """Stands in for ``rebuild_indexes``: counts calls, optionally fails, and
    can be held open to observe a rebuild in progress."""

    def __init__(self, *, fail: bool = False, hold: bool = False) -> None:
        self.calls = 0
        self.fail = fail
        self.release = threading.Event()
        if not hold:
            self.release.set()

    def __call__(self, workspace: Workspace) -> int:
        self.calls += 1
        self.release.wait(5)
        if self.fail:
            raise ValueError("disk full\nsecond line")
        return rebuild_indexes(workspace)


class IndexRefresherTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        create_workspace(self.root)
        self.path = write_record(self.root, "knowledge/plain.md", _metadata("plain"), body="Original words.\n")
        self.workspace = Workspace(self.root)
        rebuild_indexes(self.workspace)
        self.path.write_text(
            self.path.read_text(encoding="utf-8").replace("Original", "Edited"), encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._directory.cleanup()

    def test_stale_index_is_rebuilt_in_the_background(self) -> None:
        rebuild = _CountingRebuild()
        refresher = IndexRefresher(self.workspace, rebuild=rebuild)
        observed = refresher.observe(load_library(self.workspace))
        self.assertTrue(observed.index.refreshing)
        self.assertEqual(observed.index.message, strings.INDEX_HEALTH["refreshing"])
        self.assertNotIn("kos index", observed.index.message)

        refresher.wait(10)
        fresh = refresher.observe(load_library(self.workspace))
        self.assertEqual(rebuild.calls, 1)
        self.assertTrue(fresh.index.available)
        self.assertFalse(fresh.index.stale)
        self.assertFalse(fresh.index.refreshing)
        self.assertIsNone(fresh.index.message)

    def test_missing_index_is_built(self) -> None:
        (self.root / "indexes" / "catalog.sqlite3").unlink()
        refresher = IndexRefresher(self.workspace)
        self.assertTrue(refresher.observe(load_library(self.workspace)).index.refreshing)
        refresher.wait(10)
        self.assertTrue(load_library(self.workspace).index.available)

    def test_only_one_rebuild_runs_at_a_time(self) -> None:
        rebuild = _CountingRebuild(hold=True)
        refresher = IndexRefresher(self.workspace, rebuild=rebuild)
        refresher.observe(load_library(self.workspace))
        # The corpus changes again while the first rebuild is still running.
        self.path.write_text(self.path.read_text(encoding="utf-8") + "\nMore.\n", encoding="utf-8")
        second = refresher.observe(load_library(self.workspace))
        self.assertTrue(second.index.refreshing)
        rebuild.release.set()
        refresher.wait(10)
        self.assertEqual(rebuild.calls, 1)

    def test_failed_rebuild_is_not_retried_until_the_corpus_changes(self) -> None:
        rebuild = _CountingRebuild(fail=True)
        refresher = IndexRefresher(self.workspace, rebuild=rebuild)
        refresher.observe(load_library(self.workspace))
        refresher.wait(10)

        for _ in range(3):
            failed = refresher.observe(load_library(self.workspace))
            self.assertFalse(failed.index.refreshing)
            self.assertEqual(failed.index.message, strings.INDEX_HEALTH["refresh_failed"].format(detail="disk full"))
        self.assertEqual(rebuild.calls, 1)

        self.path.write_text(self.path.read_text(encoding="utf-8") + "\nChanged again.\n", encoding="utf-8")
        self.assertTrue(refresher.observe(load_library(self.workspace)).index.refreshing)
        refresher.wait(10)
        self.assertEqual(rebuild.calls, 2)

    def test_a_corpus_with_lint_issues_is_not_rebuilt(self) -> None:
        (self.root / "knowledge" / "broken.md").write_text("---\nid: broken\n---\n\nNo metadata.\n", encoding="utf-8")
        rebuild = _CountingRebuild()
        refresher = IndexRefresher(self.workspace, rebuild=rebuild)
        observed = refresher.observe(load_library(self.workspace))
        self.assertFalse(observed.index.refreshing)
        self.assertEqual(observed.index.message, strings.INDEX_HEALTH["refresh_blocked"])
        self.assertEqual(rebuild.calls, 0)

    def test_disabled_refresher_only_reports(self) -> None:
        rebuild = _CountingRebuild()
        refresher = IndexRefresher(self.workspace, enabled=False, rebuild=rebuild)
        observed = refresher.observe(load_library(self.workspace))
        self.assertTrue(observed.index.stale)
        self.assertEqual(observed.index.message, strings.INDEX_HEALTH["stale"])
        self.assertEqual(rebuild.calls, 0)


class ServerRefreshTests(unittest.TestCase):
    def test_server_rebuilds_a_stale_index_and_search_comes_back(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(root, "knowledge/plain.md", _metadata("plain"), body="Original words.\n")
            rebuild_indexes(Workspace(root))
            path.write_text(path.read_text(encoding="utf-8").replace("Original", "Xylophone"), encoding="utf-8")

            with serve(root, refresh_index=True) as base_url:
                deadline = time.monotonic() + 10
                while True:
                    with urllib.request.urlopen(base_url + "/api/workspace", timeout=5) as response:
                        health = json.loads(response.read())["health"]
                    if not health["search_disabled"]:
                        break
                    self.assertTrue(health["index_refreshing"], health)
                    self.assertLess(time.monotonic(), deadline, "the index was never rebuilt")
                    time.sleep(0.1)
                self.assertFalse(health["index_stale"])
                self.assertFalse(health["index_refreshing"])

                with urllib.request.urlopen(base_url + "/api/search?q=xylophone", timeout=5) as response:
                    search = json.loads(response.read())
                self.assertTrue(search["search_available"])
                self.assertEqual([result["id"] for result in search["results"]], ["plain"])


if __name__ == "__main__":
    unittest.main()
