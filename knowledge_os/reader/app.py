"""Route table and app factory for the Knowledge OS Reader.

The reader is a JSON API (``/api/*``) plus a single-page React app built by
``reader-ui/`` and committed at ``static/app/``. Every route is registered
here, once: ``api/__init__.py`` builds the ``/api/*`` route list from its
own sibling endpoint modules (mirroring the old ``views/`` package's
per-view split, one JSON endpoint per module), this module mounts static
assets and adds the SPA fallback that lets a client-side route
(``/p/...``, ``/r/...``, a refresh, a deep link) resolve to ``index.html``
instead of a 404.

View/endpoint modules reach the shared per-request ``Library`` and a JSON
response helper through ``get_library()`` and ``json_response()``, defined
below. Those two imports (``from ..app import get_library, json_response``)
are why the API modules are imported *inside* ``create_app()`` rather than
at this module's top level: every endpoint module imports this module, so
importing them up front would be a circular import. By the time
``create_app()`` runs, this module has already finished executing
(``get_library``/``json_response`` are fully defined), so an endpoint
module's own ``from ..app import ...`` resolves against the already-
initialized module instead of a half-built one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from knowledge_os.workspace import Workspace

from .library import Library, load_library

#: Package-relative asset locations, shared by the app factory and by
#: ``kos-read``'s own sanity checks. ``STATIC_APP_DIR`` is the React build
#: output (``reader-ui``'s ``npm run build``, committed to the repository so
#: ``pip install -e ".[reader]"`` and ``kos-read`` work with no Node
#: toolchain installed).
PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_APP_DIR = PACKAGE_ROOT / "static" / "app"
ASSETS_DIR = STATIC_APP_DIR / "assets"


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


def json_response(payload: Any, *, status_code: int = 200) -> JSONResponse:
    """The one place every ``/api/*`` handler builds its response, so status
    codes and content type stay consistent across all of them."""

    return JSONResponse(payload, status_code=status_code)


def not_found(detail: str) -> JSONResponse:
    """Unknown ids return 404 JSON, uniformly, across every endpoint."""

    return json_response({"detail": detail}, status_code=404)


async def _spa_index(request: Request) -> Response:
    """Serve the built SPA's ``index.html`` for every non-``/api`` path
    (``/``, ``/p/...``, ``/r/...``, ``/search``, a refresh, a deep link),
    so client-side routing and a hard reload both work. If the frontend has
    never been built (a fresh checkout with no ``npm run build`` yet), this
    reports that plainly instead of a bare 404/500."""

    index = STATIC_APP_DIR / "index.html"
    if not index.is_file():
        return PlainTextResponse(
            "The reader UI has not been built. Run `npm install && npm run build` in reader-ui/.",
            status_code=503,
        )
    return FileResponse(index)


async def _api_not_found(request: Request) -> Response:
    path = request.path_params.get("full_path", "")
    return not_found(f"No API route matches /api/{path}.")


def create_app(workspace: Workspace) -> Starlette:
    """Build the reader app for one workspace.

    Binds nothing itself: binding to ``127.0.0.1`` only is ``cli.py``'s job
    (via ``uvicorn.run(host=...)``). This wires the JSON API, the built
    SPA's static assets and fallback, and the workspace this process
    serves — one workspace per process, matching the accepted decision's
    boundaries.
    """

    from .api import build_api_routes
    from .api.write import new_write_token

    routes: list[Route | Mount] = list(build_api_routes())
    routes.append(Route("/api/{full_path:path}", _api_not_found))

    if ASSETS_DIR.is_dir():
        routes.append(Mount("/assets", app=StaticFiles(directory=str(ASSETS_DIR)), name="assets"))
    # A bare path convertor's regex also matches an empty string, so this
    # one route serves both "/" and every deeper client-side path
    # ("/p/...", "/r/.../compare", a refresh, a bookmark).
    routes.append(Route("/{full_path:path}", _spa_index))

    app = Starlette(debug=False, routes=routes)
    app.state.workspace = workspace
    # Random per process: only a page that can read this server's own
    # responses (GET /api/session) can write through it.
    app.state.write_token = new_write_token()
    return app
