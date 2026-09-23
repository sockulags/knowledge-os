"""The agent tools: what each one takes, what it does, and what it returns.

Each tool is plain data in and out, independent of the MCP protocol layer:
``call_tool(name, arguments, caller)`` finds the running app, calls its local
API, and returns a ``ToolResult`` whose ``data`` is a JSON object. Failures
are results too (``is_error``), shaped ``{"ok": false, "error": KIND,
"message", "next_step", "written"}`` so an agent can act on them:

- ``app_not_open``: no knowledge base is open in the app (or the app is
  closed). Nothing was written.
- ``app_not_responding``: a runtime file exists but no running app answers
  for it. Nothing was written.
- ``request_failed``: the app stopped answering during a request. A write may
  or may not have happened; read the page again before retrying.
- ``not_found``, ``conflict`` (adds ``current_sha256``), ``duplicate``,
  ``validation`` (adds ``issues``), ``bad_request``, ``forbidden``,
  ``not_allowed``, ``search_unavailable``: refused, nothing was written.

There is deliberately no tool that accepts, withdraws, or supersedes a
decision (the ``agent-access`` decision): those stay human actions in the app
or the command line. ``write_note`` refuses to edit decisions for the same
reason, and ``propose_decision`` always creates a draft.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .local_api import LocalApi, quote
from .runtime import AppUnavailable, RuntimeInfo, connect

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_TAG = re.compile(r"<[^>]+>")
_SEARCH_LIMIT_DEFAULT = 10
_SEARCH_LIMIT_MAX = 50


@dataclass(frozen=True)
class Caller:
    """Who is calling: the MCP client's name (``clientInfo.name``) and where
    it runs (a configured label or its working directory's name)."""

    client: str
    place: str | None

    def agent_json(self) -> dict[str, str | None]:
        return {"client": self.client, "place": self.place}


@dataclass(frozen=True)
class ToolResult:
    data: dict[str, Any]
    is_error: bool = False


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool
    handler: Callable[[LocalApi, dict[str, Any], Caller], ToolResult] = field(repr=False)


class ToolError(Exception):
    def __init__(self, kind: str, message: str, next_step: str, **extra: Any):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.next_step = next_step
        self.extra = extra


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

_APP_NEXT_STEP = {
    "app_not_open": (
        "Ask the person to open the Knowledge OS app and open a knowledge base, then try again. "
        "The knowledge base is only available to agents while the app has it open."
    ),
    "app_not_responding": (
        "Ask the person to open (or restart) the Knowledge OS app with a knowledge base open, then try again."
    ),
    "request_failed": (
        "Ask the person to check that the Knowledge OS app is still open. Read the page again before retrying, "
        "because the write may already have happened."
    ),
}

_API_NEXT_STEP = {
    "bad_request": "Fix the arguments and call the tool again.",
    "forbidden": "The app refused the request. Ask the person to restart the Knowledge OS app, then try again.",
    "not_found": "Use search, list_projects, or list_folder to find the right id.",
    "conflict": (
        "The page changed after you read it. Call read_page again, apply your change to the new content, "
        "and send the new content_sha256 as expected_sha256."
    ),
    "duplicate": (
        "A page with this id or at this place already exists. Pick another id, or read_page that id and "
        "edit it with its content_sha256."
    ),
    "validation": "Fix what the message and issues describe, then call the tool again.",
}


def _error(kind: str, message: str, next_step: str, *, written: bool | str = False, **extra: Any) -> ToolResult:
    return ToolResult({"ok": False, "error": kind, "message": message, "next_step": next_step, "written": written, **extra}, True)


def _api_error(status: int, body: Any) -> ToolError:
    body = body if isinstance(body, dict) else {}
    kind = body.get("error")
    if kind not in _API_NEXT_STEP:
        kind = {400: "bad_request", 403: "forbidden", 404: "not_found", 409: "conflict", 422: "validation"}.get(
            status, "unexpected"
        )
    message = str(body.get("detail") or f"The app answered with HTTP {status}.")
    extra: dict[str, Any] = {}
    if "current_sha256" in body:
        extra["current_sha256"] = body["current_sha256"]
    if body.get("issues"):
        extra["issues"] = body["issues"]
    next_step = _API_NEXT_STEP.get(kind, "Report this to the person; the app answered unexpectedly.")
    return ToolError(kind, message, next_step, **extra)


def _expect(status_and_body: tuple[int, Any], *ok: int) -> Any:
    status, body = status_and_body
    if status not in ok:
        raise _api_error(status, body)
    return body


# ---------------------------------------------------------------------------
# Argument helpers
# ---------------------------------------------------------------------------


def _string(arguments: Mapping[str, Any], name: str, *, required: bool = False) -> str | None:
    value = arguments.get(name)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolError("bad_request", f"{name} is required.", _API_NEXT_STEP["bad_request"])
        return None
    if not isinstance(value, str):
        raise ToolError("bad_request", f"{name} must be a string.", _API_NEXT_STEP["bad_request"])
    return value.strip()


def _string_list(arguments: Mapping[str, Any], name: str) -> list[str] | None:
    value = arguments.get(name)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ToolError("bad_request", f"{name} must be a list of strings.", _API_NEXT_STEP["bad_request"])
    return [item.strip() for item in value if item.strip()]


def _record_id(value: str, name: str = "id") -> str:
    if not ID_PATTERN.fullmatch(value):
        raise ToolError(
            "bad_request",
            f"{name} {value!r} is not a valid id: use lowercase letters, digits, and single hyphens, e.g. 'retry-policy'.",
            _API_NEXT_STEP["bad_request"],
        )
    return value


def slug(title: str) -> str:
    """A page id from a title: lowercase ASCII words joined by hyphens."""

    text = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    text = text[:80].rstrip("-")
    return text or "note"


def _folder(value: str | None) -> str | None:
    if value is None:
        return None
    parts = [part for part in value.replace("\\", "/").split("/") if part]
    if not parts or any(part in {".", ".."} for part in parts):
        raise ToolError("bad_request", f"folder {value!r} is not a folder inside the project.", _API_NEXT_STEP["bad_request"])
    return "/".join(parts)


def _scope(project: str | None) -> tuple[str, str]:
    """(type, scope) for a page in a project or, without one, general knowledge."""

    if project is None or project == "general":
        return "knowledge", "general"
    return "project", f"project:{_record_id(project, 'project')}"


def _commit_json(commit: Any) -> dict[str, Any] | None:
    if not isinstance(commit, dict):
        return None
    return {key: commit.get(key) for key in ("committed", "sha", "message", "skipped")}


def _plain(snippet_html: str) -> str:
    return html.unescape(_TAG.sub("", snippet_html))


_DECISION_STATE = {"draft": "proposed", "active": "in force", "superseded": "replaced", "archived": "withdrawn"}


def _state(is_decision: bool, status: str | None) -> str | None:
    if status is None:
        return None
    return _DECISION_STATE.get(status, status) if is_decision else status


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _search(api: LocalApi, arguments: dict[str, Any], _caller: Caller) -> ToolResult:
    query = _string(arguments, "query", required=True)
    project = _string(arguments, "project")
    limit = arguments.get("limit", _SEARCH_LIMIT_DEFAULT)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= _SEARCH_LIMIT_MAX:
        raise ToolError("bad_request", f"limit must be a whole number from 1 to {_SEARCH_LIMIT_MAX}.", _API_NEXT_STEP["bad_request"])
    params = {"q": query or ""}
    if project is not None:
        params["scope"] = _scope(project)[1]
    body = _expect(api.get("/api/search", params), 200)
    if not body.get("search_available", True):
        raise ToolError(
            "search_unavailable",
            str(body.get("disabled_reason") or "Search is not available in this knowledge base right now."),
            "Browse with list_projects and list_folder instead, and tell the person the app reports a problem with the knowledge base.",
        )
    rows = body.get("results") or []
    results = [
        {
            "id": row.get("id"),
            "title": row.get("title"),
            "kind": "decision" if row.get("record_kind") == "decision" else row.get("type"),
            "state": _state(row.get("record_kind") == "decision", row.get("status")),
            "trust": row.get("trust_label") or None,
            "project": row.get("project_id") or "general",
            "snippet": _plain(str(row.get("snippet_html") or "")),
        }
        for row in rows[:limit]
    ]
    return ToolResult(
        {
            "ok": True,
            "query": query,
            "count": len(results),
            "results": results,
            "note": "Search results are leads, not verified facts. Use read_page for the full text and its state.",
        }
    )


def _read_page(api: LocalApi, arguments: dict[str, Any], _caller: Caller) -> ToolResult:
    record_id = _record_id(_string(arguments, "id", required=True) or "")
    body = _expect(api.get(f"/api/records/{quote(record_id)}"), 200)
    editing = body.get("editing") or {}
    details = body.get("technical_details") or {}
    metadata = editing.get("metadata") or {}
    is_decision = bool(body.get("is_decision"))
    return ToolResult(
        {
            "ok": True,
            "id": body.get("id"),
            "title": body.get("title"),
            "kind": "decision" if is_decision else body.get("type"),
            "type": body.get("type"),
            "state": _state(is_decision, details.get("status")),
            "trust": details.get("trust_label"),
            "project": editing.get("project_id") or "general",
            "folder": editing.get("folder") or "",
            "path": details.get("path") or editing.get("path"),
            "content": editing.get("raw_body"),
            "content_sha256": editing.get("content_sha256") or details.get("content_sha256"),
            "tags": metadata.get("tags", []),
            "related": metadata.get("related", []),
            "sources": metadata.get("sources", []),
            "provenance": [
                {key: entry.get(key) for key in ("kind", "reference", "captured") if entry.get(key) is not None}
                for entry in details.get("provenance") or []
            ],
            "editable_with_write_note": bool(editing.get("editable")) and not is_decision,
        }
    )


def _nav(api: LocalApi) -> dict[str, Any]:
    return _expect(api.get("/api/nav"), 200)


def _list_projects(api: LocalApi, _arguments: dict[str, Any], _caller: Caller) -> ToolResult:
    nav = _nav(api)
    projects = [
        {
            "id": project.get("id"),
            "title": project.get("title"),
            "folders": [child.get("name") for child in (project.get("tree") or {}).get("children") or []],
        }
        for project in nav.get("projects") or []
    ]
    return ToolResult(
        {
            "ok": True,
            "knowledge_base": nav.get("workspace_name"),
            "projects": projects,
            "note": "Knowledge that applies everywhere (project 'general') is not in a project folder; find it with search.",
        }
    )


def _page_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    is_decision = bool(entry.get("is_decision"))
    pill = entry.get("status_pill") or {}
    return {
        "id": entry.get("id"),
        "title": entry.get("title"),
        "kind": "decision" if is_decision else entry.get("type"),
        "state": pill.get("label"),
    }


def _list_folder(api: LocalApi, arguments: dict[str, Any], _caller: Caller) -> ToolResult:
    project_id = _record_id(_string(arguments, "project", required=True) or "", "project")
    folder = _folder(_string(arguments, "folder")) or ""
    nav = _nav(api)
    project = next((p for p in nav.get("projects") or [] if p.get("id") == project_id), None)
    if project is None:
        known = [p.get("id") for p in nav.get("projects") or []]
        raise ToolError(
            "not_found", f"There is no project {project_id!r}. Projects: {', '.join(known) or 'none'}.", _API_NEXT_STEP["not_found"]
        )
    node = project.get("tree") or {}
    for part in folder.split("/") if folder else []:
        child = next((c for c in node.get("children") or [] if c.get("name") == part), None)
        if child is None:
            names = [c.get("name") for c in node.get("children") or []]
            raise ToolError(
                "not_found",
                f"Project {project_id!r} has no folder {folder!r}. Folders here: {', '.join(names) or 'none'}.",
                _API_NEXT_STEP["not_found"],
            )
        node = child
    overview = node.get("overview")
    return ToolResult(
        {
            "ok": True,
            "project": project_id,
            "project_title": project.get("title"),
            "folder": folder,
            "overview": _page_entry(overview) if overview else None,
            "pages": [_page_entry(entry) for entry in node.get("records") or []],
            "folders": [child.get("name") for child in node.get("children") or []],
        }
    )


def _list_proposed_decisions(api: LocalApi, arguments: dict[str, Any], _caller: Caller) -> ToolResult:
    project = _string(arguments, "project")
    params = {"project": project} if project else None
    body = _expect(api.get("/api/decisions/proposed", params), 200)
    items = [
        {
            "id": item.get("id"),
            "title": item.get("title"),
            "project": (item.get("project") or {}).get("id") or "general",
            "proposed_by": (item.get("proposed_by") or {}).get("label"),
            "proposed_at": item.get("proposed_at"),
            "replaces": (
                {"id": item["replaces"].get("id"), "title": item["replaces"].get("title")} if item.get("replaces") else None
            ),
            "excerpt": item.get("excerpt"),
        }
        for item in body.get("items") or []
    ]
    return ToolResult(
        {
            "ok": True,
            "count": len(items),
            "decisions": items,
            "note": "These are proposals. None governs anything until a person accepts it in the Knowledge OS app.",
        }
    )


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _write_result(action: str, body: Mapping[str, Any], **extra: Any) -> ToolResult:
    index = body.get("index") or {}
    data: dict[str, Any] = {
        "ok": True,
        "action": action,
        "id": body.get("id"),
        "path": body.get("path"),
        "state": body.get("status"),
        "content_sha256": body.get("content_sha256"),
        "commit": _commit_json(body.get("commit")),
        **extra,
    }
    if index.get("error"):
        data["index_warning"] = index["error"]
    return ToolResult(data)


def _write_note(api: LocalApi, arguments: dict[str, Any], caller: Caller) -> ToolResult:
    content = arguments.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ToolError("bad_request", "content is required: the page's Markdown text.", _API_NEXT_STEP["bad_request"])
    title = _string(arguments, "title")
    tags = _string_list(arguments, "tags")
    expected = _string(arguments, "expected_sha256")
    given_id = _string(arguments, "id")

    if expected is not None:
        if given_id is None:
            raise ToolError("bad_request", "id is required when expected_sha256 is given (editing a page).", _API_NEXT_STEP["bad_request"])
        record_id = _record_id(given_id)
        for name in ("project", "folder", "status"):
            if arguments.get(name) is not None:
                raise ToolError(
                    "bad_request",
                    f"{name} can only be set when creating a page, not when editing one.",
                    _API_NEXT_STEP["bad_request"],
                )
        current = _expect(api.get(f"/api/records/{quote(record_id)}"), 200)
        if current.get("is_decision"):
            raise ToolError(
                "not_allowed",
                f"{record_id!r} is a decision. Agents cannot edit decisions.",
                "To change a decision, call propose_decision with supersedes set to its id; a person decides whether to accept it.",
            )
        if not (current.get("editing") or {}).get("editable"):
            raise ToolError(
                "not_allowed",
                f"{record_id!r} is a {current.get('type')} page, which cannot be edited here.",
                "Write a new note instead, and link it with related if that helps.",
            )
        changes: dict[str, Any] = {}
        if title is not None:
            changes["title"] = title
        if tags is not None:
            changes["tags"] = tags
        payload: dict[str, Any] = {"expected_sha256": expected, "body": content, "agent": caller.agent_json()}
        if changes:
            payload["metadata"] = changes
        body = _expect(api.patch(f"/api/records/{quote(record_id)}", payload), 200)
        return _write_result("updated", body)

    if title is None:
        raise ToolError("bad_request", "title is required when creating a page.", _API_NEXT_STEP["bad_request"])
    record_id = _record_id(given_id) if given_id is not None else slug(title)
    project = _string(arguments, "project")
    folder = _folder(_string(arguments, "folder"))
    status = _string(arguments, "status") or "active"
    if status not in {"active", "draft"}:
        raise ToolError("bad_request", "status must be 'active' or 'draft'.", _API_NEXT_STEP["bad_request"])
    record_type, scope = _scope(project)
    if folder is not None and record_type != "project":
        raise ToolError("bad_request", "folder needs a project: general knowledge has no folders.", _API_NEXT_STEP["bad_request"])
    metadata: dict[str, Any] = {"id": record_id, "title": title, "type": record_type, "status": status, "scope": scope}
    if tags:
        metadata["tags"] = tags
    payload = {"metadata": metadata, "body": content, "agent": caller.agent_json()}
    if folder is not None:
        payload["project_path"] = f"{folder}/{record_id}.md"
    body = _expect(api.post("/api/records", payload), 201)
    return _write_result("created", body)


def _propose_decision(api: LocalApi, arguments: dict[str, Any], caller: Caller) -> ToolResult:
    title = _string(arguments, "title", required=True) or ""
    content = arguments.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ToolError("bad_request", "content is required: the decision's Markdown text.", _API_NEXT_STEP["bad_request"])
    record_id = _record_id(_string(arguments, "id") or slug(title))
    project = _string(arguments, "project")
    record_type, scope = _scope(project)
    folder = _folder(_string(arguments, "folder"))
    if folder is not None and record_type != "project":
        raise ToolError("bad_request", "folder needs a project: general decisions have no folders.", _API_NEXT_STEP["bad_request"])
    if folder is None and record_type == "project":
        folder = "decisions"
    metadata: dict[str, Any] = {
        "id": record_id,
        "title": title,
        "type": record_type,
        "record_kind": "decision",
        "status": "draft",
        "scope": scope,
    }
    supersedes = _string(arguments, "supersedes")
    if supersedes is not None:
        metadata["supersedes"] = [_record_id(supersedes, "supersedes")]
    related = _string_list(arguments, "related")
    if related:
        metadata["related"] = [_record_id(item, "related") for item in related]
    tags = _string_list(arguments, "tags")
    if tags:
        metadata["tags"] = tags
    payload: dict[str, Any] = {"metadata": metadata, "body": content, "agent": caller.agent_json()}
    if folder is not None:
        payload["project_path"] = f"{folder}/{record_id}.md"
    body = _expect(api.post("/api/records", payload), 201)
    return _write_result(
        "proposed",
        body,
        next_step=(
            "Nothing more to do: the decision waits in the Knowledge OS app's Decide inbox. It governs nothing "
            "until a person accepts it there; agents cannot accept, withdraw, or supersede decisions."
        ),
    )


# ---------------------------------------------------------------------------
# The tool table
# ---------------------------------------------------------------------------

_PROJECT_ARG = {
    "type": "string",
    "description": "Project id (see list_projects), or 'general' for knowledge that applies everywhere.",
}

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="search",
        title="Search the knowledge base",
        description=(
            "Full-text search of the knowledge base open in the Knowledge OS app: notes, documentation, and "
            "decisions. Returns ids, titles, kind, state (for decisions: proposed, in force, replaced, "
            "withdrawn), and a snippet. Results are leads, not verified facts; read_page gives the full text. "
            "Search before writing so you extend an existing page instead of duplicating it."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Words to look for."},
                "project": {**_PROJECT_ARG, "description": "Only search this project ('general' for knowledge that applies everywhere)."},
                "limit": {"type": "integer", "minimum": 1, "maximum": _SEARCH_LIMIT_MAX, "default": _SEARCH_LIMIT_DEFAULT},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        read_only=True,
        handler=_search,
    ),
    ToolSpec(
        name="read_page",
        title="Read a page",
        description=(
            "Read one page (note, documentation, or decision) by id: its Markdown content, title, kind, state, "
            "project, folder, tags, links, provenance, and content_sha256. To edit the page with write_note, "
            "send that content_sha256 back as expected_sha256."
        ),
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "The page id, e.g. from search or list_folder."}},
            "required": ["id"],
            "additionalProperties": False,
        },
        read_only=True,
        handler=_read_page,
    ),
    ToolSpec(
        name="list_projects",
        title="List projects",
        description=(
            "List the projects in the knowledge base open in the Knowledge OS app, with each project's id, "
            "title, and top-level folders. Use a project id with list_folder, search, write_note, and "
            "propose_decision."
        ),
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        read_only=True,
        handler=_list_projects,
    ),
    ToolSpec(
        name="list_folder",
        title="List a project folder",
        description=(
            "List what is in one folder of a project: its overview page, the pages in it (id, title, kind, "
            "state), and its subfolders. Leave folder empty for the project's top level."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Project id from list_projects."},
                "folder": {"type": "string", "description": "Folder path inside the project, e.g. 'architecture' or 'architecture/api'."},
            },
            "required": ["project"],
            "additionalProperties": False,
        },
        read_only=True,
        handler=_list_folder,
    ),
    ToolSpec(
        name="write_note",
        title="Write a note",
        description=(
            "Create a note or documentation page, or edit one. Notes are saved directly and committed to the "
            "knowledge base's Git history under your agent's name. To create, give title and content (plus "
            "project and folder to place it; without a project it is general knowledge). To edit, give the "
            "page's id, the complete new content, and expected_sha256 = the content_sha256 from read_page; a "
            "stale hash is refused as a conflict and nothing is written. Decisions cannot be written or edited "
            "here: use propose_decision."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The page's complete Markdown text (without front matter)."},
                "title": {"type": "string", "description": "Page title. Required when creating; optional when editing."},
                "id": {
                    "type": "string",
                    "description": "Page id (lowercase-kebab). Required when editing. When creating it defaults to one made from the title.",
                },
                "expected_sha256": {
                    "type": "string",
                    "description": "Only when editing: the content_sha256 read_page returned for the version you changed.",
                },
                "project": {**_PROJECT_ARG, "description": "Only when creating: the project the note belongs to. Omit for general knowledge."},
                "folder": {"type": "string", "description": "Only when creating in a project: folder path inside the project, e.g. 'architecture'."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
                "status": {
                    "type": "string",
                    "enum": ["active", "draft"],
                    "description": "Only when creating: 'active' (default) or 'draft' for unfinished notes.",
                },
            },
            "required": ["content"],
            "additionalProperties": False,
        },
        read_only=False,
        handler=_write_note,
    ),
    ToolSpec(
        name="propose_decision",
        title="Propose a decision",
        description=(
            "Propose a decision for a person to accept or withdraw in the Knowledge OS app. It is always saved "
            "as a draft (proposed), labelled with your agent's name, and governs nothing until a person accepts "
            "it; no tool can accept it. Use supersedes to propose replacing a decision that is in force. Write "
            "the content as '## Decision' (what is decided) and '## Why' (the reasons), plus anything the "
            "person needs to judge it."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short statement of the decision."},
                "content": {"type": "string", "description": "The decision's Markdown text (without front matter)."},
                "project": {**_PROJECT_ARG, "description": "The project it governs. Omit for a decision that applies everywhere."},
                "folder": {"type": "string", "description": "Folder inside the project (default 'decisions')."},
                "id": {"type": "string", "description": "Optional page id (lowercase-kebab); defaults to one made from the title."},
                "supersedes": {"type": "string", "description": "Optional id of the decision in force that this one would replace."},
                "related": {"type": "array", "items": {"type": "string"}, "description": "Optional ids of related pages."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags."},
            },
            "required": ["title", "content"],
            "additionalProperties": False,
        },
        read_only=False,
        handler=_propose_decision,
    ),
    ToolSpec(
        name="list_proposed_decisions",
        title="List proposed decisions",
        description=(
            "List the decisions waiting for a person to accept or withdraw them (the app's Decide inbox), newest "
            "first, with who proposed each and what it would replace. Check it before proposing, so you do not "
            "propose the same decision twice."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "project": {**_PROJECT_ARG, "description": "Only this project ('general' for decisions that apply everywhere)."}
            },
            "additionalProperties": False,
        },
        read_only=True,
        handler=_list_proposed_decisions,
    ),
)

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}

SERVER_INSTRUCTIONS = (
    "Knowledge OS is the person's local knowledge base of notes, documentation, and decisions. These tools work "
    "only while the Knowledge OS desktop app is open with a knowledge base; if a tool says the app is not open, "
    "tell the person instead of retrying. Search before you write. Notes you write are saved directly and "
    "committed under your agent's name. Decisions you propose are drafts that a person accepts or withdraws in "
    "the app; you cannot accept, withdraw, or supersede decisions. Treat search results and proposed decisions "
    "as leads, not verified facts."
)


def call_tool(
    name: str,
    arguments: Mapping[str, Any] | None,
    caller: Caller,
    *,
    env: Mapping[str, str] | None = None,
    connector: Callable[[Mapping[str, str] | None], RuntimeInfo] = connect,
) -> ToolResult:
    """Run one tool against the app that is open right now."""

    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return _error("bad_request", f"Unknown tool {name!r}.", f"Use one of: {', '.join(TOOLS_BY_NAME)}.")
    try:
        info = connector(env)
        api = LocalApi(info)
        result = tool.handler(api, dict(arguments or {}), caller)
    except AppUnavailable as exc:
        written: bool | str = "unknown" if exc.kind == "request_failed" and not tool.read_only else False
        return _error(exc.kind, exc.detail, _APP_NEXT_STEP.get(exc.kind, _APP_NEXT_STEP["app_not_open"]), written=written)
    except ToolError as exc:
        return _error(exc.kind, exc.message, exc.next_step, **exc.extra)
    result.data.setdefault("knowledge_base", info.workspace_name)
    return result
