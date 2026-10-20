---
name: review-discovery
description: Use when an external agent hands back an observation and someone must decide whether to keep it as a reviewed discovery, reject it, or promote it into a new draft ("review this discovery", "should we keep what the agent found", "promote this finding"). Not for saving decisions, lessons or preferences the user stated in the conversation (use knowledge-os-capture), or updating project documentation (use knowledge-os-documentation).
---

# Review discovery

Use this skill when an external agent returns an observation and someone must decide whether it is durable enough to record. A temporary debugging observation belongs in the run notes, not in `discoveries/`. A project fact, reusable discovery, or architectural decision may be recorded when its statement is specific, its evidence is inspectable, and its scope is explicit. Speculation stays proposed until a human can explain why its evidence is sufficient. Search first for an existing record; a duplicate or possible overlap is a reason to inspect, not a reason to merge.

## Workflow

Run every command as `<python> -m knowledge_os --root <root> ...`, never as a bare `kos`. `<root>` is `KNOWLEDGE_OS_ROOT`, or else `workspace` under `[knowledge_os]` in `~/.knowledge-os/config.toml`; never infer it from the current directory, which is usually another repository. `<python>` is a launcher proven to be Python >=3.11 that imports `knowledge_os`, selected as in the `knowledge-os-capture` skill's setup reference (`setup.md`). When no root names a directory containing `knowledge-os.toml`, or no launcher is available, do nothing and say what is missing.

1. Prepare structured Markdown with `type: discovery`, `status: proposed`, a non-empty observation body, non-empty `evidence`, provenance, and the narrowest honest scope. Use `origin.project` only with the matching `project:<id>` scope.
2. Run `<python> -m knowledge_os --root <root> discovery add PATH`, then `<python> -m knowledge_os --root <root> discovery inspect ID`.
3. Run `<python> -m knowledge_os --root <root> discovery review ID`. Treat listed records as deterministic potential overlaps or conflicts requiring human review; this packet is not semantic contradiction detection or fact checking.
4. Run exactly one explicit outcome: `<python> -m knowledge_os --root <root> discovery retain ID` for project-scoped reviewed memory, `<python> -m knowledge_os --root <root> discovery reject ID --reason TEXT` for a terminal rejection, or `<python> -m knowledge_os --root <root> discovery promote ID --target-id ID --title TEXT --scope SCOPE` for a new draft. Use `--acknowledge-related` only after inspecting listed candidates, and use `--allow-scope-broadening` only for an intentional project-to-general promotion.

Never silently promote, overwrite, supersede, or merge an existing record. Promotion is new-draft creation, not verification: its only lineage is target provenance with `kind: discovery` plus the discovery's promote review target. It does not add duplicate `sources` or `related` links. If promotion is interrupted, repair canonical Markdown and run `<python> -m knowledge_os --root <root> lint` followed by `<python> -m knowledge_os --root <root> index`.
