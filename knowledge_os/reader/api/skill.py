"""``GET /api/skills/{skill_name}`` — one operational-guidance skill.

A skill is not a record (see ``views/skill.py``'s original docstring, kept
here as design memory): it has no ``id``/``type``/``status``/``scope``, no
lifecycle, and is absent from the search index. This endpoint never invents
or implies any of those fields; it serves ``library.SkillEntry`` on its own
terms, plus the ``references/*.md`` files its body links to.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from starlette.requests import Request
from starlette.responses import Response

from .. import markdown, strings
from ..app import get_library, json_response, not_found
from ..library import Library, LibraryError, SkillEntry, read_repo_document
from .common import strip_leading_h1

_REFERENCE_PATTERN = re.compile(r"references/[\w.-]+\.md")


def _find_skill(library: Library, skill_name: str) -> SkillEntry | None:
    for entry in library.skills:
        if entry.name == skill_name:
            return entry
    return None


def _find_broken_issue(library: Library, skill_name: str) -> str | None:
    expected_path = f"skills/{skill_name}/SKILL.md"
    for issue in library.issues:
        if issue.path == expected_path:
            return issue.message
    return None


def _references(workspace: object, skill: SkillEntry) -> list[dict[str, object]]:
    directory = PurePosixPath(skill.path).parent
    seen: set[str] = set()
    entries: list[dict[str, object]] = []
    for match in _REFERENCE_PATTERN.finditer(skill.body):
        rel_path = str(directory / match.group(0))
        if rel_path in seen:
            continue
        seen.add(rel_path)
        try:
            title, _ = read_repo_document(workspace, rel_path)
            entries.append({"path": rel_path, "title": title, "readable": True, "detail": None, "href": f"/f/{rel_path}"})
        except LibraryError as exc:
            entries.append({"path": rel_path, "title": rel_path, "readable": False, "detail": str(exc), "href": None})
    return entries


async def view(request: Request) -> Response:
    library = get_library(request)
    skill_name = request.path_params["skill_name"]

    skill = _find_skill(library, skill_name)
    if skill is None:
        broken_message = _find_broken_issue(library, skill_name)
        if broken_message is not None:
            return json_response(
                {
                    "name": skill_name,
                    "broken": {"label": strings.SKILL_BROKEN_TITLE, "detail": strings.SKILL_BROKEN_BODY.format(name=skill_name, message=broken_message)},
                }
            )
        return not_found(strings.SKILL_NOT_FOUND_BODY.format(name=skill_name))

    workspace = request.app.state.workspace
    # A skill's body conventionally opens with a level-1 heading that is a
    # nicer-cased rendering of its kebab-case `name` (e.g. "Ingest source"
    # for "ingest-source"); use it as the page's display title when present
    # rather than showing the raw name twice, and strip it from the body so
    # it is not repeated a second time as the first line of prose.
    all_headings = markdown.headings(skill.body)
    display_title = all_headings[0][1] if all_headings and all_headings[0][0] == 1 else skill.name
    body = strip_leading_h1(skill.body)
    body_html = markdown.render(body)
    headings = [h for h in markdown.headings(body) if h[0] <= 3]

    return json_response(
        {
            "name": skill.name,
            "title": display_title,
            "description": skill.description,
            "tags": list(skill.tags),
            "trust_label": strings.SKILL_TRUST_LABEL,
            "body_html": body_html,
            "headings": headings,
            "references": _references(workspace, skill),
            "broken": None,
        }
    )
