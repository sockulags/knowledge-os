---
id: parallel-work-needs-an-owner-for-what-crosses-it
title: Parallel work needs an owner for what crosses it
type: knowledge
status: draft
scope: general
created: '2026-09-20'
updated: '2026-09-20'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-20:knowledge-os-reader-retrospective
related:
- interface-work-needs-visual-verification
---

## The lesson

Splitting work across parallel workers with exclusive file ownership removes
merge conflicts, but it also removes any owner for the qualities that live
between the files. Whatever crosses every unit needs someone who holds it, or it
belongs to nobody.

## What happened

The Knowledge OS reader was built by twelve agents: one froze the shared
contract, and eleven then built one view each, with an exclusive file list per
unit. The mechanical result was exactly as intended. Every unit landed as its own
pull request, no two units touched the same file, and the only merge conflicts
were trivial appends to one shared strings module.

What was lost was everything the split did not assign:

- **Coherence.** The same contract value was translated into reader language
  independently in several views, with three different rules for one case. Nobody
  owned the vocabulary as a whole.
- **Wiring.** A unit built the degradation states as shared partials, and no view
  included them, because the views were written at the same time by others. The
  same happened to the Markdown stylesheet and to the link from a document to the
  comparison view.
- **Design.** The visual whole belonged to no unit. Each page looked plausible
  alone; together they had no shared hierarchy, and the one element every page
  reserved space for did not render at all.

An integration pass afterwards closed the seams, but it was scoped to logic and
explicitly told not to touch design, so the interface stayed poor until it was
rebuilt.

## How to apply it

Name the cross-cutting concerns before splitting the work, and give each one an
owner: the vocabulary, the visual system, the navigation, the error states. The
owner is either a unit whose deliverable is that concern across all pages, or the
coordinator.

Plan the integration pass as real work rather than as cleanup, and let its scope
include the qualities that no unit could own.

Prefer a single worker for anything whose value depends on how the parts look and
feel together. Parallelism buys wall-clock time on separable work; it costs
coherence on work that is not separable.
