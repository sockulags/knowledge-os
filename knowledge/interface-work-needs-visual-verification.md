---
id: interface-work-needs-visual-verification
title: Interface work needs visual verification
type: knowledge
status: draft
scope: general
created: '2026-09-20'
updated: '2026-09-20'
provenance:
- kind: user-approved-conversation
  reference: conversation:2026-09-20:knowledge-os-reader-retrospective
---

## The lesson

Automated checks on an interface prove that it answers, not that it can be used.
A page can return 200, carry every expected string, pass every assertion, and
still be unusable. Verification of an interface has to include looking at the
rendered result.

## What happened

The first Knowledge OS reader was built and verified entirely through HTTP
status codes, string assertions against the returned HTML, and inspection of CSS
values. Every check passed: 267 tests, clean lint, and a corpus left
byte-identical after serving. The interface was then found to be close to
unusable.

Three defects had passed every test, because all three were invisible to a
string assertion:

- The document page's metadata rail, the central element of the design, never
  appeared on a desktop screen. Its markup was present in the HTML, which is why
  the assertions passed, but it sat inside a closed `details` element whose
  toggle was hidden by a media query above 900 pixels. Nothing could open it.
- An empty 320 pixel column was reserved on every page, including pages with no
  rail content, squeezing the reading column to about 400 pixels.
- Markdown bodies rendered with no typography after the later React rebuild:
  headings at body size, lists without bullets, tables without spacing. The
  typography plugin was loaded but the component used a custom class that defined
  none of it.

## How to apply it

Before calling interface work done, open it and look, at the widths it claims to
support and in every theme it offers. Screenshots belong in the definition of
done for a view, next to the tests.

When an agent reports that it verified an interface visually, treat that as a
claim to check rather than evidence. In this case an agent reported screenshot
verification of the same pages whose typography was plainly broken.

Choosing to skip visual verification is a decision about what will go unchecked,
not only about cost. When that trade-off is offered, say which defects the
cheaper path cannot catch.
