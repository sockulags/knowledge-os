"""Relative Markdown links in record bodies: resolve them and rewrite them after a move.

A relative link is resolved the way the reader resolves it
(``knowledge_os/reader/markdown.py``): a destination that has a URI scheme,
starts with ``//``, or is only a ``#fragment`` is external and left alone;
otherwise the part before ``#`` is joined to the directory of the linking
file and normalized with ``posixpath``. The reader may not import this
module (it keeps one adapter), so the rule is repeated there;
``tests/test_structure.py`` checks that both agree.

``rewrite_links`` keeps every relative link pointing at the same place after
files move: a link whose target moved points at the new location, and a link
inside a moved file is recomputed from the file's new directory. Only the
destination text of a link that has to change is replaced; everything else in
the body keeps its exact bytes. Recognized forms are inline links and images
(``[text](dest "title")``, ``![alt](<dest>)``) and reference definitions
(``[label]: dest``). Fenced code blocks and inline code spans are skipped.
Links split across lines, indented code blocks, and raw HTML are not
rewritten.
"""

from __future__ import annotations

import posixpath
import re
from typing import Callable, Iterator

#: The same test as the reader's ``_EXTERNAL_LINK``: a URI scheme, a
#: protocol-relative ``//`` link, or a same-page ``#fragment``.
EXTERNAL_LINK = re.compile(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|//|#)")

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_REFERENCE_DEFINITION = re.compile(r"^( {0,3}\[(?:[^\]\\\n]|\\.)+\]:[ \t]*)(<[^>\n]*>|\S+)")

#: Old workspace-relative target path -> new target path, or None when the
#: target did not move.
Relocate = Callable[[str], "str | None"]


def resolve_link_target(source_path: str, href: str) -> tuple[str, str]:
    """Split a relative href into its workspace-relative target and ``#fragment``."""

    path, _, fragment = href.partition("#")
    target = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), path))
    return target, fragment


def _relative_href(destination: str) -> tuple[str, str, str] | None:
    """``(path, "#" or "", fragment)`` for a relative destination, else None."""

    href = destination[1:-1] if destination.startswith("<") and destination.endswith(">") else destination
    if not href or EXTERNAL_LINK.match(href) or href.startswith("/"):
        return None
    path, hash_mark, fragment = href.partition("#")
    if not path:
        return None
    return path, hash_mark, fragment


def _relative(target: str, directory: str) -> str:
    # posixpath.relpath on relative paths consults the process's working
    # directory; anchoring both below one fake absolute root avoids that.
    return posixpath.relpath("/w/" + target, "/w/" + directory if directory else "/w")


def _code_spans(line: str) -> list[tuple[int, int]]:
    """Ranges of inline code spans on one line (a backtick run closed by a run of equal length)."""

    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(line):
        if line[index] != "`":
            index += 1
            continue
        end = index
        while end < len(line) and line[end] == "`":
            end += 1
        run = line[index:end]
        search = end
        closing = -1
        while True:
            found = line.find(run, search)
            if found == -1:
                break
            after = found + len(run)
            if (after >= len(line) or line[after] != "`") and line[found - 1] != "`":
                closing = found
                break
            search = found + 1
        if closing == -1:
            index = end
            continue
        spans.append((index, closing + len(run)))
        index = closing + len(run)
    return spans


def _inline_destination(line: str, start: int) -> tuple[int, int] | None:
    """The ``(begin, end)`` of an inline link destination that starts after ``](`` at ``start``."""

    index = start
    while index < len(line) and line[index] in " \t":
        index += 1
    if index >= len(line):
        return None
    if line[index] == "<":
        closing = line.find(">", index + 1)
        return None if closing == -1 else (index, closing + 1)
    begin = index
    depth = 0
    while index < len(line):
        character = line[index]
        if character == "\\" and index + 1 < len(line):
            index += 2
            continue
        if character.isspace():
            break
        if character == "(":
            depth += 1
        elif character == ")":
            if depth == 0:
                break
            depth -= 1
        index += 1
    return None if index == begin else (begin, index)


def _destinations(line: str) -> list[tuple[int, int]]:
    """Every link destination on one line outside code, as ``(begin, end)`` offsets."""

    definition = _REFERENCE_DEFINITION.match(line)
    if definition:
        return [(definition.start(2), definition.end(2))]
    spans = _code_spans(line)
    found: list[tuple[int, int]] = []
    search = 0
    while True:
        position = line.find("](", search)
        if position == -1:
            return found
        search = position + 2
        if any(begin <= position < end for begin, end in spans):
            continue
        location = _inline_destination(line, position + 2)
        if location is not None:
            found.append(location)
            search = location[1]


def _lines_outside_fences(lines: list[str]) -> Iterator[int]:
    fence: str | None = None
    for index, line in enumerate(lines):
        match = _FENCE.match(line)
        if fence is not None:
            if (
                match
                and match.group(1)[0] == fence[0]
                and len(match.group(1)) >= len(fence)
                and not line[match.end() :].strip()
            ):
                fence = None
            continue
        if match:
            fence = match.group(1)
            continue
        yield index


def rewrite_links(body: str, old_source: str, new_source: str, relocate: Relocate) -> str:
    """Rewrite the relative links in ``body`` so they keep their targets.

    ``old_source`` and ``new_source`` are the linking file's workspace-relative
    paths before and after the change (equal when it did not move);
    ``relocate`` maps a target that moved to its new path.
    """

    new_directory = posixpath.dirname(new_source)

    def replacement(destination: str) -> str | None:
        parts = _relative_href(destination)
        if parts is None:
            return None
        path, hash_mark, fragment = parts
        old_target, _ = resolve_link_target(old_source, path)
        new_target = relocate(old_target) or old_target
        if new_source == old_source and new_target == old_target:
            return None
        new_path = _relative(new_target, new_directory)
        if path.endswith("/") and not new_path.endswith("/"):
            new_path += "/"
        if path.startswith("./") and not new_path.startswith("."):
            new_path = "./" + new_path
        if new_path == path:
            return None
        rewritten = new_path + hash_mark + fragment
        if destination.startswith("<") or any(character.isspace() for character in rewritten):
            return f"<{rewritten}>"
        return rewritten

    lines = body.splitlines(keepends=True)
    for index in _lines_outside_fences(lines):
        line = lines[index]
        for begin, end in reversed(_destinations(line)):
            new = replacement(line[begin:end])
            if new is not None:
                line = line[:begin] + new + line[end:]
        lines[index] = line
    return "".join(lines)


def relative_links(body: str, source_path: str) -> list[tuple[str, str]]:
    """Every relative link in ``body`` as ``(target, fragment)``, resolved the reader's way."""

    found: list[tuple[str, str]] = []
    lines = body.splitlines(keepends=True)
    for index in _lines_outside_fences(lines):
        line = lines[index]
        for begin, end in _destinations(line):
            parts = _relative_href(line[begin:end])
            if parts is not None:
                target, _ = resolve_link_target(source_path, parts[0])
                found.append((target, parts[2]))
    return found
