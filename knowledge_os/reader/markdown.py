"""Baseline Markdown rendering.

A working minimum so stage-B views are not blocked; a later unit upgrades
this with syntax highlighting. Renders through markdown-it-py's token stream
rather than line regexes so that headings inside fenced code blocks are not
mistaken for real headings, and so inline markup (` `code` `, emphasis) in a
heading's text is flattened correctly for anchors and tables of contents.

Raw HTML in the source is escaped, not executed (the ``html=False`` default),
which is appropriate for local Markdown of unknown provenance.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

_md = MarkdownIt("commonmark").enable("table")

_ANCHOR_STRIP = re.compile(r"[^a-z0-9]+")


def render(md: str) -> str:
    """Render Markdown to an HTML fragment (tables enabled, raw HTML escaped)."""

    return _md.render(md)


def _plain_text(inline_token: Token) -> str:
    """Flatten an inline token's children to visible text, dropping markup."""

    if inline_token.children is None:
        return inline_token.content
    parts: list[str] = []
    for child in inline_token.children:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts)


def _slugify(text: str, seen: dict[str, int]) -> str:
    slug = _ANCHOR_STRIP.sub("-", text.strip().lower()).strip("-") or "section"
    count = seen.get(slug, 0)
    seen[slug] = count + 1
    if count:
        slug = f"{slug}-{count}"
    return slug


def headings(md: str) -> list[tuple[int, str, str]]:
    """Return ``(level, text, anchor)`` for every heading, in document order.

    Anchors are deterministic and unique within one document (a repeated
    heading text gets a ``-1``, ``-2``, ... suffix), so a document's table of
    contents can link to them and the document renderer can be upgraded
    later to emit matching ``id`` attributes without changing this contract.
    """

    tokens = _md.parse(md)
    seen: dict[str, int] = {}
    result: list[tuple[int, str, str]] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1:])
        text = _plain_text(tokens[index + 1]).strip()
        result.append((level, text, _slugify(text, seen)))
    return result
