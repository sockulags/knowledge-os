"""The SPA shell carries a strict Content Security Policy; the JSON API is
unchanged. Runs in-process through Starlette's TestClient, so no port is
bound."""

from __future__ import annotations

import unittest

from starlette.testclient import TestClient

from knowledge_os.reader.app import STATIC_APP_DIR, create_app
from knowledge_os.workspace import Workspace

from reader_support import REPOSITORY


@unittest.skipUnless((STATIC_APP_DIR / "index.html").is_file(), "reader UI is not built")
class SpaContentSecurityPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        app = create_app(Workspace(REPOSITORY), refresh_index=False)
        cls.client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    def test_start_page_and_deep_links_carry_the_policy(self) -> None:
        for path in ("/", "/p/knowledge-os", "/search"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                policy = response.headers.get("content-security-policy", "")
                directives = {part.strip() for part in policy.split(";")}
                for directive in (
                    "default-src 'self'",
                    "script-src 'self'",
                    "object-src 'none'",
                    "base-uri 'none'",
                    "frame-ancestors 'none'",
                ):
                    self.assertIn(directive, directives)
                self.assertNotIn("unsafe-inline", policy)
                self.assertNotIn("unsafe-eval", policy)

    def test_built_shell_has_no_inline_script(self) -> None:
        html = (STATIC_APP_DIR / "index.html").read_text(encoding="utf-8").lower()
        self.assertEqual(html.count("<script"), html.count('<script type="module" crossorigin src="/assets/'))

    def test_json_api_is_unaffected(self) -> None:
        response = self.client.get("/api/this-route-does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers["content-type"], "application/json")
        self.assertNotIn("content-security-policy", response.headers)


if __name__ == "__main__":
    unittest.main()
