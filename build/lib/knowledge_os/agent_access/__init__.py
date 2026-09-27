"""The MCP server for agents (``kos mcp``), issue #59.

Implements the accepted ``agent-access`` decision: agents such as Claude Code
and Codex get a narrow tool surface (search, read, list, write notes, propose
decisions as drafts) and nothing that accepts, withdraws, or supersedes a
decision. The server never opens a workspace itself. Every tool call reads the
desktop app's runtime file (``runtime.py``), checks that the core it names is
still the one answering, and calls that core's local JSON API
(``local_api.py``), so agent writes get the same validation, SHA-256 conflict
checks, and Git auto-commits as a person's edits in the app.

``runtime``, ``local_api``, and ``tools`` use the standard library only; the
MCP protocol itself comes from the official Python SDK in ``server.py``
(the optional ``mcp`` extra, bundled in the desktop app's frozen core).
"""
