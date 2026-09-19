"""End-to-end tests for ``GET /api/everything``: acceptance criterion 10 --
sources and rejected discoveries are reachable, carry their trust label,
and never sit inside a governing group (there is no such group on this
page at all)."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

PORT = 8835


def _get(base_url: str, path: str) -> dict:
    with urllib.request.urlopen(base_url + path, timeout=5) as response:
        return json.loads(response.read())


class EverythingCatalogTests(unittest.TestCase):
    def test_sources_and_rejected_discoveries_are_listed_with_their_trust_label(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "sources/raw.md",
                {
                    "id": "raw",
                    "title": "Raw source",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "discoveries/dismissed.md",
                {
                    "id": "dismissed",
                    "title": "Dismissed observation",
                    "type": "discovery",
                    "status": "rejected",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-30",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                    "evidence": [{"kind": "fixture", "reference": "demo"}],
                    "reviews": [{"decision": "reject", "date": "2026-08-30", "reason": "Not corroborated."}],
                },
            )
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything")
                ids = {entry["id"]: entry for entry in data["entries"]}
                self.assertIn("raw", ids)
                self.assertIn("dismissed", ids)
                self.assertEqual(ids["raw"]["trust_phrase"], "Raw material. Nobody has checked it.")
                self.assertEqual(ids["dismissed"]["trust_phrase"], "Dismissed observation")
                # Never inside a governing pill/tone: a rejected discovery
                # and a raw source both carry a neutral-or-grey tone here,
                # never "In force" green.
                for entry_id in ("raw", "dismissed"):
                    pill = ids[entry_id]["status_pill"]
                    self.assertFalse(pill and pill["tone"] == "green")

    def test_broken_file_is_listed_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            (root / "knowledge" / "bad.md").write_text("not a record\n", encoding="utf-8")
            with serve(root, PORT) as base_url:
                data = _get(base_url, "/api/everything")
                self.assertEqual(len(data["broken"]), 1)
                self.assertEqual(data["broken"][0]["path"], "knowledge/bad.md")


if __name__ == "__main__":
    unittest.main()
