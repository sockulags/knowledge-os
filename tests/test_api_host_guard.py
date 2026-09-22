"""Tests for the loopback ``Host`` guard that wraps every request, not only
writes (see ``knowledge_os/reader/api/write.py:host_guard`` and its
installation in ``app.py``'s ``create_app``).

One real ``kos-read`` server serves one temporary workspace for the whole
class, following the same pattern as ``tests/test_api_write.py``.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path

from reader_support import serve, write_decision_fixture

PORT = 8843


def _get(base_url: str, path: str, *, host: str | None = None) -> tuple[int, object]:
    request = urllib.request.Request(base_url + path, method="GET")
    if host is not None:
        request.add_header("Host", host)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, _maybe_json(body)
    return 200, _maybe_json(body)


def _maybe_json(body: bytes) -> object:
    try:
        return json.loads(body)
    except ValueError:
        return body.decode("utf-8", errors="replace")


class HostGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._stack = ExitStack()
        directory = cls._stack.enter_context(tempfile.TemporaryDirectory())
        cls.root = Path(directory)
        write_decision_fixture(cls.root)
        cls.base_url = cls._stack.enter_context(serve(cls.root, PORT))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stack.close()

    def test_foreign_host_is_refused_on_a_get_api_route(self) -> None:
        status, result = _get(self.base_url, "/api/workspace", host="evil.example")
        self.assertEqual(status, 403, result)
        self.assertEqual(result["error"], "forbidden")

    def test_foreign_host_is_refused_on_the_spa_index(self) -> None:
        status, result = _get(self.base_url, "/", host="evil.example")
        self.assertEqual(status, 403, result)
        self.assertEqual(result["error"], "forbidden")

    def test_loopback_hosts_are_accepted_on_a_get_api_route(self) -> None:
        for host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"):
            with self.subTest(host=host):
                status, result = _get(self.base_url, "/api/workspace", host=host)
                self.assertEqual(status, 200, result)

    def test_loopback_hosts_are_accepted_on_the_spa_route(self) -> None:
        for host in (f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}"):
            with self.subTest(host=host):
                status, _ = _get(self.base_url, "/", host=host)
                # 200 once the frontend is built, 503 with its "not built"
                # plain-text page in a checkout with no `npm run build` --
                # either way, well past the host guard, not 403.
                self.assertIn(status, (200, 503))


if __name__ == "__main__":
    unittest.main()
