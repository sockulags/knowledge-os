"""``GET /api/workspace`` and ``GET /api/nav`` — the shell's own data: the
workspace name and health summary, and everything the left sidebar and the
quick-find palette need (the project tree, skills, repository documents,
and a flat record index for client-side title search).
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import language, states, strings
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
                group=language.quick_find_group(record),
                kind_label=language.quick_find_kind_label(record),
            )
        )
    # A project with pages but no overview record of its own is still a
    # place the quick switcher can jump to.
    listed_projects = {entry["id"] for entry in record_index if entry["group"] == "projects"}
    for project in projects:
        if project["id"] not in listed_projects:
            record_index.append(
                record_index_entry(
                    "project",
                    id=str(project["id"]),
                    title=str(project["title"]),
                    pill=None,
                    project=str(project["id"]),
                    group="projects",
                    kind_label=strings.QUICK_FIND_PROJECT_LABEL,
                )
            )
    for skill in library.skills:
        record_index.append(
            record_index_entry(
                "skill",
                id=skill.name,
                title=skill.name,
                pill=None,
                project=None,
                group="skills",
                kind_label=strings.QUICK_FIND_SKILL_LABEL,
            )
        )
    for entry in list_repo_documents(workspace):
        if entry.readable:
            record_index.append(
                record_index_entry(
                    "doc",
                    id=entry.path,
                    title=entry.title,
                    pill=None,
                    project=None,
                    group="docs",
                    kind_label=strings.QUICK_FIND_DOC_LABEL,
                )
            )

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
            # Shell-wide copy with no page of its own to be delivered from:
            # the quick-find placeholder, and the not-found/load-error
            # fallbacks every record-backed page (Document, Compare,
            # EditRecord) shows the same way. Loaded once with the rest of
            # the nav rather than re-fetched per page.
            "language": {
                "quick_find_placeholder": strings.QUICK_FIND_PLACEHOLDER,
                "quick_find_label": strings.QUICK_FIND_LABEL,
                "quick_find_hint": strings.QUICK_FIND_HINT,
                "quick_find_no_matches": strings.QUICK_FIND_NO_MATCHES,
                "quick_find_searching": strings.QUICK_FIND_SEARCHING,
                "quick_find_groups": strings.QUICK_FIND_GROUPS,
                "not_found_title": strings.DOCUMENT_NOT_FOUND_TITLE,
                "not_found_body": strings.DOCUMENT_NOT_FOUND_BODY,
                "load_error": strings.DOCUMENT_LOAD_ERROR,
                "network_error": strings.NETWORK_UNREACHABLE_ERROR,
            },
        }
    )
