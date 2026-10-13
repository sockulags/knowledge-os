"""Images and other files attached to pages.

An attachment is an ordinary file stored in an ``assets/`` folder next to the
page that uses it (``projects/<project>/<folder>/assets/<name>``, or
``knowledge/assets/<name>`` for a general page) and linked from the page's
Markdown with a relative path, ``![diagram](assets/diagram.png)`` or
``[report](assets/report.pdf)``. It is not a record: it has no metadata, is
never indexed, and ``kos lint`` ignores it, since the workspace scan reads
only Markdown. For the same reason a Markdown file cannot be attached.

``add_attachment`` stores one file under the workspace lock. Names are
cleaned to lowercase words joined by hyphens with the original extension; a
file whose bytes are already in that ``assets/`` folder is reused instead of
stored twice, and a different file with a taken name gets a numeric suffix.
Nothing is ever overwritten.

A page's attachments are the files in its own folder's ``assets/`` that its
body links to. ``structure.move_record`` moves them along with the page when
no other page links to them, and ``structure.delete_record`` deletes them
with the page on the same condition; a file another page still uses stays
where it is (the moved page's link is rewritten to keep pointing at it).
"""

from __future__ import annotations

import hashlib
import posixpath
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .links import relative_links
from .model import Document, content_sha256
from .workspace import Workspace, WorkspaceError, exclusive_write, workspace_mutation_lock

ATTACHMENTS_DIR = "assets"
#: Largest file the interface attaches. Git keeps every version of a file, so
#: large media belongs somewhere else.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024
#: Roots whose pages may have attachments: the types the interface creates.
_ROOTS = ("projects", "knowledge", "memory")
_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_EXTENSION = re.compile(r"^[a-z0-9]{1,10}$")


class AttachmentError(ValueError):
    """A user-actionable refusal; nothing was written."""


@dataclass(frozen=True)
class Attachment:
    path: str  # workspace-relative
    link: str  # relative to the page's folder, e.g. "assets/diagram.png"
    sha256: str
    created: bool  # False when an identical file was already there


def clean_filename(name: str) -> str:
    """``"Skärmbild 2026-09-27 kl. 10.03.PNG"`` -> ``"skarmbild-2026-09-27-kl-10-03.png"``."""

    base = posixpath.basename(name.replace("\\", "/")).strip()
    stem, dot, extension = base.rpartition(".")
    if not dot or not stem:
        stem, extension = base, ""
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^a-z0-9]+", "-", ascii_stem.lower()).strip("-")[:80].strip("-") or "file"
    extension = extension.lower()
    if extension and not _EXTENSION.fullmatch(extension):
        extension = ""
    return f"{stem}.{extension}" if extension else stem


def is_attachment_path(relative: str) -> bool:
    """Whether a workspace-relative path names a file inside an ``assets/``
    folder of a page root (``projects/``, ``knowledge/``, ``memory/``)."""

    parts = relative.split("/")
    return (
        len(parts) >= 3
        and parts[0] in _ROOTS
        and parts[-2] == ATTACHMENTS_DIR
        and all(part not in {"", ".", ".."} for part in parts)
        and posixpath.splitext(parts[-1])[1].lower() not in _MARKDOWN_SUFFIXES
    )


def page_directory(relative_page_path: str) -> str:
    return posixpath.dirname(relative_page_path)


def _check_directory(workspace: Workspace, directory: str) -> Path:
    parts = directory.split("/")
    if not directory or parts[0] not in _ROOTS or any(part in {"", ".", ".."} for part in parts):
        raise AttachmentError(
            f"{directory!r} is not a page folder; files can be attached to pages in projects/, knowledge/, or memory/"
        )
    if ATTACHMENTS_DIR in parts:
        raise AttachmentError(f"{directory!r} is inside an {ATTACHMENTS_DIR}/ folder; attach to the page's own folder")
    if parts[0] == "projects" and len(parts) < 2:
        raise AttachmentError("attach files to a page inside a project, not to projects/ itself")
    path = workspace.root / directory
    try:
        workspace.assert_safe_path(path)
    except WorkspaceError as exc:
        raise AttachmentError(str(exc)) from exc
    if not path.is_dir():
        raise AttachmentError(f"folder not found: {directory}")
    return path


def add_attachment(workspace: Workspace, directory: str, filename: str, data: bytes) -> Attachment:
    """Store ``data`` in ``<directory>/assets/`` and say how the page links to it.

    ``directory`` is the workspace-relative folder of the page that uses the
    file. An identical file already in that ``assets/`` folder is reused.
    """

    if not isinstance(data, (bytes, bytearray)) or not data:
        raise AttachmentError("the file is empty")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise AttachmentError(
            f"the file is larger than {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB; keep large media outside the "
            "knowledge base and link to it"
        )
    name = clean_filename(filename)
    if posixpath.splitext(name)[1] in _MARKDOWN_SUFFIXES:
        raise AttachmentError("a Markdown file cannot be attached; create a page instead")
    with workspace_mutation_lock(workspace):
        page_folder = _check_directory(workspace, directory)
        assets = page_folder / ATTACHMENTS_DIR
        try:
            workspace.assert_safe_path(assets)
        except WorkspaceError as exc:
            raise AttachmentError(str(exc)) from exc
        if assets.exists() and not assets.is_dir():
            raise AttachmentError(f"{directory}/{ATTACHMENTS_DIR} exists and is not a folder")
        digest = hashlib.sha256(data).hexdigest()
        if assets.is_dir():
            for existing in sorted(assets.iterdir(), key=lambda item: item.name):
                if existing.is_file() and not existing.is_symlink() and existing.stat().st_size == len(data):
                    if content_sha256(existing) == digest:
                        return _attachment(directory, existing.name, digest, created=False)
        stem, dot, extension = name.rpartition(".")
        if not dot:
            stem, extension = name, ""
        candidate = name
        counter = 2
        while (assets / candidate).exists() or (assets / candidate).is_symlink():
            candidate = f"{stem}-{counter}.{extension}" if extension else f"{stem}-{counter}"
            counter += 1
        exclusive_write(assets / candidate, bytes(data))
        return _attachment(directory, candidate, digest, created=True)


def _attachment(directory: str, name: str, digest: str, *, created: bool) -> Attachment:
    return Attachment(f"{directory}/{ATTACHMENTS_DIR}/{name}", f"{ATTACHMENTS_DIR}/{name}", digest, created)


def linked_attachments(workspace: Workspace, document: Document) -> list[str]:
    """The files in the page's own ``assets/`` folder that its body links to,
    workspace-relative, in link order without repeats."""

    page_path = workspace.relative(document.path)
    own_assets = f"{page_directory(page_path)}/{ATTACHMENTS_DIR}/"
    found: list[str] = []
    for target, _fragment in relative_links(document.body, page_path):
        if target in found or not target.startswith(own_assets) or "/" in target[len(own_assets) :]:
            continue
        if not is_attachment_path(target):
            continue
        path = workspace.root / target
        if path.is_file() and not path.is_symlink():
            found.append(target)
    return found


def linking_pages(workspace: Workspace, documents: list[Document], target: str) -> list[Document]:
    """Every record whose body links to the workspace-relative ``target``."""

    return [
        document
        for document in documents
        if any(link == target for link, _ in relative_links(document.body, workspace.relative(document.path)))
    ]


def split_by_use(
    workspace: Workspace, documents: list[Document], pages: list[Document]
) -> tuple[list[str], list[str]]:
    """The attachments of ``pages`` that only they use, and those another page
    also links to (which must stay where they are)."""

    page_ids = {document.metadata["id"] for document in pages}
    own: list[str] = []
    shared: list[str] = []
    for page in pages:
        for target in linked_attachments(workspace, page):
            if target in own or target in shared:
                continue
            others = [doc for doc in linking_pages(workspace, documents, target) if doc.metadata["id"] not in page_ids]
            (shared if others else own).append(target)
    return own, shared
