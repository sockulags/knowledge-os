"""``GET /api/workspace`` and ``GET /api/nav`` — the shell's own data: the
workspace name and health summary, and everything the left sidebar and the
quick-find palette need (the project tree, skills, repository documents,
and a flat record index for client-side title search).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import states, strings
from ..app import get_library, json_response
from ..library import Library
from ..repodocs import list_repo_documents
from .decisions import proposed_decisions
from .common import pill_for, project_title, project_tree_json, record_index_entry


def _health_json(library: Library) -> dict[str, object]:
    summary = states.build_health_summary(library)
    return {
        "lint_ok": summary.lint_ok,
        "lint_message": summary.lint_message,
        "issue_count": summary.issue_count,
        "issues": [
            {"path": issue.path, "message": issue.message, "record_id": issue.record_id}
            for issue in summary.issues
        ],
        "index_available": summary.index_available,
        "index_stale": summary.index_stale,
        "search_disabled": summary.search_disabled,
        "search_disabled_reason": summary.search_disabled_reason,
    }


async def workspace_view(request: Request) -> Response:
    library = get_library(request)
    return json_response(
        {
            "name": library.workspace_name or strings.APP_NAME,
            "health": _health_json(library),
        }
    )


def _project_ids(library: Library) -> list[str]:
    slugs = {
        record.scope.removeprefix("project:") for record in library.records if record.scope.startswith("project:")
    }
    return sorted(slugs, key=lambda slug: project_title(library, slug).lower())


async def nav_view(request: Request) -> Response:
    library = get_library(request)
    workspace = request.app.state.workspace

    projects = []
    for project_id in _project_ids(library):
        scoped = [
            r
            for r in library.records
            if r.scope == f"project:{project_id}" and not (r.type == "project" and r.id == project_id)
        ]
        project_broken = [b for b in library.broken if b.path.startswith(f"projects/{project_id}/")]
        projects.append(
            {
                "id": project_id,
                "title": project_title(library, project_id),
                "tree": project_tree_json(project_id, scoped, project_broken),
            }
        )

    skills = [{"name": skill.name, "description": skill.description} for skill in sorted(library.skills, key=lambda s: s.name.lower())]

    repo_docs = [
        {"path": entry.path, "title": entry.title}
        for entry in list_repo_documents(workspace)
        if entry.readable
    ]

    record_index: list[dict[str, object]] = []
    for record in sorted(library.records, key=lambda r: r.title.lower()):
        project_id = record.scope.removeprefix("project:") if record.scope.startswith("project:") else None
        record_index.append(
            record_index_entry(
                "decision" if record.is_decision else record.type,
                id=record.id,
                title=record.title,
                pill=pill_for(record),
                project=project_id,
            )
        )
    for skill in library.skills:
        record_index.append(record_index_entry("skill", id=skill.name, title=skill.name, pill=None, project=None))
    for entry in list_repo_documents(workspace):
        if entry.readable:
            record_index.append(record_index_entry("doc", id=entry.path, title=entry.title, pill=None, project=None))

    return json_response(
        {
            "workspace_name": library.workspace_name or strings.APP_NAME,
            "projects": projects,
            "skills": skills,
            "repo_docs": repo_docs,
            "record_index": record_index,
            # The sidebar's Decide entry and its count of proposed decisions;
            # the shell reloads nav after every decision action.
            "decide": {"label": strings.DECIDE_NAV_LABEL, "count": len(proposed_decisions(library))},
        }
    )
