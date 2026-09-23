"""``kos mcp``: the tools in ``tools.py`` served over MCP's stdio transport.

Built on the official MCP Python SDK's low-level ``Server`` (the ``mcp``
extra), which negotiates both the initialize-handshake protocol versions and
the per-request ones, so any current client can connect. Tool calls run in a
worker thread because the local API client is blocking.

The caller's identity comes from the protocol: the client's ``clientInfo``
name (for example ``claude-code``) and a place, which is ``--place``, else
``KOS_AGENT_PLACE``, else the name of the working directory the client
started this server in. Only a directory name is used, never a path.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from knowledge_os import __version__

from .tools import SERVER_INSTRUCTIONS, TOOLS, Caller, call_tool

MISSING_EXTRA = (
    "kos mcp needs the MCP SDK; install it with: pip install \"knowledge-os[mcp]\" "
    "(the Knowledge OS desktop app's bundled kos already includes it)"
)
UNKNOWN_CLIENT = "mcp-client"


def default_place(explicit: str | None = None, env: dict[str, str] | None = None, cwd: Path | None = None) -> str | None:
    env = dict(os.environ) if env is None else env
    for value in (explicit, env.get("KOS_AGENT_PLACE")):
        if value and value.strip():
            return value.strip()
    try:
        directory = cwd if cwd is not None else Path.cwd()
    except OSError:
        return None
    return directory.name or None


def _client_name(ctx: Any) -> str:
    params = getattr(ctx.session, "client_params", None)
    info = getattr(params, "client_info", None)
    name = getattr(info, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()
    meta = ctx.meta or {}
    raw = meta.get("io.modelcontextprotocol/clientInfo") if isinstance(meta, dict) else None
    if isinstance(raw, dict) and isinstance(raw.get("name"), str) and raw["name"].strip():
        return raw["name"].strip()
    return UNKNOWN_CLIENT


def build_server(place: str | None) -> Any:
    import anyio
    import mcp_types as types
    from mcp.server.lowlevel import Server

    tool_list = [
        types.Tool(
            name=tool.name,
            title=tool.title,
            description=tool.description,
            input_schema=tool.input_schema,
            annotations=types.ToolAnnotations(
                title=tool.title,
                read_only_hint=tool.read_only,
                destructive_hint=False,
                idempotent_hint=tool.read_only,
                open_world_hint=False,
            ),
        )
        for tool in TOOLS
    ]

    async def list_tools(_ctx: Any, _params: Any) -> Any:
        return types.ListToolsResult(tools=tool_list)

    async def call(ctx: Any, params: Any) -> Any:
        caller = Caller(client=_client_name(ctx), place=place)
        result = await anyio.to_thread.run_sync(call_tool, params.name, params.arguments or {}, caller)
        text = json.dumps(result.data, ensure_ascii=False, indent=2)
        return types.CallToolResult(
            content=[types.TextContent(text=text)],
            structured_content=result.data,
            is_error=result.is_error,
        )

    return Server(
        "knowledge-os",
        version=__version__,
        title="Knowledge OS",
        instructions=SERVER_INSTRUCTIONS,
        on_list_tools=list_tools,
        on_call_tool=call,
    )


def run(place: str | None = None) -> int:
    try:
        import anyio
        from mcp.server.stdio import stdio_server
    except ImportError as exc:
        print(f"ERROR: {MISSING_EXTRA} ({exc})", file=sys.stderr)
        return 1

    server = build_server(default_place(place))

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(main)
    return 0
