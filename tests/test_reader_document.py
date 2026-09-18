"""Tests for the document view, knowledge_os/reader/views/document.py.

Split in two halves, matching the repository's existing convention
(unittest, no pytest, no fixtures, workspaces built on disk in a
TemporaryDirectory):

* ``_build_context`` and its helpers are pure functions of a ``Library``, so
  most of the interesting behaviour (status/trust sentences, the leading-H1
  strip, heading-id injection, provenance overflow, an unresolved relation,
  a superseded lookup) is tested directly, without a server.
* A handful of end-to-end checks run the real ``kos-read`` process via
  ``reader_support.serve`` and assert on the rendered HTML and on
  ``static/reader.css``, covering the acceptance criteria that need an
  actual HTTP response or the real corpus: criterion 4 (openknowledge-pivot
  reads as an undecided proposal, technical details match ``kos inspect``),
  criterion 5 (inbound relations in examples/context-workspace), and
  criterion 9 (the reading column's measure and the responsive breakpoints).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY, create_workspace, serve, write_record

from knowledge_os.reader import library
from knowledge_os.reader.views import document
from knowledge_os.workspace import Workspace

PORT = 8812


def _knowledge_metadata(**overrides: object) -> dict[str, object]:
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


def _project_metadata(**overrides: object) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": "demo-project",
        "title": "Demo project",
        "type": "project",
        "status": "active",
        "scope": "project:demo-project",
        "created": "2026-08-29",
        "updated": "2026-08-29",
        "provenance": [{"kind": "fixture", "reference": "demo"}],
    }
    metadata.update(overrides)
    return metadata


class FormatDateTests(unittest.TestCase):
    def test_plain_date(self) -> None:
        self.assertEqual(document._format_date("2026-08-30"), "30 August 2026")

    def test_timestamp(self) -> None:
        self.assertEqual(document._format_date("2026-08-30T00:00:00Z"), "30 August 2026")

    def test_unparseable_value_falls_back_unchanged(self) -> None:
        self.assertEqual(document._format_date("not-a-date"), "not-a-date")


class StripLeadingH1Tests(unittest.TestCase):
    def test_leading_h1_is_removed(self) -> None:
        body = "# Record model\n\n## Managed roots\n\nText.\n"
        self.assertEqual(document._strip_leading_h1(body), "## Managed roots\n\nText.\n")

    def test_no_leading_h1_is_unchanged(self) -> None:
        body = "## Managed roots\n\nText.\n"
        self.assertEqual(document._strip_leading_h1(body), body)

    def test_leading_h2_is_not_stripped(self) -> None:
        body = "## Not a title\n\nText.\n"
        self.assertEqual(document._strip_leading_h1(body), body)

    def test_h1_further_down_is_not_stripped(self) -> None:
        body = "Intro text.\n\n# A heading later\n"
        self.assertEqual(document._strip_leading_h1(body), body)


class HeadingIdInjectionTests(unittest.TestCase):
    def test_ids_assigned_in_document_order(self) -> None:
        body = "## One\n\nText.\n\n## Two\n\nMore text.\n"
        html = document.markdown.render(body)
        anchors = [anchor for _level, _text, anchor in document.markdown.headings(body)]
        for anchor in anchors:
            self.assertEqual(html.count(f'id="{anchor}"'), 1)


class StatusAndTrustSentenceTests(unittest.TestCase):
    def _library(self, root: Path) -> library.Library:
        return library.load_library(Workspace(root))

    def test_draft_decision_reads_as_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "projects/demo-project/README.md",
                _project_metadata(),
            )
            write_record(
                root,
                "projects/demo-project/decisions/pivot.md",
                _project_metadata(
                    id="pivot",
                    title="Pivot",
                    status="draft",
                    record_kind="decision",
                    provenance=[
                        {"kind": "user-approved-conversation", "reference": "conversation:x"}
                    ],
                ),
            )
            lib = self._library(root)
            record = lib.records_by_id["pivot"]
            sentence, accent = document._status_sentence(lib, record)
            self.assertEqual(sentence, "Proposal — nobody has taken a position yet")
            self.assertEqual(accent, "proposed")

    def test_active_decision_shows_accepted_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo-project/README.md", _project_metadata())
            write_record(
                root,
                "projects/demo-project/decisions/choice.md",
                _project_metadata(
                    id="choice",
                    title="Choice",
                    status="active",
                    record_kind="decision",
                    provenance=[
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:x",
                            "captured": "2026-08-30T00:00:00Z",
                        }
                    ],
                ),
            )
            lib = self._library(root)
            record = lib.records_by_id["choice"]
            sentence, accent = document._status_sentence(lib, record)
            self.assertEqual(sentence, "In force — accepted 30 August 2026")
            self.assertIsNone(accent)

    def test_superseded_decision_resolves_successor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo-project/README.md", _project_metadata())
            write_record(
                root,
                "projects/demo-project/decisions/old.md",
                _project_metadata(
                    id="old",
                    title="Old choice",
                    status="superseded",
                    record_kind="decision",
                    provenance=[
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:x",
                            "captured": "2026-08-01T00:00:00Z",
                        }
                    ],
                ),
            )
            write_record(
                root,
                "projects/demo-project/decisions/new.md",
                _project_metadata(
                    id="new",
                    title="New choice",
                    status="active",
                    record_kind="decision",
                    supersedes=["old"],
                    provenance=[
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:y",
                            "captured": "2026-08-30T00:00:00Z",
                        }
                    ],
                ),
            )
            lib = self._library(root)
            record = lib.records_by_id["old"]
            sentence, accent = document._status_sentence(lib, record)
            self.assertEqual(sentence, "Replaced by New choice on 30 August 2026")
            self.assertEqual(accent, "retired")

    def test_superseded_with_no_resolvable_successor_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo-project/README.md", _project_metadata())
            write_record(
                root,
                "projects/demo-project/decisions/orphan.md",
                _project_metadata(
                    id="orphan",
                    title="Orphan",
                    status="superseded",
                    record_kind="decision",
                    provenance=[
                        {
                            "kind": "decision-acceptance",
                            "reference": "conversation:x",
                            "captured": "2026-08-01T00:00:00Z",
                        }
                    ],
                ),
            )
            lib = self._library(root)
            record = lib.records_by_id["orphan"]
            sentence, accent = document._status_sentence(lib, record)
            self.assertEqual(sentence, document.strings.DOCUMENT_SUPERSEDED_UNKNOWN)
            self.assertEqual(accent, "retired")

    def test_ordinary_active_record_is_current_with_no_accent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata())
            lib = self._library(root)
            record = lib.records_by_id["demo"]
            sentence, accent = document._status_sentence(lib, record)
            self.assertEqual(sentence, "Current")
            self.assertIsNone(accent)

    def test_deprecated_record_is_retired(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata(status="deprecated"))
            lib = self._library(root)
            record = lib.records_by_id["demo"]
            sentence, accent = document._status_sentence(lib, record)
            self.assertEqual(sentence, "Discouraged")
            self.assertEqual(accent, "retired")

    def test_trust_sentence_for_unverified_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata(status="draft"))
            lib = self._library(root)
            record = lib.records_by_id["demo"]
            sentence, accent = document._trust_sentence(record)
            self.assertEqual(sentence, "Draft, not confirmed")
            self.assertEqual(accent, "unverified")

    def test_trust_sentence_for_verified_record_fills_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata(verified="2026-08-29"))
            lib = self._library(root)
            record = lib.records_by_id["demo"]
            sentence, accent = document._trust_sentence(record)
            self.assertEqual(sentence, "Confirmed 29 August 2026")
            self.assertIsNone(accent)

    def test_trust_sentence_for_raw_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "sources/raw.md",
                {
                    "id": "raw",
                    "title": "Raw",
                    "type": "source",
                    "status": "active",
                    "scope": "general",
                    "created": "2026-08-29",
                    "updated": "2026-08-29",
                    "provenance": [{"kind": "fixture", "reference": "demo"}],
                },
            )
            lib = self._library(root)
            record = lib.records_by_id["raw"]
            sentence, accent = document._trust_sentence(record)
            self.assertEqual(sentence, "Raw material. Nobody has checked it.")
            self.assertEqual(accent, "raw")


class ScopeSentenceTests(unittest.TestCase):
    def test_general_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata())
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            self.assertEqual(document._scope_sentence(lib, record), "Applies everywhere")

    def test_project_scope_resolves_to_project_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "projects/demo-project/README.md", _project_metadata())
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo-project"]
            self.assertEqual(document._scope_sentence(lib, record), "Demo project")


class ProvenanceSentenceTests(unittest.TestCase):
    def test_fallback_kind_shows_raw_kind_and_reference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/demo.md",
                _knowledge_metadata(
                    provenance=[{"kind": "repository-file", "reference": "README.md"}]
                ),
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            sentence = document._provenance_sentence(lib, record, record.provenance[0])
            self.assertEqual(sentence, "repository-file: README.md")

    def test_user_approved_conversation_falls_back_to_created_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(
                root,
                "knowledge/demo.md",
                _knowledge_metadata(
                    created="2026-08-30",
                    updated="2026-08-30",
                    provenance=[
                        {"kind": "user-approved-conversation", "reference": "conversation:x"}
                    ],
                ),
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            sentence = document._provenance_sentence(lib, record, record.provenance[0])
            self.assertEqual(sentence, "A conversation you approved on 30 August 2026")

    def test_discovery_kind_resolves_target_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/target.md", _knowledge_metadata(id="target", title="Target"))
            write_record(
                root,
                "knowledge/demo.md",
                _knowledge_metadata(provenance=[{"kind": "discovery", "reference": "target"}]),
            )
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            sentence = document._provenance_sentence(lib, record, record.provenance[0])
            self.assertEqual(sentence, "Came from the observation Target")


class RelationViewTests(unittest.TestCase):
    def test_unresolved_relation_shows_broken_relation_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata(related=["missing"]))
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            [view] = [document._relation_view(relation) for relation in record.outbound]
            self.assertIsNone(view["href"])
            self.assertEqual(view["title"], "points at unknown id missing")


class BuildContextTests(unittest.TestCase):
    def test_provenance_overflow_split(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            provenance = [
                {"kind": "repository-file", "reference": f"file-{index}.md"} for index in range(5)
            ]
            write_record(root, "knowledge/demo.md", _knowledge_metadata(provenance=provenance))
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            context = document._build_context(lib, record)
            self.assertEqual(len(context["provenance_shown"]), 3)
            self.assertEqual(len(context["provenance_rest"]), 2)

    def test_short_provenance_has_no_overflow(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata())
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            context = document._build_context(lib, record)
            self.assertEqual(context["provenance_rest"], [])

    def test_toc_empty_for_headingless_body(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata(), body="Just a paragraph.\n")
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            context = document._build_context(lib, record)
            self.assertEqual(context["toc"], [])

    def test_content_sha256_matches_library_helper(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            path = write_record(root, "knowledge/demo.md", _knowledge_metadata())
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            context = document._build_context(lib, record)
            self.assertEqual(context["content_sha256_value"], library.content_sha256(path))

    def test_title_never_falls_back_to_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata(title="A Real Title"))
            lib = library.load_library(Workspace(root))
            record = lib.records_by_id["demo"]
            context = document._build_context(lib, record)
            self.assertEqual(context["record"].title, "A Real Title")


class EndToEndTests(unittest.TestCase):
    """Runs the real kos-read process (reader_support.serve) against this
    repository's own workspace and the examples/context-workspace fixture,
    covering acceptance criteria 4, 5, and 9."""

    def test_start_and_document_routes_are_healthy(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            with urllib.request.urlopen(f"{base_url}/") as response:
                self.assertEqual(response.status, 200)
            with urllib.request.urlopen(f"{base_url}/r/openknowledge-pivot") as response:
                self.assertEqual(response.status, 200)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(f"{base_url}/r/does-not-exist")
            self.assertEqual(caught.exception.code, 404)

    def test_openknowledge_pivot_reads_as_undecided_proposal(self) -> None:
        # Acceptance criterion 4.
        with serve(REPOSITORY, PORT) as base_url:
            with urllib.request.urlopen(f"{base_url}/r/openknowledge-pivot") as response:
                html = response.read().decode("utf-8")

            reading_column = html.split('<div class="reading">', 1)[1].split("</main>", 1)[0]
            for forbidden in ("draft", "provenance", "content_sha256", ".md"):
                self.assertNotIn(forbidden, reading_column.lower())

            self.assertIn("Proposal — nobody has taken a position yet", html)
            self.assertIn("A conversation you approved on 30 August 2026", html)

            # `python -m knowledge_os.cli` does not invoke main() (the module
            # has no __main__ guard; that is what the installed `kos` console
            # script is for), so call main() directly with an explicit argv.
            inspect = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "import sys\nfrom knowledge_os.cli import main\nsys.exit(main(sys.argv[1:]))",
                    "--root",
                    str(REPOSITORY),
                    "inspect",
                    "openknowledge-pivot",
                ],
                cwd=REPOSITORY,
                capture_output=True,
                text=True,
                check=True,
            )
            inspected = json.loads(inspect.stdout)

            tech_details = html.split('<summary>Technical details</summary>', 1)[1]
            self.assertIn(f"<dd>{inspected['status']}</dd>", tech_details)
            self.assertIn(f"<dd>{inspected['trust']}</dd>", tech_details)
            self.assertIn(f"<dd>{inspected['scope']}</dd>", tech_details)
            self.assertIn(f"<dd>{inspected['path']}</dd>", tech_details)
            self.assertIn(f"<dd>{inspected['content_sha256']}</dd>", tech_details)

    def test_inbound_relation_in_context_workspace_fixture(self) -> None:
        # Acceptance criterion 5.
        fixture_root = REPOSITORY / "examples" / "context-workspace"
        with serve(fixture_root, PORT) as base_url:
            with urllib.request.urlopen(f"{base_url}/r/provenance-boundaries") as response:
                html = response.read().decode("utf-8")
            self.assertIn("url-ingestion-provenance", html)
            self.assertIn("URL ingestion and provenance decision", html)

    def test_workspace_is_byte_identical_after_serving(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            create_workspace(root)
            write_record(root, "knowledge/demo.md", _knowledge_metadata())
            before = {
                path: (path.stat().st_mtime_ns, path.read_bytes())
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }
            with serve(root, PORT) as base_url:
                with urllib.request.urlopen(f"{base_url}/r/demo") as response:
                    self.assertEqual(response.status, 200)
            after = {
                path: (path.stat().st_mtime_ns, path.read_bytes())
                for path in sorted(root.rglob("*"))
                if path.is_file()
            }
            self.assertEqual(before, after)


class ReadingColumnCssTests(unittest.TestCase):
    """Acceptance criterion 9, by CSS inspection rather than screenshot."""

    def test_measure_is_in_68_to_72_characters(self) -> None:
        css = (REPOSITORY / "knowledge_os" / "reader" / "static" / "reader.css").read_text(encoding="utf-8")
        match = re.search(r"--measure:\s*(\d+)ch", css)
        self.assertIsNotNone(match, "expected a --measure: NNch token in reader.css")
        self.assertTrue(68 <= int(match.group(1)) <= 72)
        self.assertIn(".reading {", css)
        self.assertIn("max-width: var(--measure);", css)

    def test_responsive_breakpoints_exist(self) -> None:
        css = (REPOSITORY / "knowledge_os" / "reader" / "static" / "reader.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 900px)", css)
        self.assertIn("@media (max-width: 600px)", css)


if __name__ == "__main__":
    unittest.main()
