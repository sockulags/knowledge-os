"""Page ids made from titles: one rule for the core, the reader and the agent tools."""

from __future__ import annotations

import unittest

from knowledge_os.agent_access.tools import slug
from knowledge_os.model import ID_PATTERN, kebab

TITLES = ["Skärmbild från mötet", "Écrire une Note!", "Retry policy (v2)", "  --x--  ", "a" * 120]


class KebabTests(unittest.TestCase):
    def test_folds_accents_instead_of_splitting_words(self) -> None:
        self.assertEqual(kebab("Skärmbild från mötet"), "skarmbild-fran-motet")
        self.assertEqual(kebab("Écrire une Note!"), "ecrire-une-note")

    def test_limit_and_fallback(self) -> None:
        self.assertEqual(len(kebab("a" * 120)), 80)
        self.assertEqual(kebab("word " * 30, 12), "word-word-wo")
        self.assertEqual(kebab("ab-cd-ef", 3), "ab")
        self.assertEqual(kebab("a" * 120, None), "a" * 120)
        self.assertEqual(kebab("!!!", fallback="note"), "note")

    def test_results_are_valid_ids(self) -> None:
        for title in TITLES:
            self.assertRegex(kebab(title), ID_PATTERN)

    def test_agent_tools_make_the_same_ids(self) -> None:
        for title in TITLES:
            self.assertEqual(slug(title), kebab(title, 80, "note"), title)
        self.assertEqual(slug("???"), "note")


if __name__ == "__main__":
    unittest.main()
