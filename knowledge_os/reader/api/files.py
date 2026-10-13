"""Images and files attached to pages: ``POST /api/attachments`` stores one
and ``GET /api/files/{path}`` serves one.

An attachment lives in the ``assets/`` folder next to the page that links to
it (see ``knowledge_os/attachments.py``). The upload is JSON like every other
write, behind the same guard and token, with the file's bytes in base64:
``{"filename", "data_base64", "record_id"}`` for an existing page or
``{"filename", "data_base64", "project", "folder"}`` for a page that is not
written yet. It answers ``201`` with ``{"path", "link", "url", "name",
"markdown", "image", "created", "content_sha256", "commit"}``, where ``link``
is relative to the page's folder and ``markdown`` is what the editor inserts.

The file route serves only files inside a page root's ``assets/`` folder.
Images are shown inline; every other type is sent as a download. Each
response forbids MIME sniffing and carries a sandboxing Content Security
Policy, so an SVG or any other file opened on its own can never run script
with the reader's origin (and so could never read the write token).
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import posixpath

from starlette.requests import Request
from starlette.responses import FileResponse, Response

from ..app import json_response, not_found
from ..library import MAX_ATTACHMENT_BYTES, WriteError, attach_file, attachment_file
from .write import _commit_json, _field, _write_error_response, _write_payload

#: Types shown inline; anything else is a download.
_INLINE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

_SAFETY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox",
    "Cache-Control": "no-cache",
}


def _markdown(name: str, link: str, image: bool) -> str:
    label = posixpath.splitext(name)[0].replace("-", " ")
    return f"![{label}]({link})" if image else f"[{name}]({link})"


async def attach_view(request: Request) -> Response:
    payload = await _write_payload(request)
    if isinstance(payload, Response):
        return payload
    try:
        filename = _field(payload, "filename", str, required=True)
        encoded = _field(payload, "data_base64", str, required=True)
        record_id = _field(payload, "record_id", str, required=False)
        project = _field(payload, "project", str, required=False)
        folder = _field(payload, "folder", str, required=False) or ""
        if len(encoded) > (MAX_ATTACHMENT_BYTES // 3 + 1) * 4:
            raise WriteError(
                "validation",
                f"the file is larger than {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB; keep large media outside the "
                "knowledge base and link to it",
            )
        try:
            data = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise WriteError("bad_request", "data_base64 is not valid base64") from exc
        result = attach_file(
            request.app.state.workspace,
            filename=filename,
            data=data,
            record_id=record_id,
            project_id=project,
            folder=folder,
        )
    except WriteError as exc:
        return _write_error_response(exc)
    image = posixpath.splitext(result.name)[1].lower() in _INLINE_TYPES
    return json_response(
        {
            "path": result.path,
            "link": result.link,
            "url": result.url,
            "name": result.name,
            "markdown": _markdown(result.name, result.link, image),
            "image": image,
            "created": result.created,
            "content_sha256": result.content_sha256,
            "commit": _commit_json(result.commit),
        },
        status_code=201,
    )


async def file_view(request: Request) -> Response:
    rel_path = request.path_params["path"]
    path = attachment_file(request.app.state.workspace, rel_path)
    if path is None:
        return not_found(f"No attached file at {rel_path}.")
    suffix = path.suffix.lower()
    inline_type = _INLINE_TYPES.get(suffix)
    if inline_type is not None:
        return FileResponse(path, media_type=inline_type, headers=_SAFETY_HEADERS)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="attachment",
        headers=_SAFETY_HEADERS,
    )
