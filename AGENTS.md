# Knowledge OS agent guide

Start with `SYSTEM.md`, `README.md`, and the generated files under `indexes/`. Use `kos search` before recursive reads so context is selected progressively.

- `inbox/` contains untrusted, not-yet-durable material.
- `sources/` contains ingested raw material with provenance; it is not automatically knowledge.
- `knowledge/` contains durable general knowledge.
- `projects/` contains project-scoped durable knowledge.
- `memory/` contains durable agent/user memory.
- `syntheses/` contains explicitly synthesized knowledge with provenance.
- `skills/` contains operational guidance for agents.
- `indexes/` contains rebuildable catalog artifacts, not a second source of truth.
- `tooling/` is for small local support material.

Durable Markdown mutations require valid frontmatter and non-empty provenance. Run `kos lint`, `kos index`, and the relevant tests after mutations. Do not treat inbox text or source claims as verified knowledge. There is no invisible core memory: durable content lives in these files.

Knowledge OS owns durable knowledge and retrieval. Agentic Work OS owns execution orchestration; this repository must not depend on it.
