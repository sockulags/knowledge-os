"""The frozen core's entry point (desktop/core/kos_core.py) accepts the same
arguments the desktop shell passes to a Python interpreter, including the
``-P`` of the in-app agent's ``kos mcp``."""

from __future__ import annotations

import importlib.util
import io
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ENTRY = Path(__file__).resolve().parents[1] / "desktop" / "core" / "kos_core.py"


def load_entry():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("kos_core_entry", ENTRY)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KosCoreEntryTests(unittest.TestCase):
    def test_runs_the_cli_with_and_without_a_leading_P(self) -> None:
        entry = load_entry()
        for argv in (["-m", "knowledge_os", "mcp", "--place", "Knowledge OS app"], ["-P", "-m", "knowledge_os", "mcp", "--place", "Knowledge OS app"]):
            with self.subTest(argv=argv), patch("knowledge_os.cli.main", return_value=0) as cli:
                self.assertEqual(entry.main(argv), 0)
                cli.assert_called_once_with(["mcp", "--place", "Knowledge OS app"])

    def test_refuses_anything_else(self) -> None:
        entry = load_entry()
        for argv in ([], ["-P"], ["-c", "print(1)"], ["-m", "os"], ["-P", "-P", "-m", "knowledge_os"]):
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()):
                self.assertEqual(entry.main(argv), 2)

    def test_the_shell_passes_what_the_entry_accepts(self) -> None:
        service = (ENTRY.parents[1] / "src" / "main" / "agents" / "service.ts").read_text(encoding="utf-8")
        self.assertIn("args: ['-P', '-m', 'knowledge_os', 'mcp', '--place', IN_APP_PLACE]", service)


if __name__ == "__main__":
    unittest.main()
