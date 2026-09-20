"""Plain-text helpers shared by ``GET /api/search`` (a snippet is a raw
slice of a record's own Markdown source) and the compare view's paragraph
diff (a changed paragraph's word-level highlight is computed on the same
kind of raw text, not on rendered HTML). Both need to turn Markdown source
into safe, readable plain text before wrapping part of it in ``<mark>``.
"""

from __future__ import annotations

import re

#: A markdown link with its URL still attached: `[text](url)`. Deliberately
#: requires the trailing `(...)` so this can never consume a bare match
#: marker a caller wraps in the same bracket characters. The link text's
#: own character class allows exactly one level of nested "[...]" (a
#: caller's own match marker nested inside link text).
_MD_LINK = re.compile(r"\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^()]*)\)")
#: A leading heading marker ("## ", "### ", ...).
_MD_HEADING = re.compile(r"#{1,6}\s*")
#: Emphasis/strong markers: **text**, *text*, __text__, _text_.
_MD_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(.+?)\1")
#: Inline code backticks.
_MD_CODE = re.compile(r"`([^`]*)`")


def strip_markdown_syntax(text: str) -> str:
    """Drop heading markers, link/emphasis/code syntax, keeping the words
    themselves -- the same stripping a search snippet already needed
    (``library.search``'s ``snippet()`` call runs over the FTS index, not
    over rendered HTML, so the raw slice can carry any of this verbatim).
    Order matters: links are stripped first, since a genuine markdown link
    and a caller's own match marker can use the same bracket characters."""

    text = _MD_LINK.sub(r"\1", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_EMPHASIS.sub(r"\2", text)
    text = _MD_CODE.sub(r"\1", text)
    return text


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
