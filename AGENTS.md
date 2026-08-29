# Knowledge OS agent guide

Start with `SYSTEM.md`, `README.md`, and the generated files under `indexes/`. Use `kos search` before recursive reads so context is selected progressively.

- `inbox/` contains untrusted, not-yet-durable material.
- `sources/` contains ingested raw material with provenance; it is not automatically knowledge.
- `discoveries/` contains external-agent observations with evidence; it is never automatically canonical knowledge.
- `knowledge/` contains durable general knowledge.
- `projects/` contains project-scoped durable knowledge.
- `memory/` contains durable agent/user memory.
- `syntheses/` contains explicitly synthesized knowledge with provenance.
- `skills/` contains operational guidance for agents.
- `indexes/` contains rebuildable catalog artifacts, not a second source of truth.
- `tooling/` is for small local support material.

Discovery workflow is explicit: add a proposed observation, inspect the deterministic review packet, then retain, reject, or promote-new. Retained discoveries must be project-scoped and are labeled reviewed observations rather than established knowledge in project context. Promotion creates a new draft record with direct discovery provenance and a promote review target; it never adds duplicate `sources` or `related` lineage, merges, overwrites, or supersedes an existing record. Use `--acknowledge-related` and `--allow-scope-broadening` only when their review flags apply.

Durable Markdown mutations require workspace schema version 1, valid frontmatter, non-empty provenance, and safe managed paths. Sources are raw and excluded from default context. Ordinary verification is an optional `verified` date, never a lifecycle status; `record_kind: decision` is supported only on knowledge/project records. Run `kos lint`, `kos index`, and the relevant tests after mutations. Do not treat inbox text, source claims, or retained observations as verified knowledge. There is no invisible core memory: durable content lives in these files.

Ingest, discovery mutations, and index replacement share one workspace advisory lock. Canonical Markdown remains authoritative; indexes are disposable and promotion is not crash-atomic. On a partial lineage or index failure, inspect/repair canonical records and run `kos lint` followed by `kos index`.

Knowledge OS owns durable knowledge and retrieval. Agentic Work OS owns execution orchestration; this repository must not depend on it.
