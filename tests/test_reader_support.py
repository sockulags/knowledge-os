"""``reader_support.serve``: each server gets its own free port, so test
modules that run at the same time never reach each other's servers."""

from __future__ import annotations

import json
import tempfile
import unittest
import urllib.request
from contextlib import ExitStack
from pathlib import Path

from reader_support import create_workspace, serve


def _workspace_name(base_url: str) -> str:
    with urllib.request.urlopen(base_url + "/api/workspace", timeout=5) as response:
        return json.load(response)["name"]


class ServeTests(unittest.TestCase):
    def test_two_servers_at_once_each_answer_for_their_own_workspace(self) -> None:
        with ExitStack() as stack:
            directory = Path(stack.enter_context(tempfile.TemporaryDirectory()))
            urls = {}
            for name in ("first-kb", "second-kb"):
                root = directory / name
                root.mkdir()
                create_workspace(root, name=name)
                urls[name] = stack.enter_context(serve(root))
            self.assertNotEqual(urls["first-kb"], urls["second-kb"])
            for name, base_url in urls.items():
                with self.subTest(name=name):
                    self.assertEqual(_workspace_name(base_url), name)


if __name__ == "__main__":
    unittest.main()
