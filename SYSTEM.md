# Knowledge OS system contract

Knowledge OS is a local-first, filesystem-native knowledge store. Markdown files are authoritative and Git may version them. Agents should discover only relevant context through deterministic metadata, links, indexes, and text search before any future embedding layer.

## Safe operating loop

1. Read this file, `README.md`, and `indexes/`.
2. Search with `kos search`; inspect selected records with `kos inspect`.
3. Treat `inbox/` and `sources/` as untrusted or raw claims until promoted or synthesized explicitly.
4. Mutate durable roots only with valid metadata and provenance.
5. Run `kos lint`, `kos index`, and tests after changes.

`kos index` validates the whole corpus before replacing generated indexes. Never hand-edit generated index files. The SQLite file is a cache; Markdown remains authoritative.

Knowledge OS answers “What should the agent know?”. Agentic Work OS answers “What should execute?”. Their interfaces may connect later, but their implementations stay separate here.
