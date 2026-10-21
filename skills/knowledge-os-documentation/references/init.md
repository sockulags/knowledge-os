# Documentation initialization

Initialization is separate from normal documentation retrieval. Run it only when the user asks to
initialize the requested scope.

## Global initialization

Global initialization installs a short managed block in the user-level Codex
`AGENTS.md` and Claude `CLAUDE.md`. It also writes `~/.knowledge-os/config.toml`.
These are user-level writes, so require direct user authorization immediately before the command.

Use the fixed command contract. `<python>` is the proven Python >=3.11 launcher described in
`skills/knowledge-os-capture/references/setup.md`; never run a bare `kos`. Initialization takes
the workspace or repository as an argument, so these two commands need no `--root`:

```text
<python> -m knowledge_os documentation init-global --workspace PATH [--host codex] [--host claude] [--user-home PATH] [--replace] [--json]
```

Without `--host`, the command writes both managed files, Codex `~/.codex/AGENTS.md` and Claude
`~/.claude/CLAUDE.md`; pass `--host codex` or `--host claude` to write only that one. When asking
for authorization, name the hosts and files the command will write. Use `--user-home PATH` when
the user names a non-default home directory. Use `--replace` only when the user authorizes
replacing an existing managed block. Use `--json` when the caller needs machine-readable results.

The resulting config uses this shape and identifies the Knowledge OS workspace for normal retrieval:

```toml
[knowledge_os]
version = 1
workspace = "C:/path/to/knowledge-os"
```

Global config does not make search results verified. General knowledge and memory remain subject to
task relevance and their recorded lifecycle and provenance.

## Repository initialization

Repository initialization writes `.knowledge-os-project.toml` at the repository root. It accepts
one or more project bindings. Each binding is a project ID with an optional repository-relative
path:

```text
<python> -m knowledge_os documentation init-repo --repo PATH --project ID[=RELATIVE_PATH] [--project ...] [--user-home PATH] [--replace] [--json]
```

The generated binding file has one project entry under `knowledge_os.projects` for each `--project`
option:

```toml
[knowledge_os]
version = 1
workspace_name = "Knowledge OS"
workspace_schema_version = 1

[[knowledge_os.projects]]
id = "knowledge-os"
path = "."

[[knowledge_os.projects]]
id = "shared-library"
path = "packages/shared-library"
```

An omitted path binds the project to the repository root. Paths are relative to the repository and
must remain inside it. A task inside a monorepo uses the binding with the longest matching path.
Missing or ambiguous bindings are safe no-ops during normal documentation work. The explicit
`init-repo` command may create or replace the binding file when authorized by the user.

Use `--user-home PATH` to select the home directory containing the global config. Use `--replace`
only for an authorized replacement. Use `--json` when the caller needs machine-readable results.
