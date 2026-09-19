"""End-to-end tests for ``GET /api/search``: filters, a missing index, and
a stale index (Sec.6 "Missing index" / "Stale index", acceptance
criterion 7).
"""

from __future__ import annotations

import json
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

from knowledge_os.index import rebuild_indexes
from knowledge_os.workspace import Workspace

PORT = 8834


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read())


def _record(record_id: str, **overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": record_id,
        "title": overrides.pop("title", record_id.title()),
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": record_id}],
    }
    metadata.update(overrides)
    return metadata


class MissingIndexTests(unittest.TestCase):
    def test_search_reports_unavailable_and_browsing_still_works(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _record("plain"))
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=plain")
                self.assertFalse(data["search_available"])
                self.assertIn("kos index", data["disabled_reason"])
                self.assertEqual(data["results"], [])

                # Browsing still works.
                with urllib.request.urlopen(base_url + "/api/records/plain", timeout=5) as response:
                    self.assertEqual(response.status, 200)


class StaleIndexTests(unittest.TestCase):
    def test_search_reports_stale_after_an_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(root, "knowledge/plain.md", _record("plain"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            # Edit the record after indexing, with a newer mtime than the
            # index build (a filesystem-timestamp race on a very fast
            # machine is why this sleeps briefly rather than editing
            # instantly).
            time.sleep(0.05)
            path.write_text(path.read_text(encoding="utf-8").replace("Body.", "Edited body."), encoding="utf-8")

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/workspace")
                self.assertTrue(data["health"]["index_stale"])
                self.assertTrue(data["health"]["search_disabled"])


class FilterTests(unittest.TestCase):
    def test_type_filter_narrows_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/apple.md", _record("apple", title="Apple pie recipe"))
            write_record(
                root,
                "sources/apple-source.md",
                _record("apple-source", type="source", title="Apple pie source material"),
            )
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=apple&type=source")
                self.assertTrue(data["search_available"])
                ids = {r["id"] for r in data["results"]}
                self.assertEqual(ids, {"apple-source"})

    def test_unknown_filter_value_is_dropped_not_trusted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/apple.md", _record("apple"))
            workspace = Workspace(root)
            rebuild_indexes(workspace)

            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/search?q=apple&type=not-a-real-type")
                self.assertEqual(data["filters"], {})
                self.assertEqual({r["id"] for r in data["results"]}, {"apple"})


if __name__ == "__main__":
    unittest.main()
