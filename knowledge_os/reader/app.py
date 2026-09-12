"""Route table and app factory for the Knowledge OS Reader.

Every route is registered here, once, so that no stage-B unit ever needs to
edit this file. Each of the eleven other units fills in exactly one view by
replacing the body of `async def view(request: Request) -> Response` inside
its own `views/<name>.py` module (see that module's stub); the route table
below is the complete, frozen wiring from a path to its view module.

View modules reach the shared Jinja2 environment and the per-request Library
through `get_library()` and `render()`, defined below. Those two imports
(`from ..app import get_library, render`) are why the view modules are
imported *inside* `create_app()` rather than at this module's top level: every
view imports this module, so importing the views up front would be a
circular import. By the time `create_app()` runs, this module has already
finished executing (get_library/render/etc. are fully defined), so the
view modules' own `from ..app import ...` resolves against the already-
initialized module instead of a half-built one.
"""

from __future__ import annotations

from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from knowledge_os.workspace import Workspace

from . import markdown, strings
from .library import Library, load_library

#: Package-relative asset locations, shared by the app factory and by
#: `kos-read`'s own sanity checks.
PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"


def _build_templates() -> Jinja2Templates:
    """Build the one Jinja2 environment every view renders through.

    Preconfigured so a stage-B view never has to touch environment setup:
    the `strings` module is a template global (``{{ strings.NAV_START }}``),
    and baseline Markdown rendering is available both as a global
    (``{{ markdown.render(text) }}``) and as the ``|markdown`` filter
    (``{{ record.body|markdown }}``).
    """

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.globals["strings"] = strings
    templates.env.globals["markdown"] = markdown
    templates.env.filters["markdown"] = markdown.render
    return templates


def get_library(request: Request) -> Library:
    """Return this request's Library, loaded at most once per request.

    ``load_library()`` re-scans the whole corpus from disk and is never
    cached *across* requests: a record edited while the server keeps running
    must show up on the next request (acceptance criterion 8). Memoizing on
    Starlette's per-request ``request.state`` only avoids a second
    filesystem walk if one handler needs the library more than once; the
    memo does not outlive the request.
    """

    cached = getattr(request.state, "library", None)
    if cached is None:
        cached = load_library(request.app.state.workspace)
        request.state.library = cached
    return cached


def render(request: Request, template_name: str, **context: object) -> HTMLResponse:
    """Render one template through the app's shared Jinja2 environment."""

    templates: Jinja2Templates = request.app.state.templates
    return templates.TemplateResponse(request, template_name, context)


def create_app(workspace: Workspace) -> Starlette:
    """Build the reader app for one workspace.

    Binds nothing itself: binding to ``127.0.0.1`` only is ``cli.py``'s job
    (via ``uvicorn.run(host=...)``). This wires routes, the shared template
    environment, and the workspace this process serves, one workspace per
    process, matching the accepted decision's boundaries.
    """

    from .views import document, everything, lineage, project, repodoc, search, skill, start

    routes = [
        Route("/", start.view, name="start"),
        Route("/p/{project_id}", project.view, name="project"),
        Route("/r/{record_id}", document.view, name="document"),
        Route("/r/{record_id}/compare", lineage.view, name="lineage"),
        Route("/s/{skill_name}", skill.view, name="skill"),
        Route("/f/{path:path}", repodoc.view, name="repodoc"),
        Route("/search", search.view, name="search"),
        Route("/everything", everything.view, name="everything"),
        Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ]

    app = Starlette(debug=True, routes=routes)
    app.state.workspace = workspace
    app.state.templates = _build_templates()
    return app
