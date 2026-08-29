# Context export example

This is a nested, disposable example workspace for the deterministic,
trust-aware context command. Its records are a fixture, not part of the
repository's canonical root corpus. The requested project has an exact
`projects/knowledge-os.md` overview; the other project demonstrates the scope
boundary.

From the repository root:

```powershell
kos --root examples/context-workspace index
kos --root examples/context-workspace context --project knowledge-os --task "Add URL ingestion while preserving provenance" --budget 12000 > context.md
```

The generated `context.md` is non-canonical output and is safe to discard.
