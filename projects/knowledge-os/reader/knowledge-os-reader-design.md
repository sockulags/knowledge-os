---
id: knowledge-os-reader-design
title: Reader interface design
type: project
status: draft
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-19'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-12:knowledge-os-reader-planning
- kind: user-request
  reference: conversation:2026-09-19:knowledge-os-reader-redesign
related:
- knowledge-os-reader
---

## Purpose

The reader answers one question for a person returning to the workspace after a
while: what governs now, what is only proposed, and why.

## Direction

A calm, modern workspace in the spirit of Notion. A left sidebar holds the
project tree, and the reading column keeps a 68 to 72 character measure with
generous leading. A record's properties sit in a compact block under its title
rather than in a side rail, relations appear as backlinks at the end of the page,
and long documents get an outline on wide screens. Status carries colour only
where it changes what the reader should believe: in force, proposed, unverified,
retired, raw. The interface matches the feel of modern knowledge tools without
copying any product's brand.

## Information architecture

The project directory tree is the navigation, following the
`project-directory-layout` decision. Within a project, decisions are
additionally grouped by meaning rather than by type: in force now, waiting on
you, replaced. A project page opens with that overview, before the project's
own overview text. Type is a filter dimension, because `status` and `record_kind` say
what the reader should believe while `type` only says where a file lives.

Raw sources, observations at every review state, and retired records stay
reachable and carry their trust label. The rules for what an agent receives as
default context are deliberately narrower than what a human library should show.

Relationships are directed and the contract excludes a backlink subsystem, so the
reader builds an inbound map in memory to answer what points at the record being
read.

## Language

Contract vocabulary never appears in the reading path. Lifecycle values, scope,
provenance kinds, trust labels, content hashes, and file paths stay exact and
reachable one click away, under a collapsed technical details disclosure on every
document and project page. Titles are shown, never filenames.

A decision reads as "Proposal — nobody has taken a position yet" or "In force —
accepted 30 August". A raw source reads as "Raw material. Nobody has checked it."
A stale index reads as "Search may be missing recent changes." Empty groups get a
sentence rather than a dash. The interface is in English throughout, with every
user-facing string in one module.

## Degradation

`kos inspect` refuses to work in an invalid corpus, so the reader parses per file
and shows a broken record as broken with its lint message while its neighbours
stay readable. A missing or stale index disables search with an explanation
instead of failing the page.

## Boundary of this record

Delivery sequence and acceptance criteria are work planning and live outside the
corpus, in the repository's planning document. This record holds the direction
only.
