"""Page templates: the starting text *New page* offers.

A template is an ordinary Markdown file in the knowledge base's
``templates/`` folder, ``templates/<name>.md``, where ``<name>`` is
lowercase kebab-case. It may start with a small frontmatter block:

```markdown
---
title: Meeting notes
description: Who met, what was decided, and what happens next.
kind: note
---
- **Date:** {{date}}
...
```

``title`` (default: the name as words) and ``description`` (default: empty)
are what the picker shows; ``kind`` is ``note`` (default) or ``decision``,
which makes the new page a proposed decision. The body is the page's
starting text; ``{{date}}`` is replaced with the day the page is created.

Templates are not records: they have no ID, provenance, or lifecycle, are
never indexed, and are not checked by ``kos lint``, so a broken template can
never block a write. A file that cannot be used is still listed, with the
reason, so the person who wrote it can see what is wrong.

Four templates are built in (``blank``, ``meeting-notes``, ``how-to``, and
``decision``); ``kos init`` writes the last three into ``templates/`` so they
can be edited. A file in ``templates/`` with the same name replaces the
built-in one, and any other file adds a template. Knowledge bases created
before templates existed get the built-in ones until they add their own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .model import ID_PATTERN
from .workspace import Workspace, WorkspaceError, is_managed_link

TEMPLATES_DIR = "templates"
TEMPLATE_KINDS = ("note", "decision")
_FIELDS = {"title", "description", "kind"}
_DATE_PLACEHOLDER = re.compile(r"\{\{\s*date\s*\}\}")
#: Templates are small starting texts; anything larger is refused rather than
#: sent to every New page form.
MAX_TEMPLATE_BYTES = 64 * 1024


@dataclass(frozen=True)
class Template:
    name: str
    title: str
    description: str
    kind: str  # "note" or "decision"
    body: str
    source: str  # "built-in" or "workspace"
    path: str | None  # workspace-relative, for a workspace template
    error: str | None = None  # why a workspace file cannot be used


def _file_text(title: str, description: str, kind: str, body: str) -> str:
    fields = {"title": title, "description": description, "kind": kind}
    frontmatter = yaml.safe_dump(fields, sort_keys=False, allow_unicode=True, width=1000)
    return f"---\n{frontmatter}---\n{body}"


#: The built-in templates, in picker order. ``kos init`` writes every one but
#: ``blank`` into ``templates/`` as ``<name>.md`` with ``_file_text``.
BUILT_IN: tuple[Template, ...] = (
    Template("blank", "Blank page", "An empty page.", "note", "", "built-in", None),
    Template(
        "meeting-notes",
        "Meeting notes",
        "Who met, what was decided, and what happens next.",
        "note",
        (
            "- **Date:** {{date}}\n"
            "- **Attendees:** \n"
            "\n"
            "## Summary\n"
            "\n"
            "## Decisions\n"
            "\n"
            "## Action items\n"
            "\n"
            "## Open questions\n"
        ),
        "built-in",
        None,
    ),
    Template(
        "how-to",
        "How-to",
        "Steps for getting one thing done.",
        "note",
        (
            "What this achieves and when to use it.\n"
            "\n"
            "## Before you start\n"
            "\n"
            "- \n"
            "\n"
            "## Steps\n"
            "\n"
            "1. \n"
            "\n"
            "## Check that it worked\n"
            "\n"
            "## If something goes wrong\n"
        ),
        "built-in",
        None,
    ),
    Template(
        "decision",
        "Decision",
        "A proposal: the situation, the choice, and what follows from it.",
        "decision",
        (
            "## Context\n"
            "\n"
            "What situation or problem makes a decision necessary.\n"
            "\n"
            "## Decision\n"
            "\n"
            "What is decided, stated as a rule.\n"
            "\n"
            "## Consequences\n"
            "\n"
            "What becomes easier or harder, and what has to change.\n"
        ),
        "built-in",
        None,
    ),
)


def built_in_files() -> dict[str, str]:
    """``templates/<name>.md`` contents for ``kos init``: every built-in
    template except ``blank``, which needs no file."""

    return {
        f"{template.name}.md": _file_text(template.title, template.description, template.kind, template.body)
        for template in BUILT_IN
        if template.name != "blank"
    }


def _default_title(name: str) -> str:
    return name.replace("-", " ").capitalize()


def _broken(name: str, path: str, error: str) -> Template:
    return Template(name, _default_title(name), "", "note", "", "workspace", path, error)


def parse_template(name: str, path: str, text: str) -> Template:
    """Read one template file; a problem comes back as ``error``, never raised."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    fields: dict[str, object] = {}
    body = normalized
    if normalized.startswith("---\n"):
        closing = normalized.find("\n---\n", 3)
        if closing == -1 and normalized.endswith("\n---"):
            closing = len(normalized) - 4
        if closing == -1:
            return _broken(name, path, "the frontmatter block is not closed with a line of three dashes")
        try:
            loaded = yaml.safe_load(normalized[4:closing]) or {}
        except yaml.YAMLError as exc:
            return _broken(name, path, f"the frontmatter is not valid YAML: {exc}")
        if not isinstance(loaded, dict):
            return _broken(name, path, "the frontmatter must be a set of fields such as title and kind")
        fields = loaded
        body = normalized[closing + 5 :]
    unknown = sorted(str(field) for field in fields if field not in _FIELDS)
    if unknown:
        return _broken(name, path, f"unknown field(s): {', '.join(unknown)}; a template may have title, description, and kind")
    title = fields.get("title", _default_title(name))
    description = fields.get("description", "")
    kind = fields.get("kind", "note")
    if description is None:
        description = ""
    if not isinstance(title, str) or not title.strip():
        return _broken(name, path, "title must be non-empty text")
    if not isinstance(description, str):
        return _broken(name, path, "description must be text")
    if kind not in TEMPLATE_KINDS:
        return _broken(name, path, f"kind must be {' or '.join(TEMPLATE_KINDS)}")
    return Template(name, title.strip(), description.strip(), str(kind), body, "workspace", path)


def _workspace_templates(workspace: Workspace) -> list[Template]:
    directory = workspace.root / TEMPLATES_DIR
    if is_managed_link(directory) or not directory.is_dir():
        return []
    found: list[Template] = []
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if path.suffix.lower() != ".md" or path.name == "README.md":
            continue
        relative = f"{TEMPLATES_DIR}/{path.name}"
        name = path.stem
        if not ID_PATTERN.fullmatch(name):
            found.append(_broken(name, relative, "the file name must be lowercase words joined by hyphens, like meeting-notes.md"))
            continue
        try:
            workspace.assert_safe_path(path)
            if not path.is_file():
                continue
            raw = path.read_bytes()
        except (WorkspaceError, OSError) as exc:
            found.append(_broken(name, relative, str(exc)))
            continue
        if len(raw) > MAX_TEMPLATE_BYTES:
            found.append(_broken(name, relative, f"the file is larger than {MAX_TEMPLATE_BYTES // 1024} KB"))
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            found.append(_broken(name, relative, "the file must be UTF-8 text"))
            continue
        found.append(parse_template(name, relative, text))
    return found


def list_templates(workspace: Workspace) -> list[Template]:
    """The templates *New page* offers: the built-in ones in their order, each
    replaced by a workspace file of the same name, then the workspace's other
    templates by name. ``blank`` is always first."""

    own = {template.name: template for template in _workspace_templates(workspace)}
    ordered = [own.pop(template.name, template) for template in BUILT_IN]
    return ordered + [own[name] for name in sorted(own)]


def find_template(workspace: Workspace, name: str) -> Template | None:
    return next((template for template in list_templates(workspace) if template.name == name), None)


def fill(body: str, today: str) -> str:
    """The template's starting text for a page created on ``today`` (ISO)."""

    return _DATE_PLACEHOLDER.sub(today, body)
