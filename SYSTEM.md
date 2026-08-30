# Knowledge OS system contract — v0.0.1

Knowledge OS is a local-first, filesystem-native knowledge store. The package
version is `0.0.1`, while `knowledge-os.toml` and the workspace schema remain
version `1`. Markdown files are authoritative and Git may version them.
[`docs/architecture.md`](docs/architecture.md) is the complete frozen
contract.

## Safe operating loop

1. Read this file, `README.md`, and `indexes/`.
2. Search with `kos search`; inspect selected records with `kos inspect`.
3. Treat `inbox/` and `sources/` as untrusted or raw claims. Sources are
   searchable but excluded from default context. Treat `discoveries/` as
   evidence-backed observations at a separate trust boundary; a discovery is
   not knowledge merely because it was retained or indexed.
4. Mutate durable roots only with valid metadata, provenance, and workspace
   schema version `1`.
5. Run `kos lint`, `kos index`, and tests after changes.

The discovery return path is `kos discovery add PATH`, `kos discovery review ID`,
and exactly one explicit `retain`, `reject`, or `promote` decision. Retain is
project-scoped reviewed memory, reject and promote are terminal, and promotion
is promote-new into a `draft` knowledge/project record. Promotion lineage is
only target provenance plus the promote review target; it does not add
redundant `sources` or `related` links.

After a user approves a complete candidate record, the safe write primitive is
`kos --root PATH capture CANDIDATE.md [--json]`. Capture is create-only for
`knowledge`, `project`, and `memory` records, requires `draft` or `active`
status and non-empty provenance, rejects `verified`, maps the type to its
canonical managed root, validates the whole staged corpus, and rebuilds the
disposable indexes. Cross-chat integrations must pass the explicit configured
workspace root; capture does not change cwd discovery semantics or perform
detection, proposal, approval, or background saving.

Ingest, capture, discovery mutations, and index replacement share one workspace
advisory lock. Mutations validate the current and staged corpus, write minimal
canonical files, then rebuild disposable indexes. The multi-file promotion is
not crash-atomic. If a partial lineage or an index failure is reported, repair
or inspect canonical Markdown, then run `kos lint` followed by `kos index`.
There is no rollback or journal for derived-state failures.

`kos index` validates the whole corpus before replacing generated indexes, and
`kos lint` validates every skill as well as every managed record. Never
hand-edit generated index files. The SQLite file and catalog are disposable;
deleting both leaves the corpus valid and `kos index` rebuilds them.

The root `knowledge-os` Codex plugin distributes the automatic
`knowledge-os-capture` skill. It detects durable decisions, reusable lessons,
and recurring preferences, batches proposals at natural pauses, and handles
user approval. It never writes before approval; after approval it invokes the
deterministic `capture` primitive with the explicit `KNOWLEDGE_OS_ROOT`. This
plugin is owned by Knowledge OS and has no Agent OS dependency. A clean plugin
install may require one explicit, one-time installation of this repository's
companion Python package; the skill derives the source root from its loaded
path, asks before mutating the user's Python environment, and safe-no-ops when
setup is declined or unavailable. It detects `sys.prefix != sys.base_prefix`
with the selected launcher: an active virtual environment receives the package
without `--user`; otherwise setup uses `--user`.

Knowledge OS answers “What should the agent know?”. Agentic Work OS answers “What should execute?”. Their interfaces may connect later, but their implementations stay separate here.
