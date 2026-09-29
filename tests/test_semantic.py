"""Search by meaning (issue #102): knowledge_os/semantic.py and its use in
the reader's search.

The real model is 590 MB and is never downloaded here. A small bag-of-words
embedder stands in for it: same interface, deterministic vectors, so the
index, the threshold, and the fusion with full-text search are tested
without it. tooling/eval_search_models.py measures the real model.
"""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from reader_support import create_workspace, write_record

from knowledge_os import semantic
from knowledge_os.index import rebuild_indexes
from knowledge_os.reader import library
from knowledge_os.workspace import Workspace, validate_workspace

try:
    import numpy as np
except ImportError:  # the search extra is optional
    np = None

#: Words the fake model treats as the same meaning, like a multilingual model would.
SYNONYMS = {"semester": "vacation", "ledighet": "vacation", "holiday": "vacation", "lön": "salary", "pay": "salary"}
SPEC = semantic.ModelSpec(
    name="fake",
    source="test",
    revision="0" * 40,
    base_url="https://example.invalid/model",
    files={},
    onnx_file="model.onnx",
    tokenizer_file="tokenizer.json",
    pooling="cls",
    dimensions=64,
    max_tokens=512,
    min_margin=0.2,
)


class FakeEmbedder:
    """Bag-of-words vectors over hashed, synonym-folded words."""

    spec = SPEC

    def __init__(self) -> None:
        self._np = np
        self.embedded: list[str] = []

    def embed(self, texts):  # type: ignore[no-untyped-def]
        rows = np.zeros((len(texts), SPEC.dimensions), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.lower().replace(".", " ").replace(",", " ").split():
                word = SYNONYMS.get(word, word)
                rows[row, int(hashlib.sha256(word.encode()).hexdigest(), 16) % SPEC.dimensions] += 1
            norm = np.linalg.norm(rows[row])
            if norm:
                rows[row] /= norm
        return rows

    def embed_query(self, text: str):  # type: ignore[no-untyped-def]
        return self.embed([text])[0]

    def embed_passages(self, texts):  # type: ignore[no-untyped-def]
        self.embedded.extend(texts)
        return self.embed(texts)


def _metadata(record_id: str, title: str) -> dict[str, object]:
    return {
        "id": record_id,
        "title": title,
        "type": "knowledge",
        "status": "active",
        "scope": "general",
        "created": "2026-09-29",
        "updated": "2026-09-29",
        "provenance": [{"kind": "fixture", "reference": record_id}],
    }


PAGES = {
    "leave": ("Leave", "Employees get twenty-five semester days each year, booked in the HR system."),
    "payday": ("Payday", "The lön is paid on the twenty-fifth of every month."),
    "coffee": ("Coffee machine", "The coffee machine on the third floor is descaled every Friday."),
    "backup": ("Backups", "The database is backed up every night at two and kept for thirty days."),
    "badges": ("Badges", "Visitors collect a badge at the front desk and return it when they leave."),
}


def _workspace(root: Path) -> Workspace:
    create_workspace(root)
    for record_id, (title, body) in PAGES.items():
        write_record(root, f"knowledge/{record_id}.md", _metadata(record_id, title), body + "\n")
    workspace = Workspace(root)
    rebuild_indexes(workspace)
    return workspace


def _documents(workspace: Workspace):  # type: ignore[no-untyped-def]
    documents, issues = validate_workspace(workspace)
    assert not issues, issues
    return documents


class PassageTests(unittest.TestCase):
    def test_passages_carry_title_and_heading_and_split_at_headings(self) -> None:
        body = "Intro text.\n\n## Setup\n\nInstall it.\n\n## Use\n\nRun it."
        self.assertEqual(
            semantic.passages("Tool", body),
            ["Tool\nIntro text.", "Tool\nSetup\nInstall it.", "Tool\nUse\nRun it."],
        )

    def test_the_pages_own_h1_is_not_repeated(self) -> None:
        self.assertEqual(semantic.passages("Tool", "# Tool\n\nText."), ["Tool\nText."])

    def test_a_heading_inside_a_code_fence_is_code(self) -> None:
        body = "## Real\n\n```sh\n\n# not a heading\n\n```\n\nAfter."
        result = semantic.passages("Page", body)
        self.assertTrue(all("\nReal\n" in passage for passage in result), result)

    def test_a_long_paragraph_is_cut_at_a_space(self) -> None:
        body = " ".join(["word"] * 1000)
        result = semantic.passages("Long", body, limit=200)
        self.assertGreater(len(result), 1)
        for passage in result:
            text = passage.split("\n", 1)[1]
            self.assertLessEqual(len(text), 200)
            self.assertFalse(text.startswith(" ") or text.endswith(" "))

    def test_links_keep_their_text_and_an_empty_page_is_its_title(self) -> None:
        self.assertEqual(semantic.passages("T", "See [the guide](guide.md)."), ["T\nSee the guide."])
        self.assertEqual(semantic.passages("Only title", ""), ["Only title"])


class InstallTests(unittest.TestCase):
    spec = semantic.ModelSpec(
        name="tiny",
        source="test",
        revision="a" * 40,
        base_url="https://example.invalid/tiny",
        files={"model.onnx": hashlib.sha256(b"model").hexdigest(), "tokenizer.json": hashlib.sha256(b"tok").hexdigest()},
        onnx_file="model.onnx",
        tokenizer_file="tokenizer.json",
        pooling="cls",
        dimensions=4,
        max_tokens=8,
    )
    content = {"model.onnx": b"model", "tokenizer.json": b"tok"}

    def fetch(self, url: str, destination: Path, expected: str, progress) -> None:  # type: ignore[no-untyped-def]
        data = self.content[url.rsplit("/", 1)[1]]
        destination.write_bytes(data)
        if hashlib.sha256(data).hexdigest() != expected:
            raise semantic.SemanticError("does not match its pinned sha256")

    def test_install_checks_every_file_and_marks_the_folder_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tiny-old").mkdir()
            folder = semantic.install_model(self.spec, root, fetch=self.fetch)
            self.assertTrue(semantic.is_installed(self.spec, root))
            self.assertEqual((folder / "model.onnx").read_bytes(), b"model")
            self.assertFalse((root / "tiny-old").exists(), "an earlier version is removed")
            semantic.remove_model(self.spec, root)
            self.assertFalse(semantic.is_installed(self.spec, root))

    def test_a_hash_mismatch_installs_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.content = {**self.content, "tokenizer.json": b"tampered"}
            with self.assertRaises(semantic.SemanticError):
                semantic.install_model(self.spec, root, fetch=self.fetch)
            self.assertFalse(semantic.is_installed(self.spec, root))
            self.assertEqual(list(root.iterdir()), [], "no staging folder or partial install is left")

    def test_only_https_is_downloaded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(semantic.SemanticError):
                semantic._download("http://example.invalid/x", Path(directory) / "x", "0", None)

    def test_checking_for_the_runtime_imports_nothing(self) -> None:
        # Serving a request asks this; importing onnxruntime there can stall
        # for a long time on Windows (see runtime_available).
        import sys

        if "onnxruntime" in sys.modules:
            self.skipTest("onnxruntime was already imported by another test")
        semantic.runtime_available()
        self.assertNotIn("onnxruntime", sys.modules)

    def test_models_live_outside_the_knowledge_base(self) -> None:
        self.assertEqual(semantic.models_root({"KOS_MODELS_DIR": "/m"}), Path("/m"))
        self.assertEqual(
            semantic.models_root({"XDG_CACHE_HOME": "/c"}),
            Path("/c") / "knowledge-os" / "models",
        )


@unittest.skipIf(np is None, "the search extra (numpy) is not installed")
class IndexAndSearchTests(unittest.TestCase):
    def test_update_reuses_unchanged_passages_and_skips_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(Path(directory))
            embedder = FakeEmbedder()
            counts = semantic.update_index(workspace, _documents(workspace), embedder, source_stamp="one")
            self.assertEqual(counts, {"passages": 5, "embedded": 5})
            again = semantic.update_index(workspace, _documents(workspace), embedder, source_stamp="two")
            self.assertEqual(again["embedded"], 0, "nothing changed, nothing is embedded")

            write_record(Path(directory), "knowledge/coffee.md", _metadata("coffee", "Coffee machine"), "Now cleaned on Mondays.\n")
            third = semantic.update_index(workspace, _documents(workspace), embedder)
            self.assertEqual(third["embedded"], 1, "only the edited page is read again")

            # Raw sources stay out of search by meaning, as they stay out of context.
            fake = mock.Mock(metadata={"type": "source", "id": "s", "title": "S"}, body="raw")
            self.assertEqual(semantic._wanted([fake]), [])

    def test_search_finds_by_meaning_and_nothing_for_an_unrelated_query(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(Path(directory))
            embedder = FakeEmbedder()
            semantic.update_index(workspace, _documents(workspace), embedder)
            matches = semantic.search(workspace, "holiday days", embedder)
            self.assertEqual(matches[0].record_id, "leave")
            self.assertEqual(semantic.search(workspace, "kubernetes autoscaling", embedder), [])

    def test_is_current_follows_the_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = _workspace(Path(directory))
            embedder = FakeEmbedder()
            self.assertFalse(semantic.is_current(workspace, SPEC))
            semantic.update_index(workspace, _documents(workspace), embedder, source_stamp=semantic.catalog_stamp(workspace))
            self.assertTrue(semantic.is_current(workspace, SPEC))
            self.assertFalse(semantic.is_current(workspace, semantic.MODEL), "another model's index is not current")


class FuseTests(unittest.TestCase):
    def match(self, record_id: str) -> semantic.Match:
        return semantic.Match(record_id, 0.9, 0.3, f"Title\n{record_id} text")

    def test_an_exact_hit_wins_a_tie_and_both_ranks_highest(self) -> None:
        fused = semantic.fuse(["a", "b"], [self.match("c"), self.match("b")], 10)
        self.assertEqual(fused, [("b", "both"), ("a", "text"), ("c", "meaning")])

    def test_limit_and_snippet(self) -> None:
        self.assertEqual(len(semantic.fuse(["a", "b", "c"], [], 2)), 2)
        self.assertEqual(semantic.passage_snippet("Title\nHeading\nBody text."), "Heading Body text.")
        long = semantic.passage_snippet("T\n" + "word " * 100, limit=30)
        self.assertTrue(long.endswith(" ...") and len(long) <= 34)


@unittest.skipIf(np is None, "the search extra (numpy) is not installed")
class ReaderSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.root = Path(self._directory.name)
        self.workspace = _workspace(self.root)
        self.embedder = FakeEmbedder()
        patches = [
            mock.patch.object(semantic, "_embedder", self.embedder),
            mock.patch.object(semantic, "MODEL", SPEC),
            mock.patch.object(semantic, "is_installed", lambda *args, **kwargs: True),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(self._directory.cleanup)

    def index(self) -> None:
        semantic.update_index(
            self.workspace, _documents(self.workspace), self.embedder, source_stamp=semantic.catalog_stamp(self.workspace)
        )

    def test_rows_found_only_by_meaning_are_labelled_and_exact_hits_stay(self) -> None:
        self.index()
        lib = library.load_library(self.workspace)
        rows = library.search_with_meaning(self.workspace, lib, "holiday")
        self.assertEqual([(row["id"], row["match"]) for row in rows], [("leave", "meaning")])
        self.assertEqual(rows[0]["snippet_is_passage"], "yes")
        rows = library.search_with_meaning(self.workspace, lib, "coffee")
        self.assertEqual(rows[0]["id"], "coffee")
        self.assertIn(rows[0]["match"], {"text", "both"})

    def test_a_model_that_cannot_load_is_reported_not_loaded_forever(self) -> None:
        with mock.patch.object(semantic, "_load_error", "bad model file"):
            status = library.semantic_status(self.workspace)
        self.assertEqual((status.state, status.error), ("failed", "bad model file"))

    def test_without_an_index_it_is_full_text_search(self) -> None:
        lib = library.load_library(self.workspace)
        self.assertEqual(library.search_with_meaning(self.workspace, lib, "holiday"), [])
        self.assertEqual(library.semantic_status(self.workspace).state, "stale")

    def test_the_api_labels_meaning_rows_and_a_get_never_writes_the_index(self) -> None:
        from starlette.testclient import TestClient

        from knowledge_os.reader.app import create_app

        client = TestClient(create_app(self.workspace), base_url="http://127.0.0.1")
        body = client.get("/api/search", params={"q": "holiday"}).json()
        self.assertEqual(body["results"], [])
        self.assertEqual(body["semantic"]["state"], "stale")
        self.assertFalse((self.root / "indexes" / semantic.INDEX_FILE).exists(), "serving a search writes nothing")

        refused = client.post("/api/semantic/refresh", json={})
        self.assertEqual(refused.status_code, 403, "a refresh is a write and needs the token")
        token = client.get("/api/session").json()["write_token"]
        with mock.patch.object(semantic, "refresh_in_background", lambda workspace, load: self.index() or True):
            response = client.post("/api/semantic/refresh", json={}, headers={"X-KOS-Write-Token": token})
        self.assertEqual(response.status_code, 200)

        body = client.get("/api/search", params={"q": "holiday"}).json()
        self.assertEqual(body["semantic"]["state"], "ready")
        [row] = body["results"]
        self.assertEqual((row["id"], row["match"], row["match_label"]), ("leave", "meaning", "Similar in meaning"))
        self.assertNotIn("<mark>", row["snippet_html"])


if __name__ == "__main__":
    unittest.main()
