---
id: documentation-check-from-code
title: Keep project documentation in step with its code through a deterministic check
type: project
record_kind: decision
status: draft
scope: project:knowledge-os
created: '2026-09-28'
updated: '2026-09-28'
provenance:
- kind: user-request
  reference: github:sockulags/knowledge-os#84
related:
- agent-access
- configurable-review-policy
- in-app-agent-over-acp
---

## Decision

A project links the code repositories it describes in its overview's
`repositories` metadata: the folder on this computer, optionally the remote,
and the commit its documentation was last checked against. Linking records
the repository's current commit.

The documentation check is deterministic and read-only: the core asks Git
what changed since the checked commit (commits, dependencies, commands and
API routes, configuration, modules, documentation) and turns that into
suggestions, each naming the commits it came from: page updates for the
pages that mention something removed or changed (and the overview for what
no page mentions yet), and proposed decisions for dependencies and module
folders added or removed.

Nothing is rewritten by the check. A suggested decision becomes a draft
decision whose provenance names its commits; a page update is an ordinary
edit by a person or an agent under the review rules; and recording the check
moves the checked commit forward, so the next check starts there. The same
check, commit reading, proposing, and recording are available in the app,
on the command line (`kos code`), and to agents over MCP.

## Why

The vision is documentation that follows the code, but a model deciding
what the code "means" and rewriting pages would put unreviewed claims into
the knowledge base. Splitting the work keeps each part honest: Git answers
what changed, exactly and repeatably; a person or an agent decides what to
write, through the same review rules and provenance as every other write;
and a decision stays a proposal until a person accepts it. Recording the
checked commit makes each check cover only what is new, and the commit
provenance lets anyone trace a page or decision back to the code.

## Consequences

- The heuristics (manifest formats, route and command patterns, what counts
  as a module) are deliberately simple and may miss or over-report changes;
  the suggestions are leads, not findings.
- A repository path is specific to a computer. A relative path works across
  computers with the same layout; otherwise the app says the repository is
  not found and names the remote to clone.
- The in-app agent can read commits (`read_commit`) of linked repositories
  only, and still has no file or shell access.
