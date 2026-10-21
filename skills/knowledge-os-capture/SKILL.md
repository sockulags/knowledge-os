---
name: knowledge-os-capture
description: Use when a conversation settles a decision, teaches a reusable lesson, or shows a recurring preference worth keeping, or when the user says "save this decision", "remember this", "save this", or "spara detta"; it batches approval-gated proposals and saves only approved records to the Knowledge OS knowledge base. Not for chatter, tentative ideas, one-off tasks, transient facts, or unverified claims; not for setting up or updating repository documentation (use knowledge-os-documentation), importing a file (use ingest-source), or judging an external agent's observation (use review-discovery).
---

# Knowledge OS capture

Keep possible durable content to yourself until a natural pause. Across ordinary conversations,
notice only:

- a settled decision that will shape later work;
- a reusable lesson or recurring preference supported by the conversation.

Do not notice ordinary chatter, a one-off task or fact, a tentative idea, or an uncertain claim as
durable knowledge. Do not interrupt active work to propose a record. At a natural pause, batch the
short list rather than proposing after every message. Each proposal must say **what** would be
recorded, the **destination and scope**, and **why** it is durable. Let the user approve, edit, or
decline each item. `save this` or `spara detta` is direct save intent; ask only when the content or
destination is materially ambiguous. Approval of a proposal is the approval to capture it; do not
add another approval ceremony.

## Capture boundary

Never write before approval. If no item is approved, do not create a candidate file and do not call
Knowledge OS. Do not use Agentic Work OS, a daemon, hook, cloud service, background worker, silent
save, model verification, or fact checking. The only server this skill uses is the Knowledge OS MCP
server, and only after approval. Saving preserves the conversation's provenance and uncertainty;
it does not verify the claim.

## Capture with the Knowledge OS MCP tools

When the `knowledge-os` MCP server's tools are available in this session (the plugin registers
the server), capture through them. They write to the knowledge base open in the Knowledge OS
desktop app, with its validation, conflict checks, and a Git commit that names this agent, and
they record this agent as the author in provenance. They need no Python setup.

1. Before proposing, `search`, `list_proposed_changes` (writes already waiting for review), and
   `list_proposed_decisions` for decisions, so a proposal extends or points at what already exists
   or waits instead of duplicating it. `read_proposed_change` shows a waiting change in full. Use
   `list_projects` to name the destination project in the proposal.
2. After approval, save an approved lesson or preference with `write_note` (title, content,
   project and folder when it belongs to a project, `status: draft` unless the person asked for it
   to be current). Save a standing preference or working agreement with `destination: memory`
   (and `project` when it applies to one project). To change an existing page, `read_page` it
   and send the complete new content with its `content_sha256` as `expected_sha256`.
3. Save an approved decision with `propose_decision`, with `supersedes` when it replaces a decision
   in force. It is stored as a proposal that governs nothing until the person accepts it in the
   app's Decide inbox; say so. There is no tool to accept, withdraw, or supersede, and approval to
   save is not acceptance.
4. When a write returns `action: waiting_for_review`, it is not saved: the knowledge base's review
   rules held it back, nothing is written yet, and the page is unchanged or does not exist. Tell the
   person that the change waits in the app's Decide inbox, where they accept or discard it, and
   name the `rule` from the result. Do not say it was saved and do not write it again.
5. Otherwise report the returned `id`, `path`, and whether `commit.committed` is true. A
   `conflict`, `duplicate`, or `validation` result wrote nothing; follow its `next_step`.

If a tool reports `app_not_open` or `app_not_responding`, nothing was written: tell the person to
open the Knowledge OS app with their knowledge base and offer to save again then. Do not fall back
to the CLI to write while the app is closed.

## CLI fallback

Only when the MCP tools are not available in this session, capture through the command line.
Every command runs as `<python> -m knowledge_os --root <root> ...`, never as a bare `kos`, with the
workspace root taken from `KNOWLEDGE_OS_ROOT` or `~/.knowledge-os/config.toml`, never from the
conversation's working directory.

- Read [references/setup.md](references/setup.md) only when you need the Python launcher, the
  workspace root, or the one-time install of the companion CLI.
- Read [references/cli-fallback.md](references/cli-fallback.md) only after an item is approved and
  you are about to write the candidate file and run `capture` (decisions included).
