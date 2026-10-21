"""``kos`` writes UTF-8 to redirected streams regardless of the console code page.

On Windows a piped stdout defaults to cp1252 unless PYTHONUTF8 or
PYTHONIOENCODING is set, which agents and skills calling ``kos`` do not do.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
FIXTURE = REPOSITORY / "examples" / "context-workspace"
TITLE = "Arrow → ✓ 漢字 zebra"


def run_kos(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in {"PYTHONUTF8", "PYTHONIOENCODING"}
    }
    environment["PYTHONPATH"] = str(REPOSITORY) + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "knowledge_os", *arguments],
        cwd=workspace,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=False,
    )


class RedirectedOutputEncodingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name) / "workspace"
        shutil.copytree(FIXTURE, cls.root, ignore=shutil.ignore_patterns("indexes"))
        record = cls.root / "knowledge" / "irrelevant-general.md"
        text = record.read_text(encoding="utf-8")
        record.write_text(text.replace("title: Office plant care", f"title: {TITLE}"), encoding="utf-8")
        indexed = run_kos(cls.root, "index")
        if indexed.returncode:
            raise AssertionError(indexed.stderr.decode("utf-8", "replace"))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def assert_succeeds(self, *arguments: str) -> str:
        result = run_kos(self.root, *arguments)
        stderr = result.stderr.decode("utf-8", "replace")
        self.assertEqual(result.returncode, 0, stderr)
        return result.stdout.decode("utf-8")

    def test_search_writes_title_as_utf8(self) -> None:
        self.assertIn(TITLE, self.assert_succeeds("search", "zebra"))

    def test_search_json_writes_title_as_utf8(self) -> None:
        output = self.assert_succeeds("search", "zebra", "--json")
        self.assertIn(TITLE, output)
        self.assertIn(TITLE, json.dumps(json.loads(output), ensure_ascii=False))

    def test_inspect_writes_title_as_utf8(self) -> None:
        self.assertIn(TITLE, self.assert_succeeds("inspect", "irrelevant-general"))

    def test_inspect_full_writes_title_as_utf8(self) -> None:
        self.assertIn(TITLE, self.assert_succeeds("inspect", "irrelevant-general", "--full"))


if __name__ == "__main__":
    unittest.main()
