"""Images and files attached to pages (issue #85): storing them in the page's
``assets/`` folder, moving and deleting them with the page, and the
``POST /api/attachments`` and ``GET /api/files/...`` routes."""

from __future__ import annotations

import base64
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from test_api_write import TOKEN_HEADER, _request
from test_structure import PROVENANCE, StructureTestCase, body_of, write_page

from knowledge_os.attachments import AttachmentError, add_attachment, clean_filename
from knowledge_os.init_workspace import init_workspace
from knowledge_os.structure import (
    StructureError,
    create_folder,
    create_project,
    delete_record,
    move_record,
    plan_page_deletion,
)
from knowledge_os.workspace import Workspace
from reader_support import serve

PORT = 8882
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class AddAttachmentTests(StructureTestCase):
    def test_names_are_cleaned_and_never_overwritten(self) -> None:
        self.assertEqual(clean_filename("Skärmbild 2026-09-27 kl. 10.03.PNG"), "skarmbild-2026-09-27-kl-10-03.png")
        self.assertEqual(clean_filename("../../etc/passwd"), "passwd")
        self.assertEqual(clean_filename(".hidden"), "hidden")

        first = add_attachment(self.workspace, "projects/acme/notes", "Diagram.png", PNG)
        self.assertEqual((first.path, first.link, first.created), ("projects/acme/notes/assets/diagram.png", "assets/diagram.png", True))
        again = add_attachment(self.workspace, "projects/acme/notes", "other-name.png", PNG)
        self.assertEqual((again.path, again.created), (first.path, False))
        different = add_attachment(self.workspace, "projects/acme/notes", "diagram.png", PNG + b"x")
        self.assertEqual(different.path, "projects/acme/notes/assets/diagram-2.png")
        self.assertEqual((self.root / first.path).read_bytes(), PNG)
        self.assert_valid()

    def test_refusals_write_nothing(self) -> None:
        cases = [
            ("projects/acme/notes", "page.md", PNG),  # Markdown would become a record
            ("projects/acme/notes", "empty.png", b""),
            ("projects/acme/missing", "x.png", PNG),
            ("projects", "x.png", PNG),
            ("sources", "x.png", PNG),
            ("projects/acme/../beta", "x.png", PNG),
            ("projects/acme/notes/assets", "x.png", PNG),
        ]
        for directory, name, data in cases:
            with self.subTest(directory=directory, name=name):
                with self.assertRaises(AttachmentError):
                    add_attachment(self.workspace, directory, name, data)
        self.assertFalse((self.root / "projects/acme/notes/assets").exists())

    def test_the_assets_folder_name_is_kept_for_attachments(self) -> None:
        with self.assertRaises(StructureError):
            create_folder(self.workspace, "acme", "assets", title="Assets", provenance=PROVENANCE)


class MoveAndDeleteTests(StructureTestCase):
    def setUp(self) -> None:
        super().setUp()
        add_attachment(self.workspace, "projects/acme/notes", "own.png", PNG)
        add_attachment(self.workspace, "projects/acme/notes", "shared.png", PNG + b"shared")
        write_page(
            self.root,
            "projects/acme/notes/report.md",
            "report",
            "project:acme",
            "![own](assets/own.png) and ![shared](assets/shared.png)\n",
        )
        write_page(self.root, "projects/acme/notes/other.md", "other", "project:acme", "Also ![shared](assets/shared.png)\n")
        self.assert_valid()

    def test_a_moved_page_takes_its_own_attachments_and_leaves_shared_ones(self) -> None:
        result = move_record(self.workspace, "report", expected_sha256=self.sha("projects/acme/notes/report.md"), folder="archive")

        self.assertFalse((self.root / "projects/acme/notes/assets/own.png").exists())
        self.assertEqual((self.root / "projects/acme/archive/assets/own.png").read_bytes(), PNG)
        self.assertTrue((self.root / "projects/acme/notes/assets/shared.png").exists())
        body = body_of(self.root / "projects/acme/archive/report.md")
        self.assertIn("![own](assets/own.png)", body)
        self.assertIn("![shared](../notes/assets/shared.png)", body)
        self.assertIn("projects/acme/notes/assets/own.png", result.touched)
        self.assertIn("projects/acme/archive/assets/own.png", result.touched)
        moved = next(item for item in result.changed if item.path == "projects/acme/archive/assets/own.png")
        self.assertEqual((moved.old_path, moved.id), ("projects/acme/notes/assets/own.png", None))
        self.assert_valid()
        self.assert_links_resolve()

    def test_a_move_across_projects_takes_attachments_and_an_identical_file_is_reused(self) -> None:
        add_attachment(self.workspace, "projects/beta", "own.png", PNG)
        move_record(
            self.workspace,
            "report",
            expected_sha256=self.sha("projects/acme/notes/report.md"),
            folder="",
            project="beta",
            allow_scope_change=True,
        )
        self.assertFalse((self.root / "projects/acme/notes/assets/own.png").exists())
        self.assertFalse((self.root / "projects/beta/assets/own-2.png").exists())
        self.assertIn("![own](assets/own.png)", body_of(self.root / "projects/beta/report.md"))
        self.assert_valid()
        self.assert_links_resolve()

    def test_emptied_assets_folder_is_removed(self) -> None:
        plan = plan_page_deletion(self.workspace, "other")
        self.assertEqual((plan.attachments, plan.kept_attachments), ((), ("projects/acme/notes/assets/shared.png",)))
        delete_record(self.workspace, "other", expected_sha256=self.sha("projects/acme/notes/other.md"))
        move_record(self.workspace, "report", expected_sha256=self.sha("projects/acme/notes/report.md"), folder="archive")
        self.assertFalse((self.root / "projects/acme/notes/assets").exists())
        self.assertEqual(
            sorted(path.name for path in (self.root / "projects/acme/archive/assets").iterdir()), ["own.png", "shared.png"]
        )

    def test_deleting_a_page_deletes_only_its_own_attachments(self) -> None:
        plan = plan_page_deletion(self.workspace, "report")
        self.assertEqual(plan.attachments, ("projects/acme/notes/assets/own.png",))
        self.assertEqual(plan.kept_attachments, ("projects/acme/notes/assets/shared.png",))
        self.assertIn("projects/acme/notes/assets/own.png", plan.expected)

        result = delete_record(
            self.workspace, "report", expected_sha256=self.sha("projects/acme/notes/report.md"), expected=plan.expected
        )
        self.assertIn("projects/acme/notes/assets/own.png", result.deleted)
        self.assertFalse((self.root / "projects/acme/notes/assets/own.png").exists())
        self.assertTrue((self.root / "projects/acme/notes/assets/shared.png").exists())
        self.assert_valid()


class AttachmentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory()
        cls.root = init_workspace(Path(cls._temp.name) / "kb")
        workspace = Workspace(cls.root)
        create_project(workspace, "demo", title="Demo", provenance=PROVENANCE)
        create_folder(workspace, "demo", "notes", title="Notes", provenance=PROVENANCE)
        write_page(cls.root, "projects/demo/notes/page.md", "page", "project:demo", "Text.\n")
        cls._server = serve(cls.root, PORT)
        cls.base_url = cls._server.__enter__()
        status, session = _request(cls.base_url, "GET", "/api/session")
        assert status == 200, session
        cls.token = session["write_token"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._server.__exit__(None, None, None)
        cls._temp.cleanup()

    def attach(self, payload: dict) -> tuple[int, dict]:
        return _request(self.base_url, "POST", "/api/attachments", payload, headers={TOKEN_HEADER: self.token})

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        try:
            with urllib.request.urlopen(self.base_url + path, timeout=10) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers), exc.read()

    def test_attach_to_a_page_then_render_and_serve_it(self) -> None:
        status, result = self.attach(
            {"record_id": "page", "filename": "Chart.png", "data_base64": base64.b64encode(PNG).decode()}
        )
        self.assertEqual(status, 201, result)
        self.assertEqual(result["path"], "projects/demo/notes/assets/chart.png")
        self.assertEqual(result["markdown"], "![chart](assets/chart.png)")
        self.assertEqual(result["url"], "/api/files/projects/demo/notes/assets/chart.png")
        self.assertTrue(result["image"])

        status, headers, content = self.get(result["url"])
        self.assertEqual((status, content), (200, PNG))
        self.assertEqual(headers["content-type"], "image/png")
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertIn("sandbox", headers["content-security-policy"])

        status, preview = _request(
            self.base_url,
            "POST",
            "/api/preview",
            {"body": "![chart](assets/chart.png) [data](assets/missing.csv)", "path": "projects/demo/notes/page.md"},
            headers={TOKEN_HEADER: self.token},
        )
        self.assertEqual(status, 200, preview)
        self.assertIn('src="/api/files/projects/demo/notes/assets/chart.png"', preview["html"])
        self.assertIn("md-link-unresolved", preview["html"])

    def test_a_file_for_a_new_page_goes_to_its_folder_and_downloads(self) -> None:
        status, result = self.attach(
            {"project": "demo", "folder": "notes", "filename": "data.csv", "data_base64": base64.b64encode(b"a,b\n").decode()}
        )
        self.assertEqual(status, 201, result)
        self.assertEqual(result["markdown"], "[data.csv](assets/data.csv)")
        status, headers, _content = self.get(result["url"])
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["content-disposition"])

        status, record = _request(self.base_url, "GET", "/api/records/demo-notes")
        self.assertEqual(status, 200)

    def test_only_attachments_are_served(self) -> None:
        for path in (
            "/api/files/projects/demo/notes/page.md",
            "/api/files/knowledge-os.toml",
            "/api/files/projects/demo/notes/assets/../page.md",
            "/api/files/projects/demo/notes/assets/nothing.png",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 404)

    def test_refusals(self) -> None:
        cases = [
            ({"record_id": "page", "filename": "x.png", "data_base64": "not base64!"}, 400),
            ({"record_id": "nope", "filename": "x.png", "data_base64": "eA=="}, 404),
            ({"project": "nope", "filename": "x.png", "data_base64": "eA=="}, 404),
            ({"filename": "x.png", "data_base64": "eA=="}, 400),
            ({"record_id": "page", "filename": "notes.md", "data_base64": "eA=="}, 422),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                status, result = self.attach(payload)
                self.assertEqual(status, expected, result)
        status, _result = _request(
            self.base_url, "POST", "/api/attachments", {"record_id": "page", "filename": "x.png", "data_base64": "eA=="}
        )
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
