# Capture through the CLI

Read this only when the Knowledge OS MCP tools are not available and an item has been approved.
Select the launcher and workspace root first as described in [setup.md](setup.md); without both,
safe-no-op and say what is missing.

## Approved capture

For each approved candidate, exclusively create a unique directory in the operating system's temp
directory, outside the Knowledge OS root and all canonical roots (`inbox/`, `sources/`,
`discoveries/`, `knowledge/`, `projects/`, `memory/`, and `syntheses/`). Write the candidate as
`<temp-directory>/<id>.md`. Create both only after approval, refuse an unexpected existing path,
and remove only that file and the empty directory created by this skill in a `finally`-style
cleanup. Never recursively remove a broad or unresolved path.

The candidate must be a complete record with valid frontmatter. Include these fields, using the
workspace's supported values: `id`, `title`, `type` (`knowledge`, `project`, or `memory`), `status`
(`draft`), `scope`, `created`, `updated`, and non-empty `provenance`. A decision also needs
`record_kind: decision`, which only `knowledge` and `project` records may carry, with `status:
draft`; without it the record is an ordinary page, not a decision. Make `id` lowercase kebab-case
and match the `<id>.md` filename. Every provenance entry may use only `kind`, `reference`, and the
optional schema-supported `captured` or `sha256` fields. Put the user-approved conversation basis
and relevant context in `reference` and the body; do not invent approval or verification metadata.
Include uncertainty in the body, omit `verified`, and never fabricate a `sha256`. Keep the body
limited to the approved durable statement and useful context.

For a `project` record, the proposal must also identify its path relative to
`projects/<project-id>/`. Use the project root by default. When the approved
destination is a nested folder or its root `README.md`, pass that exact relative
path with `--project-path`; never invent a folder that the user did not approve.

Invoke the storage boundary only after the approved file exists:

```powershell
& $python[0] $python[1] -m knowledge_os --root "$root" capture "$candidate" --writer agent --json
```

For an approved nested project destination, append `--project-path
"$approvedProjectPath"`.

POSIX shells use the same selected launcher and root, including the documented `python3` fallback:

```sh
"$python_cmd" -m knowledge_os --root "$root" capture "$candidate" --writer agent --json
```

For an approved nested project destination, append `--project-path
"$approved_project_path"`.

`--writer agent` applies the knowledge base's review rules. When a rule holds the write back, the
result's `action` is `waiting_for_review` and the change is stored as a proposed change, not as a
record: nothing is written yet. Tell the person that it waits in the app's Decide inbox, where they
accept or discard it, and name the `rule` from the result. Do not report it as saved and do not
capture it again.

Call once per approved candidate; never pass an unapproved batch. Report the exact returned fields
that identify the outcome and record, preserving their values without inference; dump the full JSON
only when its additional fields are needed to explain an error or ambiguity. Clean up the temporary
candidate after success or failure and report any cleanup failure as a blocker.

Capturing a decision stores it as a non-governing draft. Approval to store the candidate is not by
itself authority to make the decision active. Run `<python> -m knowledge_os --root <root> decision
accept ID --expected-sha256 HASH --acceptance-reference REFERENCE --json` only when the user has
also explicitly accepted the decision as governing in the current conversation. In that case, run
`<python> -m knowledge_os --root <root> inspect ID` to obtain the new record's exact
`content_sha256`, use the accepted conversation as the acceptance reference, and report the
separate activation. Never activate a replacement draft with this command; accepted replacements
must use the coordinated `<python> -m knowledge_os --root <root> supersede OLD_ID NEW_ID
--expected-old-sha256 HASH --expected-new-sha256 HASH --acceptance-reference REFERENCE --json`
operation.
