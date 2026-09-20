"""End-to-end tests for ``GET /api/records/{id}`` and
``GET /api/records/{id}/compare``: the real ``kos-read`` server, hit with
plain HTTP, asserting on the JSON it returns.

Covers acceptance criteria 4, 5, and 6 from ``docs/plans/reader-v1.md``
Sec.8 (an undecided proposal with no contract vocabulary in its properties,
inbound relations in ``examples/context-workspace``, a broken record
alongside readable neighbours), plus 404 JSON for an unknown id and
``content_sha256`` matching ``kos inspect``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve, write_record

PORT = 8833
CONTEXT_WORKSPACE = REPOSITORY / "examples" / "context-workspace"


def _get(base_url: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base_url + path, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class OpenknowledgePivotTests(unittest.TestCase):
    """Acceptance criterion 4: the real corpus's undecided proposal."""

    def test_reads_as_an_undecided_proposal_with_no_contract_vocabulary(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/records/openknowledge-pivot")
            self.assertEqual(status, 200)
            self.assertEqual(data["properties"]["status"]["value"], "Proposal — nobody has taken a position yet")
            self.assertEqual(data["properties"]["status"]["pill"]["tone"], "amber")
            self.assertIn("30 August 2026", data["properties"]["source"]["value"][0])

            # No contract vocabulary anywhere outside technical_details.
            surface = json.dumps({k: v for k, v in data.items() if k != "technical_details"})
            for forbidden in ('"draft"', '"provenance"', '"content_sha256"', ".md"):
                self.assertNotIn(forbidden, surface, f"{forbidden!r} leaked outside technical_details")

    def test_content_sha256_matches_kos_inspect(self) -> None:
        inspected = subprocess.run(
            [sys.executable, "-m", "knowledge_os", "inspect", "openknowledge-pivot"],
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=True,
        )
        expected = json.loads(inspected.stdout)["content_sha256"]
        with serve(REPOSITORY, PORT) as base_url:
            _status, data = _get(base_url, "/api/records/openknowledge-pivot")
            self.assertEqual(data["technical_details"]["content_sha256"], expected)
            self.assertEqual(data["technical_details"]["status"], "draft")
            self.assertEqual(data["technical_details"]["scope"], "project:knowledge-os")
            self.assertEqual(
                data["technical_details"]["path"], "projects/knowledge-os/decisions/openknowledge-pivot.md"
            )


class StatusAndTrustPillPlacementTests(unittest.TestCase):
    """A record's one colour pill sits on whichever properties row it
    actually describes: a decision's pill (a lifecycle state) belongs on
    Status; every other record's pill (an epistemic judgment) belongs on
    Trust, never both, and never Status for a non-decision -- "Unconfirmed"
    next to "Current" would read as the page contradicting itself."""

    def test_decision_carries_its_pill_on_status_not_trust(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            _status, data = _get(base_url, "/api/records/openknowledge-pivot")
            self.assertIsNotNone(data["properties"]["status"]["pill"])
            self.assertEqual(data["properties"]["status"]["pill"]["label"], "Waiting on you")
            self.assertIsNone(data["properties"]["trust"]["pill"])

    def test_ordinary_record_carries_its_pill_on_trust_not_status(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            _status, data = _get(base_url, "/api/records/knowledge-os-record-model")
            self.assertIsNone(data["properties"]["status"]["pill"])
            self.assertIsNotNone(data["properties"]["trust"]["pill"])
            self.assertEqual(data["properties"]["trust"]["pill"]["label"], "Unconfirmed")
            self.assertEqual(data["properties"]["status"]["value"], "Current")


class ProvenanceNeverLeaksAPathTests(unittest.TestCase):
    """``knowledge-os-record-model`` carries ten ``repository-file``
    provenance entries, each referencing a real workspace path (e.g.
    ``docs/architecture.md``). Design brief: "No contract vocabulary ...
    file paths ... outside the Technical details toggle." The properties
    block's Source sentences must never show one."""

    def test_record_model_source_sentences_have_no_file_paths(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/records/knowledge-os-record-model")
            self.assertEqual(status, 200)
            sources = data["properties"]["source"]["value"]
            self.assertGreaterEqual(len(sources), 10)
            for sentence in sources:
                self.assertNotIn(".md", sentence)
                self.assertNotIn(".py", sentence)
                self.assertNotIn("/", sentence)


class NotFoundTests(unittest.TestCase):
    def test_unknown_record_id_is_404_json(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/records/no-such-record")
            self.assertEqual(status, 404)
            self.assertIn("no-such-record", data["detail"])

    def test_unknown_record_compare_is_404_json(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            status, data = _get(base_url, "/api/records/no-such-record/compare")
            self.assertEqual(status, 404)
            self.assertIn("detail", data)


class InboundRelationTests(unittest.TestCase):
    """Acceptance criterion 5: inbound relations in examples/context-workspace."""

    def test_provenance_boundaries_shows_the_inbound_related_link(self) -> None:
        with serve(CONTEXT_WORKSPACE, PORT) as base_url:
            status, data = _get(base_url, "/api/records/provenance-boundaries")
            self.assertEqual(status, 200)
            inbound_ids = {relation["record_id"] for relation in data["inbound"]}
            self.assertIn("url-ingestion-provenance", inbound_ids)
            matching = [r for r in data["inbound"] if r["record_id"] == "url-ingestion-provenance"]
            self.assertEqual(matching[0]["field"], "related")
            self.assertTrue(matching[0]["resolved"])


class BrokenRecordAndCompareTests(unittest.TestCase):
    """Acceptance criterion 6: a corrupted file renders as broken while
    neighbours stay readable, and the compare page degrades cleanly."""

    def test_corrupted_frontmatter_does_not_break_sibling_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/good.md",
                {
                    "id": "good",
                    "title": "Good record",
                    "type": "knowledge",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            (root / "knowledge" / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")

            with serve(root, PORT) as base_url:
                status, data = _get(base_url, "/api/records/good")
                self.assertEqual(status, 200)
                self.assertEqual(data["title"], "Good record")

                status, data = _get(base_url, "/api/everything")
                self.assertEqual(status, 200)
                broken_paths = {entry["path"] for entry in data["broken"]}
                self.assertIn("knowledge/bad.md", broken_paths)
                self.assertTrue(any(entry["id"] == "good" for entry in data["entries"]))

    def test_changed_paragraph_marks_only_the_words_that_differ(self) -> None:
        # A "changed" paragraph pair must not read as "the whole thing is
        # different" when only a few words moved: the compare page's own
        # value is showing exactly what changed, not just that something
        # did. See knowledge_os/reader/api/record.py's `_word_diff_html`.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/old.md",
                {
                    "id": "old",
                    "title": "Old decision",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "superseded",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [
                        {"kind": "decision-acceptance", "reference": "c1", "captured": "2026-08-29T00:00:00Z"}
                    ],
                },
                body="Store every note in one flat file with no index.\n",
            )
            write_record(
                root,
                "projects/demo/decisions/new.md",
                {
                    "id": "new",
                    "title": "New decision",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "active",
                    "scope": "project:demo",
                    "supersedes": ["old"],
                    "created": "2026-08-30",
                    "updated": "2026-08-30",
                    "provenance": [
                        {"kind": "decision-acceptance", "reference": "c2", "captured": "2026-08-30T00:00:00Z"}
                    ],
                },
                body="Store every note in one file per topic with an index.\n",
            )
            with serve(root, PORT) as base_url:
                status, data = _get(base_url, "/api/records/old/compare")
                self.assertEqual(status, 200)
                blocks = data["comparisons"][0]["blocks"]
                self.assertEqual(len(blocks), 1)
                block = blocks[0]
                self.assertEqual(block["kind"], "changed")
                # Shared words survive unmarked...
                self.assertIn("Store every note in one", block["left_html"])
                self.assertIn("Store every note in one", block["right_html"])
                self.assertIn("file", block["left_html"])
                self.assertIn("with", block["left_html"])
                self.assertIn("with", block["right_html"])
                self.assertIn("index.", block["left_html"])
                self.assertIn("index.", block["right_html"])
                # ...only the words that actually moved are wrapped.
                self.assertIn("<mark>flat</mark>", block["left_html"])
                self.assertIn("<mark>no</mark>", block["left_html"])
                self.assertIn("<mark>per topic</mark>", block["right_html"])
                self.assertIn("<mark>an</mark>", block["right_html"])
                self.assertNotIn("<mark>Store", block["left_html"])
                self.assertNotIn("<mark>file</mark>", block["left_html"])

    def test_decision_with_no_lineage_reports_no_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/choice.md",
                {
                    "id": "choice",
                    "title": "Choice",
                    "type": "project",
                    "record_kind": "decision",
                    "status": "active",
                    "scope": "project:demo",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [
                        {"kind": "decision-acceptance", "reference": "c1", "captured": "2026-08-29T00:00:00Z"}
                    ],
                },
            )
            with serve(root, PORT) as base_url:
                status, data = _get(base_url, "/api/records/choice/compare")
                self.assertEqual(status, 200)
                self.assertEqual(data["comparisons"], [])
                self.assertEqual(data["status_text"], "In force — accepted 29 August 2026")


if __name__ == "__main__":
    unittest.main()
