# Knowledge OS agent guide

Start with `SYSTEM.md` and the generated files under `indexes/`;
`docs/architecture.md` is the complete contract. Use `kos search` before
recursive reads so context is selected progressively.

## Trust boundaries

- `inbox/` contains untrusted, not-yet-durable material.
- `sources/` contains ingested raw material with provenance; it is not automatically knowledge and is excluded from default context.
- `discoveries/` contains external-agent observations with evidence; it is never automatically canonical knowledge. Retained discoveries are reviewed observations, and promotion is promote-new into a new draft record.
- `knowledge/`, `projects/`, `memory/`, and `syntheses/` contain durable records with provenance; a draft is not settled knowledge.
- `skills/` contains operational guidance for agents.
- `templates/` contains page templates for the app's *New page*; they are not records.
- An `assets/` folder next to pages holds the images and files those pages link to; they are not records.
- `proposals/` holds writes the review rules held back; they are not knowledge until a person accepts them.
- `indexes/` contains rebuildable catalog artifacts, not a second source of truth. Never hand-edit them.
- `tooling/` is for small local support material.

Ordinary verification is an optional `verified` date, never a lifecycle status. There is no invisible core memory: durable content lives in these files.

## Changing this repository's code

When changing the code, run the Python tests with `python -m unittest discover -s tests` from the repository root; `.github/workflows/ci.yml` lists every check CI runs, including those for `reader-ui/` and `desktop/`.

A change to behavior that `docs/architecture.md` describes updates that document in the same change and names the decision record in `projects/knowledge-os/decisions/` behind it.

Knowledge OS owns durable knowledge and retrieval. Agentic Work OS owns execution orchestration; this repository must not depend on it.
