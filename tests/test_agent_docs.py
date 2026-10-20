from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"\bv?\d+\.\d+\.\d+\b")


class AgentDocumentationTests(unittest.TestCase):
    def test_system_summary_names_no_package_version(self) -> None:
        # The version lives in pyproject.toml only, so the summary cannot go stale.
        text = (ROOT / "SYSTEM.md").read_text(encoding="utf-8")
        self.assertIsNone(VERSION.search(text))
        self.assertIn("pyproject.toml", text)

    def test_architecture_title_names_no_version(self) -> None:
        title = (ROOT / "docs" / "architecture.md").read_text(encoding="utf-8").splitlines()[0]
        self.assertIsNone(VERSION.search(title))

    def test_agent_entry_files_stay_short(self) -> None:
        lines = sum(
            len((ROOT / name).read_text(encoding="utf-8").splitlines()) for name in ("AGENTS.md", "SYSTEM.md")
        )
        self.assertLess(lines, 120)


if __name__ == "__main__":
    unittest.main()
