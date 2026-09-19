"""Tests for knowledge_os/reader/api/common.py: the JSON-shaping helpers
every API endpoint shares. Pure, no server needed.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from reader_support import create_workspace, write_record

from knowledge_os.reader.api import common
from knowledge_os.reader.library import load_library
from knowledge_os.workspace import Workspace


def _load(build) -> "common.Library":
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        create_workspace(root)
        build(root)
        return load_library(Workspace(root))


class PillForLifecycleStatusTests(unittest.TestCase):
    """A deprecated or archived ordinary record must get its own distinct
    grey pill label, not silently collapse to the generic "Replaced" word
    (the two status literals -- "deprecated"/"archived" -- do not spell the
    same as their pill words -- "Discouraged"/"Archived")."""

    def _record(self, status: str):
        def build(root: Path) -> None:
            write_record(
                root,
                "knowledge/old.md",
                {
                    "id": "old",
                    "title": "Old",
                    "type": "knowledge",
                    "status": status,
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = _load(build)
        return library.records_by_id["old"]

    def test_deprecated_record_gets_the_discouraged_label(self) -> None:
        pill = common.pill_for(self._record("deprecated"))
        self.assertEqual(pill, {"label": "Discouraged", "tone": "grey"})

    def test_archived_record_gets_the_archived_label(self) -> None:
        pill = common.pill_for(self._record("archived"))
        self.assertEqual(pill, {"label": "Archived", "tone": "grey"})


class PillForDecisionTests(unittest.TestCase):
    def test_draft_decision_is_amber_waiting(self) -> None:
        def build(root: Path) -> None:
            write_record(
                root,
                "projects/demo/README.md",
                {
                    "id": "demo",
                    "title": "Demo",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/idea.md",
                {
                    "id": "idea",
                    "title": "Idea",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "draft",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )

        library = _load(build)
        pill = common.pill_for(library.records_by_id["idea"])
        self.assertEqual(pill, {"label": "Waiting on you", "tone": "amber"})


if __name__ == "__main__":
    unittest.main()
