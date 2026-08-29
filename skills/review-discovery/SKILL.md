---
name: review-discovery
description: Decide whether an external-agent observation should remain a reviewed discovery, be rejected, or be promoted into a new draft without bypassing the Knowledge OS trust boundary.
---

# Review discovery

Use this skill when an external agent returns an observation and someone must decide whether it is durable enough to record. A temporary debugging observation belongs in the run notes, not in `discoveries/`. A project fact, reusable discovery, or architectural decision may be recorded when its statement is specific, its evidence is inspectable, and its scope is explicit. Speculation stays proposed until a human can explain why its evidence is sufficient. Search first for an existing record; a duplicate or possible overlap is a reason to inspect, not a reason to merge.

## Workflow

1. Prepare structured Markdown with `type: discovery`, `status: proposed`, a non-empty observation body, non-empty `evidence`, provenance, and the narrowest honest scope. Use `origin.project` only with the matching `project:<id>` scope.
2. Run `kos discovery add PATH`, then `kos discovery inspect ID`.
3. Run `kos discovery review ID`. Treat listed records as deterministic potential overlaps or conflicts requiring human review; this packet is not semantic contradiction detection or fact checking.
4. Run exactly one explicit outcome: `kos discovery retain ID` for project-scoped reviewed memory, `kos discovery reject ID --reason TEXT` for a terminal rejection, or `kos discovery promote ID --target-id ID --title TEXT --scope SCOPE` for a new draft. Use `--acknowledge-related` only after inspecting listed candidates, and use `--allow-scope-broadening` only for an intentional project-to-general promotion.

Never silently promote, overwrite, supersede, or merge an existing record. Promotion is new-draft creation, not verification: its only lineage is target provenance with `kind: discovery` plus the discovery's promote review target. It does not add duplicate `sources` or `related` links. If promotion is interrupted, repair canonical Markdown and run `kos lint` followed by `kos index`.
