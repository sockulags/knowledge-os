"""``GET /api/templates`` — the templates *New page* offers.

A template is not a record (see ``knowledge_os/templates.py``): it has no
ID, lifecycle, or provenance and is never indexed. This endpoint lists every
one, built in or from the knowledge base's ``templates/`` folder, with its
starting text for a page created today, plus the picker's words.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import Response

from .. import strings
from ..app import json_response
from ..library import page_templates

TEMPLATES_FOLDER = "templates"


async def view(request: Request) -> Response:
    workspace = request.app.state.workspace
    items = []
    for template, text in page_templates(workspace):
        items.append(
            {
                "name": template.name,
                "title": template.title,
                "description": template.description,
                "kind": template.kind,
                "body": text,
                "source": template.source,
                "path": template.path,
                "error": template.error,
            }
        )
    language = {**strings.TEMPLATES_LANGUAGE, "hint": strings.TEMPLATES_LANGUAGE["hint"].format(folder=TEMPLATES_FOLDER)}
    return json_response({"templates": items, "folder": TEMPLATES_FOLDER, "language": language})
