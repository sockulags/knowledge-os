"""``GET /s/{skill_name}`` — one operational-guidance skill by permalink.

A skill is not a record. ``knowledge_os.skills`` fixes exactly three allowed
frontmatter fields (``name``, ``description``, ``tags``); a skill has no
``id``, ``type``, ``status``, ``scope``, ``record_kind``, ``provenance``,
``created``/``updated``/``verified``, no lifecycle, no supersession, and is
absent from the search index. This view never invents or implies any of
those fields for a skill; it renders ``library.SkillEntry`` on its own terms.

Skills carry the trust label ``strings.SKILL_TRUST_LABEL`` ("operational
guidance"), assigned by ``library.py`` because ``context_policy.trust_label``
never returns it.

Three states, all rendered through ``skill.html`` (never a 500):

* Found — ``skill_name`` matches a ``library.SkillEntry.name`` in
  ``Library.skills``. Normal page.
* Broken — the name matches no entry in ``Library.skills``, but
  ``skills/{skill_name}/SKILL.md`` appears in ``Library.issues`` (a skill
  whose frontmatter failed to parse; ``validate_workspace`` folds skill
  parse issues into the same issue list it uses for records — see
  ``knowledge_os/workspace.py``). Rendered as broken with the exact message,
  never as "not found" and never as a silent empty page.
* Not found — no match either way. A clean explaining page.

``knowledge-os-documentation`` additionally has a ``references/``
subdirectory of plain Markdown files with no frontmatter, which
``load_skills`` ignores entirely (it only walks ``SKILL.md``). Those files
are surfaced here as clearly secondary material, outside the record
contract, via ``library.read_repo_document`` — never opened directly by
this module. The skill's own body is the only place that names them (as
Markdown links such as ``[references/init.md](references/init.md)``), so
this view discovers them by scanning the body text for that pattern rather
than walking the filesystem itself; a skill with no such links renders no
references block at all.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import get_library, render
from ..library import Library, LibraryError, SkillEntry, read_repo_document

#: The exact, raw contract term ``library.py`` assigns every skill as its
#: trust label (mirrors that module's own private ``_SKILL_TRUST_LABEL``,
#: which is not exported). Shown only in the "technical details" disclosure,
#: never in the primary reading path, where ``strings.SKILL_TRUST_LABEL``
#: ("Operational guidance for agents...") is used instead.
TRUST_LABEL_RAW = "operational guidance"

#: Matches a reference file's repository-relative path as it appears inside
#: a skill body's own Markdown links (both the link text and the href use
#: this same literal form: ``references/<name>.md``). Deliberately narrow:
#: this is pattern matching over text already loaded in memory, not a
#: Markdown parser and not a filesystem walk.
_REFERENCE_PATTERN = re.compile(r"references/[\w.-]+\.md")


def _find_skill(library: Library, skill_name: str) -> SkillEntry | None:
    for entry in library.skills:
        if entry.name == skill_name:
            return entry
    return None


def _find_broken_issue(library: Library, skill_name: str) -> str | None:
    """Return the issue message for skills/{skill_name}/SKILL.md, if any."""

    expected_path = f"skills/{skill_name}/SKILL.md"
    for issue in library.issues:
        if issue.path == expected_path:
            return issue.message
    return None


def _references(workspace: object, skill: SkillEntry) -> tuple[dict[str, object], ...]:
    """Resolve every ``references/*.md`` link named in the skill's own body.

    Each entry's title comes from ``library.read_repo_document`` (which
    falls back to the filename when the file has no heading); a file that
    cannot be read is still listed, marked unreadable, with the reason.
    """

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
            entries.append({"path": rel_path, "title": title, "readable": True, "detail": None})
        except LibraryError as exc:
            entries.append({"path": rel_path, "title": rel_path, "readable": False, "detail": str(exc)})
    return tuple(entries)


async def view(request: Request) -> Response:
    library = get_library(request)
    skill_name = request.path_params["skill_name"]

    skill = _find_skill(library, skill_name)
    if skill is None:
        broken_message = _find_broken_issue(library, skill_name)
        return render(
            request,
            "skill.html",
            page_title=strings.SKILL_NOT_FOUND_TITLE if broken_message is None else strings.SKILL_BROKEN_TITLE,
            library=library,
            skill=None,
            skill_name=skill_name,
            broken_message=broken_message,
            references=(),
            # A broken skill exists (its SKILL.md just failed validation),
            # so only an outright unknown name is a 404 -- the same
            # distinction views/document.py's Library.broken would draw for
            # a record, applied to the skill contract (Sec.6 "Broken
            # record").
            status_code=200 if broken_message is not None else 404,
        )

    workspace = request.app.state.workspace
    return render(
        request,
        "skill.html",
        page_title=skill.name,
        library=library,
        skill=skill,
        skill_name=skill_name,
        broken_message=None,
        references=_references(workspace, skill),
        trust_label_raw=TRUST_LABEL_RAW,
    )
