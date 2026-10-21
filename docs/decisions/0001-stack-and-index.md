# Decision 0001: small local stack

Use Python 3.11, `argparse`, `pathlib`, dataclasses, `unittest`, PyYAML 6,
and SQLite FTS5 for Knowledge OS v0.0.1. Markdown is authoritative;
`indexes/catalog.md` is a human-readable generated catalog and
`indexes/catalog.sqlite3` is a disposable search cache. This keeps the frozen
slice inspectable and local without introducing a service or vector database.

## Superseded in part

The clause "without introducing a ... vector database" no longer holds. The
accepted decision `local-semantic-search`
(`projects/knowledge-os/decisions/local-semantic-search.md`) adds search by
meaning with an optional local model and a disposable semantic index,
`indexes/semantic.sqlite3`, next to the full-text cache. Markdown stays
authoritative and there is still no service.
