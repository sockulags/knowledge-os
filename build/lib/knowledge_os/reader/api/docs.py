"""``GET /api/docs/{path}`` — one file from the unmanaged repository-document
tier: outside the record contract, read-only, always labelled as such.

The path parameter is caller-supplied, so this route is refused-by-default:
it only reaches ``library.read_repo_document`` when the normalized path
exactly matches ``repodocs.REPO_DOCUMENT_PATHS`` or a skill's own
``references/*.md`` file (``repodocs.is_skill_reference_path``). Every other
shape, including every path-traversal attempt, is refused before touching
the filesystem, and every refusal answers the same 404 JSON shape
deliberately: telling a caller *why* would leak information about a path it
should not be probing in the first place.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import get_library, json_response, not_found
from ..library import path_index
from ..repodocs import REPO_DOCUMENT_PATHS, is_skill_reference_path, read_text_entry, render_document
from .common import strip_leading_h1


async def view(request: Request) -> Response:
    workspace = request.app.state.workspace
    library = get_library(request)
    raw_path = request.path_params["path"]
    rel_path = raw_path.lstrip("/")

    if rel_path not in REPO_DOCUMENT_PATHS and not is_skill_reference_path(rel_path):
        return not_found(strings.REPODOC_NOT_IN_TIER.format(path=raw_path))

    document, text = read_text_entry(workspace, rel_path)
    if not document.readable:
        assert document.detail is not None
        return not_found(document.detail)

    assert text is not None
    body = strip_leading_h1(text)
    html, toc = render_document(body, source_path=rel_path, resolve_link=path_index(library).get)
    return json_response(
        {
            "path": document.path,
            "title": document.title,
            "unmanaged_label": strings.UNMANAGED_TIER_LABEL,
            "body_html": html,
            "headings": [list(item) for item in toc],
        }
    )
