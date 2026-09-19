"""The JSON API: one Starlette ``Route`` per endpoint, assembled here.

Every endpoint module in this package is a non-adapter module (no
``knowledge_os.*`` import — see ``tests/test_reader_readonly.py``'s
``OneAdapterRuleTests``, which now walks this package instead of the old
``views/``), built the same way the original HTML views were: pure
functions over ``library.Library`` and its dataclasses, reshaped into JSON
through ``api/common.py`` and translated to sentences through
``language.py``/``strings.py``, never re-deriving trust, lifecycle, or
grouping rules of their own.
"""

from __future__ import annotations

from starlette.routing import Route

from . import docs, everything, home, project, record, search, skill, workspace_nav


def build_api_routes() -> list[Route]:
    return [
        Route("/api/workspace", workspace_nav.workspace_view, name="api-workspace"),
        Route("/api/nav", workspace_nav.nav_view, name="api-nav"),
        Route("/api/home", home.view, name="api-home"),
        Route("/api/projects/{project_id}", project.view, name="api-project"),
        Route("/api/records/{record_id}", record.view, name="api-record"),
        Route("/api/records/{record_id}/compare", record.compare_view, name="api-record-compare"),
        Route("/api/skills/{skill_name}", skill.view, name="api-skill"),
        Route("/api/docs/{path:path}", docs.view, name="api-docs"),
        Route("/api/search", search.view, name="api-search"),
        Route("/api/everything", everything.view, name="api-everything"),
    ]
