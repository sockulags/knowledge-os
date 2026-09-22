"""``kos-read --exit-on-stdin-eof``: the server stops when its launching
parent closes (or loses) the stdin pipe, which is how the desktop shell
avoids orphaned Python processes after a crash."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from reader_support import REPOSITORY

from knowledge_os.init_workspace import init_workspace

#: This module's own end-to-end port, distinct from every other reader test
#: module's fixed port.
LIFELINE_PORT = 8841


class StdinLifelineTests(unittest.TestCase):
    def test_reader_exits_when_its_stdin_closes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = init_workspace(Path(tmp) / "lifeline-kb")
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "knowledge_os.reader",
                    "--root",
                    str(root),
                    "--port",
                    str(LIFELINE_PORT),
                    "--exit-on-stdin-eof",
                ],
                env=environment,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 15
                while True:
                    self.assertIsNone(process.poll(), "kos-read exited before serving")
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{LIFELINE_PORT}/api/workspace", timeout=1).close()
                        break
                    except (urllib.error.URLError, ConnectionError, TimeoutError):
                        self.assertLess(time.monotonic(), deadline, "kos-read did not start serving")
                        time.sleep(0.1)
                assert process.stdin is not None
                process.stdin.close()
                self.assertEqual(process.wait(timeout=10), 0)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
