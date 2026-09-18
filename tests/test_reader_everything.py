"""Tests for the Everything view, ``GET /everything``.

The real workspace (13 project records, 4 skills) has no sources and no
discoveries, so the states that matter most for acceptance criterion 10
(sources and rejected discoveries reachable, carrying their trust label,
never inside a governing group) cannot be exercised on it. This suite builds
its own fixture workspace with a source record and a discovery at every
review status, plus a broken record and a skill, and checks both the pure
label-selection helpers directly and the rendered page end-to-end via
``reader_support.serve()``.

Follows the repository convention: unittest only, workspaces built on disk
in a ``TemporaryDirectory()``, no pytest, no fixtures.
"""

from __future__ import annotations

import tempfile
import unittest
import urllib.request
from pathlib import Path

from reader_support import create_workspace, serve, write_record

from knowledge_os.reader import library, strings
from knowledge_os.reader.views import everything
from knowledge_os.workspace import Workspace

PORT = 8816


def _metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "demo",
        "title": "Demo",
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": "demo"}],
    }
    metadata.update(overrides)
    return metadata


def _load(builder) -> library.Library:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        create_workspace(root)
        builder(root)
        return library.load_library(Workspace(root))


class TrustPhraseHelperTests(unittest.TestCase):
    """Direct tests of the label-selection helpers; no server involved."""

    def test_raw_source_never_prints_the_raw_trust_label(self) -> None:
        lib = _load(
            lambda root: write_record(
                root, "sources/raw.md", _metadata(id="raw", type="source", title="Raw source")
            )
        )
        record = lib.records_by_id["raw"]
        self.assertEqual(record.trust_label, "raw source; not established knowledge")
        phrase = everything._trust_phrase(record, lib)
        self.assertEqual(phrase, strings.TRUST_LABELS["raw source; not established knowledge"])
        self.assertEqual(everything._record_accent(record), "raw")

    def test_discovery_statuses_get_distinct_phrasing_and_accents(self) -> None:
        def builder(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _metadata(id="demo", type="project", scope="project:demo"))
            write_record(
                root,
                "discoveries/proposed-one.md",
                _metadata(
                    id="proposed-one",
                    type="discovery",
                    status="proposed",
                    scope="project:demo",
                    evidence=[{"kind": "fixture", "reference": "x"}],
                ),
            )
            write_record(
                root,
                "discoveries/retained-one.md",
                _metadata(
                    id="retained-one",
                    type="discovery",
                    status="retained",
                    scope="project:demo",
                    evidence=[{"kind": "fixture", "reference": "x"}],
                    reviews=[{"decision": "retain", "date": "2026-08-29"}],
                ),
            )
            write_record(
                root,
                "discoveries/rejected-one.md",
                _metadata(
                    id="rejected-one",
                    type="discovery",
                    status="rejected",
                    scope="project:demo",
                    evidence=[{"kind": "fixture", "reference": "x"}],
                    reviews=[{"decision": "reject", "date": "2026-08-29", "reason": "no longer applicable"}],
                ),
            )

        lib = _load(builder)
        proposed = lib.records_by_id["proposed-one"]
        retained = lib.records_by_id["retained-one"]
        rejected = lib.records_by_id["rejected-one"]

        # trust_label() collapses proposed/rejected to the same string; the
        # view must still tell them apart via Record.status.
        self.assertEqual(proposed.trust_label, "discovery observation; not default context")
        self.assertEqual(rejected.trust_label, "discovery observation; not default context")
        self.assertEqual(everything._trust_phrase(proposed, lib), strings.DISCOVERY_STATUS["proposed"])
        self.assertEqual(everything._trust_phrase(retained, lib), strings.DISCOVERY_STATUS["retained"])
        self.assertEqual(everything._trust_phrase(rejected, lib), strings.DISCOVERY_STATUS["rejected"])

        # An unreviewed (proposed) discovery reads as raw; a reviewed one
        # (retained or rejected) is neutral, whichever way it was decided.
        self.assertEqual(everything._record_accent(proposed), "raw")
        self.assertIsNone(everything._record_accent(retained))
        self.assertIsNone(everything._record_accent(rejected))

    def test_unusable_durable_record_never_prints_the_raw_trust_label(self) -> None:
        def builder(root: Path) -> None:
            write_record(root, "knowledge/deprecated-one.md", _metadata(id="deprecated-one", status="deprecated"))
            write_record(root, "knowledge/archived-one.md", _metadata(id="archived-one", status="archived"))

        lib = _load(builder)
        deprecated = lib.records_by_id["deprecated-one"]
        archived = lib.records_by_id["archived-one"]
        self.assertEqual(deprecated.trust_label, "unusable durable record")
        self.assertEqual(archived.trust_label, "unusable durable record")

        deprecated_phrase = everything._trust_phrase(deprecated, lib)
        archived_phrase = everything._trust_phrase(archived, lib)
        self.assertEqual(deprecated_phrase, strings.LIFECYCLE_STATUS["deprecated"])
        self.assertEqual(archived_phrase, strings.LIFECYCLE_STATUS["archived"])
        self.assertNotEqual(deprecated_phrase, archived_phrase)
        self.assertNotIn("unusable durable record", deprecated_phrase)
        self.assertNotIn("unusable durable record", archived_phrase)
        self.assertEqual(everything._record_accent(deprecated), "retired")

    def test_decision_draft_and_active_get_plan_language(self) -> None:
        def builder(root: Path) -> None:
            write_record(root, "projects/demo/README.md", _metadata(id="demo", type="project", scope="project:demo"))
            write_record(
                root,
                "projects/demo/decisions/proposal.md",
                {
                    "id": "proposal",
                    "title": "A proposal",
                    "type": "project",
                    "status": "draft",
                    "scope": "project:demo",
                    "record_kind": "decision",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            write_record(
                root,
                "projects/demo/decisions/accepted.md",
                {
                    "id": "accepted",
                    "title": "An accepted decision",
                    "type": "project",
                    "status": "active",
                    "scope": "project:demo",
                    "record_kind": "decision",
                    "created": "2026-08-29",
                    "updated": "2026-08-30",
                    "provenance": [
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:2026-08-30:demo",
                            "captured": "2026-08-30T00:00:00Z",
                        }
                    ],
                },
            )

        lib = _load(builder)
        draft = lib.records_by_id["proposal"]
        active = lib.records_by_id["accepted"]

        self.assertEqual(everything._trust_phrase(draft, lib), strings.DECISION_STATUS["draft"])
        self.assertEqual(everything._record_accent(draft), "proposed")

        self.assertEqual(
            everything._trust_phrase(active, lib),
            strings.DECISION_STATUS["active"].format(date="30 August"),
        )
        # An accepted (governing) decision is neutral, not "unverified":
        # a decision is confirmed by acceptance, not by the verified field.
        self.assertIsNone(everything._record_accent(active))

    def test_ordinary_draft_and_active_durable_records_are_unverified(self) -> None:
        def builder(root: Path) -> None:
            write_record(root, "knowledge/draft-one.md", _metadata(id="draft-one", status="draft"))
            write_record(root, "knowledge/active-one.md", _metadata(id="active-one", status="active"))

        lib = _load(builder)
        draft = lib.records_by_id["draft-one"]
        active = lib.records_by_id["active-one"]
        self.assertEqual(everything._trust_phrase(draft, lib), strings.TRUST_LABELS["draft durable; not verified"])
        self.assertEqual(everything._trust_phrase(active, lib), strings.TRUST_LABELS["active durable; not verified"])
        self.assertEqual(everything._record_accent(draft), "unverified")
        self.assertEqual(everything._record_accent(active), "unverified")


class EverythingViewServeTests(unittest.TestCase):
    """End-to-end: serve a fixture workspace and read the rendered page."""

    def test_everything_page_covers_sources_discoveries_skills_and_broken_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo/README.md", _metadata(id="demo", type="project", scope="project:demo"))
            write_record(
                root,
                "sources/raw.md",
                _metadata(id="raw", type="source", title="Raw source", scope="project:demo"),
            )
            write_record(
                root,
                "discoveries/proposed-one.md",
                _metadata(
                    id="proposed-one",
                    type="discovery",
                    status="proposed",
                    title="Proposed observation",
                    scope="project:demo",
                    evidence=[{"kind": "fixture", "reference": "x"}],
                ),
            )
            write_record(
                root,
                "discoveries/retained-one.md",
                _metadata(
                    id="retained-one",
                    type="discovery",
                    status="retained",
                    title="Retained observation",
                    scope="project:demo",
                    evidence=[{"kind": "fixture", "reference": "x"}],
                    reviews=[{"decision": "retain", "date": "2026-08-29"}],
                ),
            )
            write_record(
                root,
                "discoveries/rejected-one.md",
                _metadata(
                    id="rejected-one",
                    type="discovery",
                    status="rejected",
                    title="Rejected observation",
                    scope="project:demo",
                    evidence=[{"kind": "fixture", "reference": "x"}],
                    reviews=[{"decision": "reject", "date": "2026-08-29", "reason": "no longer applicable"}],
                ),
            )
            (root / "knowledge" / "broken.md").write_text("no frontmatter here\n", encoding="utf-8")
            skill_dir = root / "skills" / "demo-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(
                "---\n"
                "name: demo-skill\n"
                "description: A fixture skill for the everything view test.\n"
                "---\n\n"
                "Body.\n",
                encoding="utf-8",
            )

            before = {path: path.stat().st_mtime_ns for path in root.rglob("*") if path.is_file()}

            with serve(root, PORT) as base_url:
                start_response = urllib.request.urlopen(f"{base_url}/")
                self.assertEqual(start_response.status, 200)

                response = urllib.request.urlopen(f"{base_url}/everything")
                self.assertEqual(response.status, 200)
                html = response.read().decode("utf-8")

            after = {path: path.stat().st_mtime_ns for path in root.rglob("*") if path.is_file()}
            self.assertEqual(before, after, "serving must leave the workspace byte-identical, including mtimes")

            self.assertIn("Raw source", html)
            self.assertIn(strings.TRUST_LABELS["raw source; not established knowledge"], html)

            self.assertIn("Proposed observation", html)
            self.assertIn(strings.DISCOVERY_STATUS["proposed"], html)
            self.assertIn("Retained observation", html)
            self.assertIn(strings.DISCOVERY_STATUS["retained"], html)
            self.assertIn("Rejected observation", html)
            self.assertIn(strings.DISCOVERY_STATUS["rejected"], html)

            self.assertIn("demo-skill", html)
            self.assertIn(strings.SKILL_TRUST_LABEL, html)

            self.assertIn(strings.BROKEN_RECORD_LABEL, html)
            self.assertIn("knowledge/broken.md", html)

            # Acceptance criterion 10: reachable and labelled, but never
            # inside a governing (meaning-based) group. Checked against the
            # exact header markup, not a bare substring: some header words
            # ("Raw material", "Proposed") legitimately recur inside trust
            # phrases and fixture titles elsewhere on this same page.
            for header in strings.PROJECT_GROUP_HEADERS.values():
                self.assertNotIn(f'class="group__header">{header}<', html)

            # The raw contract trust-label strings must never leak through.
            self.assertNotIn("discovery observation; not default context", html)
            self.assertNotIn("unusable durable record", html)

    def test_everything_route_is_reachable_at_the_root_url(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/plain.md", _metadata(id="plain", title="Plain"))
            with serve(root, PORT) as base_url:
                response = urllib.request.urlopen(f"{base_url}/everything")
                self.assertEqual(response.status, 200)
                html = response.read().decode("utf-8")
                self.assertIn("Plain", html)
                self.assertIn(strings.EVERYTHING_TITLE, html)


if __name__ == "__main__":
    unittest.main()
