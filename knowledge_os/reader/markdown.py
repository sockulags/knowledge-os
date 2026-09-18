"""Markdown rendering for the reader: highlighting, tables, anchors, links.

Renders through markdown-it-py's token stream rather than line regexes so
that headings inside fenced code blocks are not mistaken for real headings,
and so inline markup (` `code` `, emphasis) in a heading's text is flattened
correctly for anchors and tables of contents.

Raw HTML in the source is escaped, not executed, via an explicit
``html=False``: the "commonmark" preset otherwise leaves raw HTML enabled
(CommonMark itself permits it), which would parse an angle-bracket
placeholder in running prose (``<project-id>``, ``<ROOT>``) as an unknown
tag and silently drop it from the rendered page. The corpus is local and
trusted, but the placeholders still need to stay visible text, not vanish.

Four upgrades over the original baseline, all additive:

* Raw HTML is explicitly disabled (see above) so a placeholder like
  ``<project-id>`` renders as escaped, visible text.

* Fenced code blocks are highlighted server-side with Pygments. An absent
  or unrecognised language degrades to a plain escaped code block (the
  original baseline behaviour) instead of raising.
* Pipe tables render inside a ``.table-scroll`` wrapper (see
  ``static/views/markdown.css``) so a wide table scrolls within its own
  box rather than widening the reading column.
* Headings get stable, unique ``id`` attributes (via the same slugify
  logic ``headings()`` already used), and an optional ``source_path`` /
  ``resolve_link`` pair lets a caller rewrite a relative record-to-record
  link (``architecture/README.md``) into a ``/r/<record-id>`` permalink.
  A link ``resolve_link`` cannot place (a bare directory, a path outside
  the corpus) degrades to plain, non-clickable text rather than a link
  that would 404.

``render()`` and ``headings()`` keep their original positional signature;
the new behaviour is opt-in through keyword-only parameters, so every
existing call site (``render(body)``, ``markdown.render`` as a Jinja
filter) keeps working unchanged.
"""

from __future__ import annotations

import posixpath
import re
from typing import Callable, Iterator

from markdown_it import MarkdownIt
from markdown_it.token import Token
from pygments import highlight as _pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from . import strings

#: A caller-supplied lookup from a normalized, workspace-relative POSIX path
#: (the target of a relative link, resolved against ``source_path``) to a
#: record id, or ``None`` when nothing lives at that path. A plain dict's
#: ``.get`` method already satisfies this signature.
ResolveLink = Callable[[str], "str | None"]

_ANCHOR_STRIP = re.compile(r"[^a-z0-9]+")

#: A link is left untouched (never looked up as a relative record path) when
#: it carries a URI scheme (``https:``, ``mailto:``, ...), is protocol-
#: relative (``//...``), or is a same-page fragment (``#section``).
_EXTERNAL_LINK = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")

#: nowrap=True yields bare `<span class="...">` tokens with no surrounding
#: `<div>/<pre>`; markdown-it-py's own fence renderer supplies the `<pre>
#: <code class="language-...">` wrapper (see `_highlight_code` below), so
#: highlighted and plain fences share identical surrounding markup.
_FORMATTER = HtmlFormatter(nowrap=True)


def _highlight_code(code: str, lang: str, _attrs: str) -> str:
    """``highlight`` hook for markdown-it-py's fence renderer.

    Returning ``""`` (falsy) makes markdown-it-py fall back to its own
    plain, HTML-escaped ``<pre><code>`` rendering — the same path taken for
    a fence with no language at all — so an absent or unrecognised
    language degrades to a plain, readable code block instead of raising.
    """

    if not lang:
        return ""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""
    return _pygments_highlight(code, lexer, _FORMATTER)


def _render_table_open(_tokens: list[Token], _idx: int, _options: object, _env: object) -> str:
    return '<div class="table-scroll"><table>\n'


def _render_table_close(_tokens: list[Token], _idx: int, _options: object, _env: object) -> str:
    return "</table></div>\n"


#: The "commonmark" preset otherwise leaves ``html: True`` (CommonMark
#: itself permits raw HTML passthrough); explicitly disabling it is what
#: makes an angle-bracket placeholder in running prose (``<project-id>``,
#: ``<ROOT>``) render as visible, escaped text (``&lt;project-id&gt;``)
#: instead of being parsed as an unknown tag and silently dropped by the
#: browser. A real autolink (``<https://example.com>``) is a separate
#: CommonMark construct and still renders as a link either way.
_md = MarkdownIt("commonmark", {"highlight": _highlight_code, "html": False}).enable("table")
_md.renderer.rules["table_open"] = _render_table_open
_md.renderer.rules["table_close"] = _render_table_close


def render(md: str, *, source_path: str | None = None, resolve_link: ResolveLink | None = None) -> str:
    """Render Markdown to an HTML fragment.

    ``source_path`` (the rendered record's own workspace-relative POSIX
    path) and ``resolve_link`` are optional and keyword-only. Passing both
    rewrites every relative link into a ``/r/<record-id>`` permalink when
    ``resolve_link`` recognises the link's target path once resolved
    against ``source_path``'s directory; passing neither (the default)
    leaves links exactly as authored, matching the original baseline.
    """

    tokens = _md.parse(md)
    _assign_heading_ids(tokens)
    if source_path is not None and resolve_link is not None:
        _rewrite_relative_links(tokens, source_path, resolve_link)
    return _md.renderer.render(tokens, _md.options, {})


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


def _iter_headings(tokens: list[Token]) -> Iterator[tuple[Token, int, str]]:
    """Yield ``(heading_open token, level, text)`` for every heading.

    Shared by ``headings()`` and the render-time id-assignment pass so both
    walk the same tokens in the same order with the same text extraction;
    given the same document, they produce the same anchor sequence.
    """

    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        level = int(token.tag[1:])
        text = _plain_text(tokens[index + 1]).strip()
        yield token, level, text


def _assign_heading_ids(tokens: list[Token]) -> None:
    seen: dict[str, int] = {}
    for token, _level, text in _iter_headings(tokens):
        token.attrSet("id", _slugify(text, seen))


def headings(md: str) -> list[tuple[int, str, str]]:
    """Return ``(level, text, anchor)`` for every heading, in document order.

    Anchors are deterministic and unique within one document (a repeated
    heading text gets a ``-1``, ``-2``, ... suffix), matching the ``id``
    attributes ``render()`` assigns to the same document's rendered
    headings, so a table of contents can link straight into the reading
    column.
    """

    tokens = _md.parse(md)
    seen: dict[str, int] = {}
    return [(level, text, _slugify(text, seen)) for _, level, text in _iter_headings(tokens)]


def _resolve_link_target(source_path: str, href: str) -> tuple[str, str]:
    """Split a relative href into its lookup path and any ``#fragment``.

    The lookup path is normalized against the directory containing
    ``source_path`` using pure string manipulation (``posixpath``, no
    filesystem access): ``../decisions/x.md`` from
    ``projects/knowledge-os/architecture/README.md`` becomes
    ``projects/knowledge-os/decisions/x.md``; a bare directory reference
    (``decisions/``) normalizes to ``projects/knowledge-os/decisions``,
    which will not match any record's file path and so is correctly left
    unresolved.
    """

    path, _, fragment = href.partition("#")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), path))
    return target, fragment


def _demote_unresolved_link(token: Token, source_path: str, resolve_link: ResolveLink) -> bool:
    """Rewrite one ``link_open`` token in place; return whether it was
    demoted to a non-link ``span`` (so its matching ``link_close`` must be
    demoted too)."""

    href = token.attrGet("href") or ""
    if not href or _EXTERNAL_LINK.match(href):
        return False
    target, fragment = _resolve_link_target(source_path, href)
    try:
        record_id = resolve_link(target)
    except Exception:
        # A caller-supplied lookup must never turn a rendering pass into a
        # 500; treat any failure the same as "nothing lives there".
        record_id = None
    if record_id:
        new_href = f"/r/{record_id}" + (f"#{fragment}" if fragment else "")
        token.attrSet("href", new_href)
        return False
    # No record resolves: degrade to plain, visibly non-broken text rather
    # than a link that would 404 (the bare-directory case, or a relative
    # path outside the corpus).
    token.tag = "span"
    token.attrs.pop("href", None)
    token.attrSet("class", "md-link-unresolved")
    token.attrSet("title", strings.MARKDOWN_LINK_UNRESOLVED)
    return True


def _inline_children(tokens: list[Token]) -> Iterator[Token]:
    for token in tokens:
        if token.type == "inline" and token.children:
            yield from token.children


def _rewrite_relative_links(tokens: list[Token], source_path: str, resolve_link: ResolveLink) -> None:
    """Rewrite every relative record-to-record link in place.

    CommonMark never nests a link inside another link, so a single flag
    tracking "the most recently opened link_open became a span" is enough
    to keep each link_open paired with its own link_close correctly.
    """

    demoted = False
    for token in _inline_children(tokens):
        if token.type == "link_open":
            demoted = _demote_unresolved_link(token, source_path, resolve_link)
        elif token.type == "link_close" and demoted:
            token.tag = "span"
            demoted = False
