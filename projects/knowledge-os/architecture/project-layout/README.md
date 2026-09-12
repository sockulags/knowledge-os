---
id: project-directory-layout
title: Project directory layout
type: project
record_kind: decision
status: active
scope: project:knowledge-os
created: '2026-09-12'
updated: '2026-09-12'
provenance:
- kind: user-request
  reference: conversation:2026-09-12:project-directory-layout
- kind: decision-acceptance
  reference: conversation:2026-09-12:project-directory-layout-approval
  captured: '2026-09-12T14:44:12.103226Z'
---

## Decision

Every project's durable project documentation is contained in
`projects/<project-id>/`. The project overview is the root record `README.md`
in that directory.

Below the project root, directories may use any safe filesystem name and may
nest to any depth. Any directory may contain its own metadata-bearing
`README.md` root record. Other records use filenames matching their globally
unique IDs.

The directory tree is organizational. Project ownership remains explicit
through `scope: project:<project-id>`, and validation prevents project records
from escaping that project's directory. Raw sources and discoveries remain in
their separate trust-boundary roots.
