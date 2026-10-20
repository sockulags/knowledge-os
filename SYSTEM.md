# Knowledge OS system summary

Knowledge OS is a local-first, filesystem-native knowledge store. Markdown files
are authoritative and Git may version them; `indexes/` is derived and
disposable. The package version is in `pyproject.toml`, and the workspace
schema in `knowledge-os.toml` is version `1`. This file is a short summary:
[`docs/architecture.md`](docs/architecture.md) is the complete contract, and
the decisions behind it are in `projects/knowledge-os/decisions/`.

## Ways in

- The `kos` command line (`python -m knowledge_os`) ingests, captures, updates,
  accepts, withdraws, and supersedes decisions, runs the discovery return path,
  creates, moves, renames, and deletes pages and folders, and searches, lints,
  and indexes. See "CLI contract".
- `kos-read` and the desktop app serve one workspace on a loopback-only JSON
  API whose writes call the same core functions. See "Local interface write
  API", "Page templates", "Attachments", and "Structure editing".
- `kos mcp` gives agents tools through the running desktop app and never opens
  a workspace itself. See "Agent access over MCP".
- `skills/` holds the agent skills distributed by the Codex and Claude plugins.

## Rules that hold everywhere

- Every write goes through a core mutation: one workspace advisory lock, a
  staged whole-corpus validation, an exact SHA-256 guard for edits, and an index
  rebuild. Multi-file writes are not crash-atomic; after a reported partial
  failure, repair the canonical Markdown and run `kos lint`, then `kos index`.
- Decisions are created as drafts. Only `kos decision accept` activates one, a
  material change is a new draft followed by `kos supersede`, and agents cannot
  edit decisions.
- Review rules in `knowledge-os.toml` can hold note writes back as
  `proposals/<id>.md` until a person accepts or discards them.
- Templates in `templates/` and files in `assets/` folders are not records.
- Search combines full-text with optional search by meaning. Every result is a
  lead to inspect, not verified knowledge.

## Safe operating loop

1. Read this file, `AGENTS.md`, and `indexes/`.
2. Search with `kos search`; inspect selected records with `kos inspect`.
3. Write only when the current request or repository policy authorizes it, with
   valid metadata and non-empty provenance.
4. Run `kos lint` and `kos index` after changes.
