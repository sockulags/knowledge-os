# Decision 0001: small local stack

Use Python 3.11, `argparse`, `pathlib`, dataclasses, `unittest`, PyYAML 6,
and SQLite FTS5 for Knowledge OS v0.0.1. Markdown is authoritative;
`indexes/catalog.md` is a human-readable generated catalog and
`indexes/catalog.sqlite3` is a disposable search cache. This keeps the frozen
slice inspectable and local without introducing a service or vector database.
