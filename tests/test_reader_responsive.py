"""The reader keeps answering while another kos operation holds the
workspace lock (a sync's merge and push, say).

The test process holds ``workspace_mutation_lock`` itself, which is a file
lock shared across processes, while a real ``kos-read`` server serves the
workspace. A save sent in that time must wait for the lock on a worker
thread, not on the server's event loop, so reads keep answering and the save
succeeds once the lock is released.
"""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path

from reader_support import serve, write_decision_fixture

from knowledge_os.workspace import Workspace, workspace_mutation_lock

TOKEN_HEADER = "X-KOS-Write-Token"
#: The acceptance bound for a read while the lock is held.
READ_BUDGET_SECONDS = 0.25


def _request(base_url: str, method: str, path: str, payload: object | None = None, token: str | None = None):
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(base_url + path, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header(TOKEN_HEADER, token)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


class ResponsiveWhileLockedTests(unittest.TestCase):
    def setUp(self) -> None:
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.root = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        write_decision_fixture(self.root)
        self.base_url = stack.enter_context(serve(self.root))
        status, session = _request(self.base_url, "GET", "/api/session")
        self.assertEqual(status, 200, session)
        self.token = session["write_token"]
        # Warm up: the first request pays for imports and the first corpus load.
        self.assertEqual(_request(self.base_url, "GET", "/api/home")[0], 200)

    def _timed_home(self) -> float:
        started = time.perf_counter()
        status, _body = _request(self.base_url, "GET", "/api/home")
        elapsed = time.perf_counter() - started
        self.assertEqual(status, 200)
        return elapsed

    def test_reads_answer_and_a_save_waits_while_the_lock_is_held(self) -> None:
        answers: list[tuple[int, dict]] = []
        metadata = {
            "id": "saved-while-locked",
            "title": "Saved while locked",
            "type": "knowledge",
            "status": "active",
            "scope": "general",
            "provenance": [{"kind": "user-authored", "reference": "test:saved-while-locked"}],
        }

        def save() -> None:
            answers.append(
                _request(self.base_url, "POST", "/api/records", {"metadata": metadata, "body": "Body.\n"}, self.token)
            )

        with workspace_mutation_lock(Workspace(self.root)):
            saver = threading.Thread(target=save)
            saver.start()
            time.sleep(0.5)  # the save is now waiting for the lock inside the server
            timings = [self._timed_home() for _ in range(5)]
            self.assertTrue(saver.is_alive(), "the save finished while the lock was still held")
            self.assertEqual(answers, [])
        saver.join(timeout=30)
        self.assertFalse(saver.is_alive())

        self.assertLess(sorted(timings)[len(timings) // 2], READ_BUDGET_SECONDS, timings)
        self.assertLess(max(timings), 2.0, timings)
        ((status, body),) = answers
        self.assertEqual(status, 201, body)
        self.assertEqual(body["id"], "saved-while-locked")
        self.assertTrue((self.root / body["path"]).is_file())


if __name__ == "__main__":
    unittest.main()
