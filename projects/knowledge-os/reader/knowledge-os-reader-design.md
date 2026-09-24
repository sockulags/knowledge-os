---
id: knowledge-os-reader-design
title: Reader interface design
type: project
status: draft
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-24'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-12:knowledge-os-reader-planning
- kind: user-request
  reference: conversation:2026-09-19:knowledge-os-reader-redesign
- kind: user-request
  reference: github:sockulags/knowledge-os#57
related:
- knowledge-os-reader
---

## Purpose

The reader answers one question for a person returning to the workspace after a
while: what governs now, what is only proposed, and why.

## Direction

A calm workspace for reading and writing documentation and decisions, with a
look of its own. A left sidebar holds the project tree, and the reading column
keeps a 68 to 72 character measure with generous leading. A record's properties
sit in a compact block under its title rather than in a side rail, relations
appear as backlinks at the end of the page, and long documents get an outline
on wide screens. Status carries colour only where it changes what the reader
should believe: in force, proposed, unverified, retired, raw.

The first version of this record set the direction "in the spirit of Notion".
The layout above stays, but the look no longer follows any other product: the
warm greys, black primary buttons, and round pills made the app read as a
copy of a well-known tool and as unfinished. The visual identity below
replaces that reference (issue #57).

## Visual identity

The identity is ink and paper: a warm paper ground, a near-black ink for text,
one petrol-ink accent for everything the reader can act on, and a serif for
titles. It reads as a ledger of what was decided rather than as a generic
notes app.

**Colour.** All values are CSS custom properties in `reader-ui/src/index.css`,
with a light and a dark set; the desktop shell's own pages copy them in
`desktop/src/renderer/src/style.css`.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--color-bg` | `#fbfaf7` | `#15181b` | Paper: the reading surface |
| `--color-bg-sidebar` | `#f2f0ea` | `#101316` | Sidebar, table heads, quiet panels |
| `--color-bg-raised` | `#ffffff` | `#1c2024` | Cards, dialogs, menus, fields |
| `--color-bg-active` | `#dfeaed` | `#1b3540` | The selected row, a drop target |
| `--color-text` / `-muted` / `-faint` | `#1b1c1e` / `#54565a` / `#6b6d70` | `#eae8e3` / `#b3b5b8` / `#92969a` | Three text levels |
| `--color-accent` | `#1f5e73` | `#6cbad0` | Primary buttons, focus ring, links |
| `--color-danger` | `#a8261d` | `#e5736a` | Destructive buttons |

Status tones (green in force, amber proposed, yellow unconfirmed, grey
replaced or withdrawn, violet raw, red broken) keep their meaning; their text
and background pairs were retuned so each passes WCAG AA (4.5:1) in both
themes, as do all three text levels on every surface. Before, the faintest
text measured 2.6 to 2.8:1 in light and 3.3 to 3.5:1 in dark, and the dark
theme's danger button put white text on light red at 2.3:1. Red appears only when something went
wrong, and the petrol accent never marks a status, so the two never compete.

**Type.** Inter for the interface and body text; Source Serif 4 for page
titles, section headings, and headings inside documents, so a page reads as
one voice from its title down. Both ship with the app. The scale is 11.5 px
(uppercase group labels), 12, 13, 14, 15 (interface), 16 (reading), 18, 21
(section headings), and 30 / 36 px (page titles on narrow and wide screens).

**Shape and space.** Three radii: 6 px for controls, 10 px for cards and
lists, 14 px for dialogs and floating panels. Pages share one column width
per kind (760 px for lists and overviews, 720 px for reading, 860 px for the
editor, 900 to 1100 px for comparisons, sync conflicts, and tables) and the
same top and side padding.

**Components.** A small set of shared classes replaces the class strings each
view used to repeat: buttons (`kos-btn` with primary, secondary, ghost, and
danger variants, and a small size), `kos-icon-btn`, `kos-input` for fields and
selects, `kos-card` and `kos-row` for lists, `kos-overlay`, `kos-menu`, and
`kos-menu-item` for floating surfaces, `kos-chip` for filters, `kos-eyebrow`
for group labels, and `kos-title`, `kos-heading`, and `kos-lede` for page
headings. Status badges are small tinted labels with a dot rather than round
pills, so the state reads even in greyscale. Every focusable element shows the
same 2 px accent focus ring when reached from the keyboard; fields show an
accent border and a soft halo instead.

**Motion.** Hover and press change colour only, in 120 ms. Menus, dialogs, and
toasts fade in over 90 to 120 ms and never block input; with reduced motion
turned on, nothing animates.

## App icon

A page that governs, marked with an ochre ribbon, in front of the fainter
draft behind it, on a petrol-ink tile. It tells the product's story, what is in
force above what is only proposed, without borrowing another app's symbol. The
tile keeps it legible on light and dark taskbars. At 16 and 24 px a separate
drawing on the 16 px grid keeps only the tile, the page, and the ribbon. The
sources and the generated `.ico` live in `desktop/build/`; `npm run icon`
regenerates them (see `desktop/README.md`). The small drawing is also the
reader's favicon and the mark beside the workspace name.

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
