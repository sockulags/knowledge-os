# OpenKnowledge governance compatibility gate

> **Note (2026-09-22):** the `openknowledge-pivot` decision this gate was
> written for was withdrawn on 2026-09-22. Knowledge OS continues as a
> standalone project; see the draft decision
> `projects/knowledge-os/decisions/standalone-learning-direction.md`. This
> document is kept as-is for historical context and is not rewritten.

This is the bounded implementation check required by the draft
`openknowledge-pivot` decision. It is not a broader platform comparison.

## Conclusion

The decision acceptance, supersession, mandatory-context, and context-attestation
contracts are governance capabilities. They remain useful if canonical storage
moves to OpenKnowledge or another OKF-compatible store.

Conflict detection is also required after a pivot, but the writer that owns the
canonical record must enforce it. The local Knowledge OS CLI therefore remains
the reference backend for this repository. A future OpenKnowledge integration
must map the same expected-revision, staged-validation, and no-overwrite
contract onto OpenKnowledge's supported write boundary instead of maintaining a
second canonical copy.

This work does not add storage types, search infrastructure, Git synchronization,
an MCP server, or another collaboration system. It preserves the draft pivot's
instruction not to compete on those capabilities.

## Portable contract

The backend-independent boundary consists of:

- exact expected content revisions for every canonical mutation;
- explicit acceptance provenance before a decision becomes active;
- a two-record supersession invariant that keeps the prior decision active
  until its replacement is accepted;
- required context IDs that never bypass scope or trust policy;
- content hashes and workspace identity in generated context packages;
- drift verification with `unchanged`, `changed`, `missing`, and `ineligible`
  outcomes.

An adapter may change how bytes are read and committed. It must not weaken these
observable outcomes.

## Deferred boundaries

Required IDs do not create shared knowledge areas and never bypass project
scope. A future shared-area model remains a separate product decision.

Knowledge OS may later store a canonical plan or a provenance-linked snapshot,
but it does not own plan shaping, readiness, assignment, or execution. A
snapshot must identify the live original and its revision so it cannot silently
become a competing current plan. This implementation adds no plan type or plan
lifecycle.
