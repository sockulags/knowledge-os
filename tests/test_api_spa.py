"""SPA fallback and API-404 tests: every non-``/api`` path resolves to the
built ``index.html`` (so a deep link or a hard refresh works), and every
unmatched ``/api/*`` path answers 404 JSON.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request

from reader_support import REPOSITORY, serve

PORT = 8839


class ApiNotFoundTests(unittest.TestCase):
    def test_unknown_api_route_is_404_json(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            try:
                urllib.request.urlopen(base_url + "/api/this-route-does-not-exist", timeout=5)
                self.fail("expected an HTTPError")
            except urllib.error.HTTPError as exc:
                self.assertEqual(exc.code, 404)
                data = json.loads(exc.read())
                self.assertIn("detail", data)


class SpaFallbackTests(unittest.TestCase):
    """Whether the SPA has been built (``reader-ui``'s ``npm run build``)
    changes what "serves the app" means, but every one of these paths must
    resolve through the app.py fallback route rather than a bare 404, in
    both cases: 200 with index.html when built, 503 with a clear message
    when not (see app.py's ``_spa_index``)."""

    def _check(self, base_url: str, path: str) -> None:
        try:
            with urllib.request.urlopen(base_url + path, timeout=5) as response:
                status = response.status
                body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read()
        self.assertIn(status, (200, 503))
        if status == 200:
            self.assertIn(b"<html", body.lower())
        else:
            self.assertIn(b"not been built", body)

    def test_deep_links_resolve_through_the_fallback(self) -> None:
        with serve(REPOSITORY, PORT) as base_url:
            for path in ("/", "/p/knowledge-os", "/r/openknowledge-pivot", "/search", "/everything", "/nonexistent"):
                with self.subTest(path=path):
                    self._check(base_url, path)


if __name__ == "__main__":
    unittest.main()
