---
name: ingest-source
description: Ingest one local Markdown or text source while preserving provenance and validating the durable record.
tags:
  - ingest
  - ingestion
  - provenance
  - local-file
  - validation
---

# Ingest source

Use this skill when a local Markdown or text file should become a raw, provenance-bearing source. Do not treat ingestion as claim verification or synthesis.

## Workflow

1. Inspect the workspace contracts and indexes.
2. Run `kos ingest PATH`; it validates and refreshes indexes.
3. Run `kos lint` and inspect the resulting record provenance.

## Boundary

Only the ingest workflow may create the generated source and refresh indexes. Do not hand-edit generated indexes or mutate durable knowledge implicitly.
