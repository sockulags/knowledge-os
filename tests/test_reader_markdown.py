"""Tests for knowledge_os/reader/markdown.py.

Pure-module tests: no server, no workspace on disk, mostly plain assertions
on rendered HTML strings. Follows the repository's existing convention:
unittest only, no pytest, no fixtures. A handful of tests at the bottom
render the real corpus (docs/architecture.md and its neighbours) to catch
anything a synthetic fixture would miss, using REPOSITORY from
reader_support the same way the other reader tests do.
"""

from __future__ import annotations

import unittest

from reader_support import REPOSITORY

from knowledge_os.reader import markdown


class BackwardCompatibilityTests(unittest.TestCase):
    """render() and headings() keep their original single-positional-arg
    signature; siblings calling them with just a body string must see no
    behaviour change from adding the new keyword-only parameters."""

    def test_render_accepts_a_single_positional_argument(self) -> None:
        html = markdown.render("# Title\n\nSome *text*.")
        self.assertIn("<h1", html)
        self.assertIn("<em>text</em>", html)

    def test_headings_signature_and_return_shape_unchanged(self) -> None:
        result = markdown.headings("# One\n\n## Two\n")
        self.assertEqual(result, [(1, "One", "one"), (2, "Two", "two")])

    def test_render_without_source_path_leaves_relative_links_untouched(self) -> None:
        html = markdown.render("[here](architecture/README.md)")
        self.assertIn('href="architecture/README.md"', html)
        self.assertNotIn("md-link-unresolved", html)

    def test_render_with_source_path_but_no_resolver_leaves_links_untouched(self) -> None:
        html = markdown.render("[here](architecture/README.md)", source_path="projects/demo/README.md")
        self.assertIn('href="architecture/README.md"', html)


class RawHtmlHandlingTests(unittest.TestCase):
    """The corpus uses angle-bracket placeholders (<project-id>, <ROOT>) in
    running prose; they must render as visible, escaped text rather than
    being parsed as unknown HTML tags and silently dropped by a browser."""

    def test_angle_bracket_placeholder_in_prose_is_escaped_not_dropped(self) -> None:
        html = markdown.render("The workspace root is <ROOT> and the id is <project-id>.")
        self.assertIn("&lt;ROOT&gt;", html)
        self.assertIn("&lt;project-id&gt;", html)
        # Never emitted as literal, unescaped angle brackets: an unknown
        # tag would parse in a browser and its "text" would vanish.
        self.assertNotIn("<ROOT>", html)
        self.assertNotIn("<project-id>", html)

    def test_angle_bracket_placeholder_in_inline_code_is_escaped(self) -> None:
        html = markdown.render("Use `<project-id>` as the scope.")
        self.assertIn("<code>&lt;project-id&gt;</code>", html)

    def test_real_autolink_still_renders_as_a_link(self) -> None:
        html = markdown.render("See <https://example.com> for details.")
        self.assertIn('<a href="https://example.com">https://example.com</a>', html)


class CodeHighlightingTests(unittest.TestCase):
    def test_known_language_is_highlighted(self) -> None:
        html = markdown.render('```powershell\nGet-ChildItem -Path .\n```\n')
        self.assertIn('<pre><code class="language-powershell">', html)
        # Pygments emits token spans for a recognised lexer.
        self.assertIn('<span class="', html)
        self.assertIn("Get-ChildItem", html)

    def test_bash_language_is_highlighted(self) -> None:
        html = markdown.render('```bash\necho "hi"\n```\n')
        self.assertIn('<pre><code class="language-bash">', html)
        self.assertIn('<span class="', html)

    def test_text_language_degrades_to_plain_but_does_not_raise(self) -> None:
        html = markdown.render('```text\nplain diagram content\n```\n')
        self.assertIn('<pre><code class="language-text">', html)
        self.assertIn("plain diagram content", html)

    def test_unknown_language_degrades_to_plain_code_block(self) -> None:
        html = markdown.render('```not-a-real-language\nsome content\n```\n')
        self.assertIn('<pre><code class="language-not-a-real-language">', html)
        self.assertIn("some content", html)
        # No pygments highlighting was applied for a language it does not know.
        self.assertNotIn('<span class="', html)

    def test_absent_language_renders_plain_pre_code_with_no_class(self) -> None:
        html = markdown.render('```\nbare fence\n```\n')
        self.assertIn("<pre><code>bare fence", html)
        self.assertNotIn("language-", html)

    def test_code_block_content_is_html_escaped_for_known_and_unknown_languages(self) -> None:
        known = markdown.render('```bash\necho "<value>"\n```\n')
        unknown = markdown.render('```made-up\necho "<value>"\n```\n')
        self.assertIn("&lt;value&gt;", known)
        self.assertIn("&lt;value&gt;", unknown)
        self.assertNotIn("<value>", known)
        self.assertNotIn("<value>", unknown)


class TableTests(unittest.TestCase):
    def test_pipe_table_renders_inside_a_scroll_container(self) -> None:
        table = "| a | b |\n| --- | --- |\n| 1 | 2 |\n"
        html = markdown.render(table)
        self.assertIn('<div class="table-scroll"><table>', html)
        self.assertIn("</table></div>", html)
        self.assertIn("<th>a</th>", html)
        self.assertIn("<td>1</td>", html)


class HeadingAnchorTests(unittest.TestCase):
    def test_single_heading_gets_a_slug_id(self) -> None:
        html = markdown.render("# Getting Started\n")
        self.assertIn('<h1 id="getting-started">Getting Started</h1>', html)

    def test_duplicate_heading_text_gets_numeric_suffixes_not_duplicates(self) -> None:
        doc = "# Foo\n\n## Foo\n\n### Foo\n"
        self.assertEqual(
            markdown.headings(doc),
            [(1, "Foo", "foo"), (2, "Foo", "foo-1"), (3, "Foo", "foo-2")],
        )
        html = markdown.render(doc)
        self.assertIn('<h1 id="foo">', html)
        self.assertIn('<h2 id="foo-1">', html)
        self.assertIn('<h3 id="foo-2">', html)

    def test_rendered_ids_match_headings_anchors_for_the_same_document(self) -> None:
        doc = "# A\n\nSome text.\n\n## B\n\ntext\n\n## B\n"
        expected_anchors = [anchor for _level, _text, anchor in markdown.headings(doc)]
        html = markdown.render(doc)
        rendered_ids = [anchor for anchor in expected_anchors if f'id="{anchor}"' in html]
        self.assertEqual(rendered_ids, expected_anchors)

    def test_two_level_heading_structure_preserves_levels_and_order(self) -> None:
        doc = "# Top\n\n## One\n\n### One A\n\n## Two\n"
        self.assertEqual(
            markdown.headings(doc),
            [(1, "Top", "top"), (2, "One", "one"), (3, "One A", "one-a"), (2, "Two", "two")],
        )

    def test_heading_text_flattens_inline_markup_for_the_anchor(self) -> None:
        result = markdown.headings("## The `kos lint` command\n")
        self.assertEqual(result, [(2, "The kos lint command", "the-kos-lint-command")])


class RelativeLinkResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path_to_id = {
            "projects/knowledge-os/architecture/README.md": "knowledge-os-architecture",
            "projects/knowledge-os/operations/README.md": "knowledge-os-operations",
            "projects/knowledge-os/decisions/openknowledge-pivot.md": "openknowledge-pivot",
        }

    def test_sibling_relative_link_resolves_to_a_permalink(self) -> None:
        html = markdown.render(
            "[Architecture](architecture/README.md)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn('<a href="/r/knowledge-os-architecture">Architecture</a>', html)

    def test_parent_relative_link_resolves_to_a_permalink(self) -> None:
        html = markdown.render(
            "[pivot](../decisions/openknowledge-pivot.md)",
            source_path="projects/knowledge-os/architecture/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn('<a href="/r/openknowledge-pivot">pivot</a>', html)

    def test_bare_directory_link_degrades_to_harmless_non_link_text(self) -> None:
        html = markdown.render(
            "[Decisions](decisions/)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertNotIn("<a ", html)
        self.assertNotIn('href="decisions/"', html)
        self.assertIn('<span class="md-link-unresolved"', html)
        self.assertIn(">Decisions</span>", html)

    def test_link_outside_the_corpus_degrades_to_harmless_non_link_text(self) -> None:
        html = markdown.render(
            "[elsewhere](../../outside/nowhere.md)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertNotIn("<a ", html)
        self.assertIn("md-link-unresolved", html)

    def test_absolute_url_is_never_looked_up_or_rewritten(self) -> None:
        html = markdown.render(
            "[ext](https://example.com/path)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn('<a href="https://example.com/path">ext</a>', html)

    def test_fragment_only_link_is_never_looked_up_or_rewritten(self) -> None:
        html = markdown.render(
            "[jump](#somewhere)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn('<a href="#somewhere">jump</a>', html)

    def test_fragment_on_a_resolved_link_is_preserved(self) -> None:
        html = markdown.render(
            "[section](architecture/README.md#overview)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn('<a href="/r/knowledge-os-architecture#overview">section</a>', html)

    def test_text_around_an_unresolved_link_is_unaffected(self) -> None:
        html = markdown.render(
            "before [Decisions](decisions/) after",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn("before ", html)
        self.assertIn(" after", html)

    def test_resolver_exception_degrades_to_unresolved_instead_of_raising(self) -> None:
        def _boom(_path: str) -> str | None:
            raise RuntimeError("lookup failed")

        html = markdown.render(
            "[x](somewhere/else.md)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=_boom,
        )
        self.assertIn("md-link-unresolved", html)
        self.assertNotIn("<a ", html)

    def test_multiple_links_in_one_paragraph_are_resolved_independently(self) -> None:
        html = markdown.render(
            "[ok](architecture/README.md) then [broken](decisions/) then [ok2](operations/README.md)",
            source_path="projects/knowledge-os/README.md",
            resolve_link=self.path_to_id.get,
        )
        self.assertIn('<a href="/r/knowledge-os-architecture">ok</a>', html)
        self.assertIn('<span class="md-link-unresolved" title="', html)
        self.assertIn(">broken</span>", html)
        self.assertIn('<a href="/r/knowledge-os-operations">ok2</a>', html)


class RealCorpusSmokeTests(unittest.TestCase):
    """Render the actual, harder documents in this repository. These are
    the cases called out in the unit brief: docs/architecture.md (10 flat
    ## headings) and docs/architecture-audit-v0.1.md (52 headings, the
    harder anchor-collision case)."""

    def test_architecture_doc_renders_without_raising_and_has_ten_headings(self) -> None:
        text = (REPOSITORY / "docs" / "architecture.md").read_text(encoding="utf-8")
        html = markdown.render(text)
        self.assertTrue(html)
        self.assertEqual(len(markdown.headings(text)), 10)

    def test_architecture_audit_doc_renders_without_raising_and_anchors_are_unique(self) -> None:
        text = (REPOSITORY / "docs" / "architecture-audit-v0.1.md").read_text(encoding="utf-8")
        html = markdown.render(text)
        self.assertTrue(html)
        heads = markdown.headings(text)
        self.assertEqual(len(heads), 52)
        anchors = [anchor for _level, _text, anchor in heads]
        self.assertEqual(len(anchors), len(set(anchors)))

    def test_two_level_operations_doc_preserves_h2_h3_nesting(self) -> None:
        text = (REPOSITORY / "projects" / "knowledge-os" / "operations" / "knowledge-os-cli.md").read_text(
            encoding="utf-8"
        )
        heads = markdown.headings(text)
        levels = {level for level, _text, _anchor in heads}
        self.assertTrue({2, 3}.issubset(levels))
        markdown.render(text)  # must not raise

    def test_project_readme_relative_links_resolve_against_the_real_corpus(self) -> None:
        readme_path = REPOSITORY / "projects" / "knowledge-os" / "README.md"
        text = readme_path.read_text(encoding="utf-8")
        path_to_id = {
            "projects/knowledge-os/architecture/README.md": "knowledge-os-architecture",
            "projects/knowledge-os/operations/README.md": "knowledge-os-operations",
            "projects/knowledge-os/decisions/openknowledge-pivot.md": "openknowledge-pivot",
        }
        html = markdown.render(
            text,
            source_path="projects/knowledge-os/README.md",
            resolve_link=path_to_id.get,
        )
        self.assertIn('<a href="/r/knowledge-os-architecture">', html)
        self.assertIn('<a href="/r/knowledge-os-operations">', html)
        self.assertIn('<a href="/r/openknowledge-pivot">', html)
        # The bare "decisions/" directory link has no record at that exact
        # path and must degrade, not 404.
        self.assertIn("md-link-unresolved", html)
        self.assertNotIn('href="decisions/"', html)


if __name__ == "__main__":
    unittest.main()
