# Knowledge OS system contract

Knowledge OS is a local-first, filesystem-native knowledge store. Markdown files are authoritative and Git may version them. Agents should discover only relevant context through deterministic metadata, links, indexes, and text search before any future embedding layer.

## Safe operating loop

1. Read this file, `README.md`, and `indexes/`.
2. Search with `kos search`; inspect selected records with `kos inspect`.
3. Treat `inbox/` and `sources/` as untrusted or raw claims until promoted or synthesized explicitly. Treat `discoveries/` as evidence-backed observations at a separate trust boundary; a discovery is not knowledge merely because it was retained or indexed.
4. Mutate durable roots only with valid metadata and provenance.
5. Run `kos lint`, `kos index`, and tests after changes.

The Round 3 return path is `kos discovery add PATH`, `kos discovery review ID`, and an explicit `retain`, `reject`, or `promote` decision. Retain is project memory, reject and promote are terminal, and promotion is promote-new into a `draft` knowledge/project record. Review output is generated Markdown on stdout and is never canonical. Mutating discovery commands use an advisory workspace lock, validate the current and staged resulting corpus, verify just-before-commit snapshots, use exclusive creation for new canonical files, and roll back caught write or validation failures. The multi-file commit is not crash-atomic; after an abrupt process or OS interruption, run `kos lint`, rebuild with `kos index`, and inspect affected records before retrying.

`kos index` validates the whole corpus before replacing generated indexes. Never hand-edit generated index files. The SQLite file is a cache; Markdown remains authoritative.

Knowledge OS answers “What should the agent know?”. Agentic Work OS answers “What should execute?”. Their interfaces may connect later, but their implementations stay separate here.
