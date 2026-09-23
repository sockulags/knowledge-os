"""Who an agent write came from: the ``agent-authored`` provenance kind.

The accepted ``agent-access`` decision gives every write an agent makes
through the MCP server (``knowledge_os.agent_access``) a provenance entry
that names the agent and where it ran:

    {"kind": "agent-authored", "reference": "agent:<client>:<place>",
     "captured": "<UTC timestamp>"}

``<client>`` is the MCP client's own name from its ``clientInfo`` (for
example ``claude-code``) and ``<place>`` a short label for where the agent
ran: a configured label or the name of its working directory, never a full
path. ``:<place>`` is left out when there is no place. Both parts are cleaned
to letters, digits, spaces, ``.``, ``_``, and ``-`` so a reference always
splits back into the same two parts.

Like every provenance kind except ``record``, ``discovery``,
``decision-acceptance``, and ``decision-withdrawal``, the kind is opaque to
the core: lint does not resolve the reference. The local write API accepts it
from any caller that holds the write token; it labels agent work, it does not
prove it. This module has no dependencies so the reader (display, commit
messages) and the MCP server (building the identity) share one definition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

AGENT_PROVENANCE_KIND = "agent-authored"
_REFERENCE_PREFIX = "agent:"
_LABEL_LIMIT = 60

#: MCP ``clientInfo.name`` -> the name people know the agent by. A client not
#: listed here is shown by its own (cleaned) name.
KNOWN_AGENT_NAMES: dict[str, str] = {
    "claude-code": "Claude Code",
    "claude-ai": "Claude",
    "codex": "Codex",
    "codex-mcp-client": "Codex",
    "codex-cli": "Codex",
}

_UNSAFE = re.compile(r"[^\w .-]+", re.UNICODE)
_RUNS = re.compile(r"[\s]+")


def clean_label(value: object) -> str:
    """One reference part: safe characters only, single spaces, at most 60
    characters. Returns ``""`` when nothing usable is left."""

    if not isinstance(value, str):
        return ""
    text = _UNSAFE.sub("-", value)
    text = _RUNS.sub(" ", text).strip(" .-_")
    return text[:_LABEL_LIMIT].strip(" .-_")


@dataclass(frozen=True)
class AgentIdentity:
    """A cleaned agent client name and optional place."""

    client: str
    place: str | None = None

    @classmethod
    def create(cls, client: object, place: object = None) -> AgentIdentity | None:
        """Clean both parts; ``None`` when the client name is empty after cleaning."""

        cleaned = clean_label(client)
        if not cleaned:
            return None
        return cls(cleaned, clean_label(place) or None)

    @property
    def reference(self) -> str:
        return f"{_REFERENCE_PREFIX}{self.client}" + (f":{self.place}" if self.place else "")

    @property
    def display_name(self) -> str:
        return agent_display_name(self.client)

    def provenance_entry(self, now: datetime | None = None) -> dict[str, str]:
        stamp = (now or datetime.now(UTC)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        return {"kind": AGENT_PROVENANCE_KIND, "reference": self.reference, "captured": stamp}


def agent_display_name(client: str) -> str:
    return KNOWN_AGENT_NAMES.get(client.lower(), client)


def parse_agent_reference(reference: str) -> AgentIdentity | None:
    """``agent:<client>[:<place>]`` back into its parts; ``None`` when the
    reference does not have that shape."""

    if not reference.startswith(_REFERENCE_PREFIX):
        return None
    client, _, place = reference[len(_REFERENCE_PREFIX) :].partition(":")
    if not client or clean_label(client) != client or (place and clean_label(place) != place):
        return None
    return AgentIdentity(client, place or None)
