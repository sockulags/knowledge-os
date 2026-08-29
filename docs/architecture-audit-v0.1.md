# Knowledge OS architecture audit before v0.1

Date: 2026-08-29

## Executive assessment

**Assessment: healthy with targeted corrections.**

The three implemented loops are coherent and reinforce the intended product boundary:

1. local material becomes a provenance-bearing source, then a validated deterministic index entry;
2. a request becomes a bounded, deterministic, non-canonical context package;
3. agent output becomes a canonical observation, then an explicit review outcome, and only then a new draft durable record.

The filesystem is still the durable truth. SQLite, the catalog, review packets, and context packages are derived or generated. The CLI remains local, the dependency surface is small, and Agentic Work OS has not leaked into the implementation.

The architecture should **not be frozen exactly as implemented**, however. Three boundary defects are visible in executable behavior:

- Raw `source` records are eligible for context and receive no trust label.
- Project resolution can use any usable project-scoped record, including a raw source, as the mandatory project overview.
- One-hop relationship traversal can import an ordinary record from another project scope.

A temporary-workspace audit reproduced all three behaviors. A project-scoped active source became the sole mandatory context item with no trust label. In a workspace with a valid project overview, a general raw source was selected by FTS without a trust label and an explicitly related `project:other` record crossed into the package. These are not documentation problems; they follow from `USABLE_STATUSES`, `_resolve_project`, `_context_eligible`, and `_collect_ranked_candidates` in `knowledge_os/context.py`.

The metadata model also needs a small semantic freeze before durable files accumulate. `status` mixes lifecycle and verification, `project` is both a storage/type category and an implicit project identity convention, and architectural decisions already exist in two incompatible forms: an unmanaged file under `docs/decisions/` and an ordinary project record whose title says it is a decision.

No redesign, graph ontology, journal, database, plugin framework, or new retrieval technology is justified. Correct the semantic and trust boundaries, simplify the mutation contract, and then freeze v0.1.

## Current architecture map

### Executable flow

```text
local file
  -> ingest.py
  -> canonical sources/<id>.md
  -> workspace validation
  -> index.py
  -> generated catalog.md + SQLite FTS

context request
  -> request validation
  -> corpus + index validation
  -> project resolution
  -> FTS candidates + one-hop relationships + skills
  -> scoring + whole-item budget selection
  -> generated kos-context/v1 Markdown on stdout

external observation
  -> discovery add
  -> canonical discoveries/<id>.md (proposed)
  -> generated review packet
  -> retain | reject | promote-new
  -> embedded review history
  -> optional new draft knowledge/project record
  -> regenerated indexes
```

### Module ownership as implemented

- `model.py` parses YAML frontmatter and validates record-local metadata, discovery review history, and dates.
- `workspace.py` discovers a workspace, traverses managed directories, validates corpus-wide IDs and links, validates promoted lineage, and provides atomic single-file replacement.
- `index.py` validates the corpus, renders the Markdown catalog, builds SQLite FTS5, searches it, and detects a stale SQLite cache.
- `ingest.py` captures a local text file, computes its digest and stable ID, writes one canonical source, and rebuilds indexes.
- `context.py` validates requests and skills, resolves projects, applies trust/eligibility policy, retrieves and expands candidates, ranks them, budgets them, and renders the package.
- `discovery.py` owns discovery commands, review rendering, related-record retrieval, lifecycle transitions, promotion, advisory locking, whole-corpus staging, snapshots, commit, and rollback.
- `cli.py` is a thin command adapter over the domain functions.
- `tests/` uses subprocess-level behavior tests for the three loops and direct fault injection for discovery commit behavior.

The dependency direction is mostly sound: CLI depends on domain modules; context and discovery depend on validation and indexes; indexes depend on workspace/model. The main exception is mutation infrastructure living inside `discovery.py`, which prevents ingest and direct index rebuilds from sharing the same concurrency contract.

## Core invariants

### Enforced now

1. A workspace is rooted by the presence of `knowledge-os.toml`.
2. Managed Markdown has valid UTF-8 YAML frontmatter with known top-level fields.
3. Every managed record has a lowercase kebab-case ID, and its filename stem equals that ID.
4. IDs are globally unique across managed directories.
5. Record `type` matches its top-level managed directory.
6. Scope is `general` or `project:<id>`; `project` records cannot be general.
7. `created <= updated`; a verification date is bounded by those dates.
8. Every record has non-empty provenance.
9. `related`, `sources`, and `supersedes` IDs resolve.
10. A discovery has a non-empty body and evidence, a valid workflow history, and a status matching its latest review.
11. Record evidence references resolve when `evidence.kind == record`.
12. Retained discoveries are project-scoped.
13. Promoted discoveries have a non-self target with the expected type/scope, reciprocal links, and direct target provenance.
14. An invalid corpus cannot be indexed or mutated through ingest/discovery domain commands.
15. New ingest and promotion targets are never intentionally overwritten.
16. Context and discovery review require a current SQLite cache and do not rebuild it implicitly.
17. Context output is deterministic for unchanged corpus, skills, index, and request, and its estimated size does not exceed the budget.

`validate_metadata` is the obvious enforcement point for record-local invariants. `validate_workspace` is the obvious enforcement point for cross-record invariants. That separation is good.

### Missing or ambiguous

1. A project scope does not have to resolve to an exact project identity/overview record.
2. `knowledge` is documented as general knowledge, but validation permits `scope: project:<id>`; the directory/type contract and scope contract can disagree semantically.
3. Context relationships are not constrained to `general` plus the requested project.
4. Trust classification is not defined for sources, draft records, active records, memory, or synthesis.
5. `verified` is both a status and a date-backed epistemic property.
6. `sources` and `supersedes` can self-reference or form cycles; only promotion self-lineage is rejected.
7. A workspace marker's declared version is never parsed or enforced.
8. Skills are not checked by `kos lint`; malformed skill metadata fails only when context is requested.
9. Managed-file traversal does not explicitly reject symlinks or enforce that resolved files remain inside the workspace root.
10. Ingest, index, and discovery mutations do not share one workspace-wide lock.

These gaps do not require more abstraction. They require a clearer contract at the existing record, workspace, and context policy boundaries.

## Domain model findings

### First-class concepts

| Concept | Representation and ownership | Lifecycle and location | Canonical? | References and mutations | Semantic clarity |
| --- | --- | --- | --- | --- | --- |
| Workspace | Root marked by `knowledge-os.toml`; owns the corpus namespace and generated indexes | Exists while marker exists | Marker/config is canonical | CLI discovers it; domain APIs read/mutate under it | Mostly clear, but marker schema/version is not validated |
| Record/document | Markdown plus validated frontmatter; `Document` is the in-memory parsed view | Created and edited as files | File is canonical; `Document` is not | All record links use global IDs | Clear structural unit |
| Source | Captured raw local text and byte provenance | Created by ingest under `sources/`; currently `active` | Canonical as captured raw material, not as truth | Search and context can reference it; ingest creates it | Clear on disk, unclear in context trust policy |
| Knowledge | Durable general material | `knowledge/`; standard statuses | Canonical record | Manual edits or discovery promotion; relationships/provenance can reference it | Broad but usable; verification is unclear and project scope is incorrectly accepted |
| Project record | Durable project-scoped material and, by convention, project overview | `projects/`; standard statuses | Canonical record | Manual edits or project-scoped promotion | Overloaded: a project identity, overview, decision, and ordinary project note use the same type |
| Memory | Durable user/agent memory | `memory/`; standard statuses | Canonical record | Manual edits; retrievable in context | Insufficient semantic contract: subject, durability, and trust are not distinguished |
| Synthesis | Explicitly derived durable material | `syntheses/`; standard statuses | Canonical record | Manual edits; provenance and relationships should identify inputs | Intent is clear, but no synthesis-specific invariant distinguishes it from knowledge |
| Discovery | Evidence-bearing external observation | `proposed -> retained/rejected/promoted` under `discoveries/` | Canonical as an observation, never automatically as established knowledge | Discovery CLI mutates; review history is embedded; promotion creates a draft | Strongest and clearest concept in the model |
| Evidence reference | Support for a discovery statement | Embedded list in a discovery | Canonical as part of discovery | Record references are resolved; file/URL/command/test references remain opaque | Clear purpose; shares shape with provenance but not meaning |
| Provenance entry | Why/how a record came to exist or was derived | Embedded non-empty list in every record | Canonical metadata | Created by ingest/promotion or manual authoring | Purpose is clear, but reference semantics are mostly opaque and overlap with `sources` |
| Relationship | ID link in `related`, `sources`, or `supersedes` | Lives with source record | Canonical metadata | Manual edits and promotion | Field names imply types, but exact direction and meaning need definition |
| Review event | Human/workflow decision on a discovery | Append-only embedded history | Canonical part of discovery | Discovery retain/reject/promote commands | Clear and well validated |
| Review packet | Deterministic view of discovery, evidence, history, and candidates | Stdout only | Generated, non-canonical | Read-only discovery review | Clear |
| Context request/package | Request value plus selected Markdown package | In memory/stdout; `kos-context/v1` | Generated, non-canonical | Context command only | Clear external boundary; selection policy has trust/scope defects |
| Skill | Procedural guidance with discovery metadata | `skills/<dir>/SKILL.md` | Canonical operational content, but not corpus knowledge | Manually edited; parsed only by context | Suitable lightweight model, but validation ownership is misplaced |
| Index/catalog | Human catalog and SQLite FTS cache | Rebuilt by `kos index` and mutations | Derived/rebuildable | Index module only in principle | Clear |
| Architectural decision | Currently `docs/decisions/*.md` or an ordinary project record | No unified lifecycle or retrieval contract | Durable but split across systems | Manual documentation only | Implicit first-class need; current representation is inconsistent |

### Decision vs discovery vs knowledge

The current schema forces decisions into generic durable records or outside the corpus. The need for a first-class decision semantic is real now because the repository already contains both forms.

- “Knowledge OS uses SQLite FTS5 as its deterministic retrieval backend” is an **active architectural decision** and a **current system fact**. The decision record should state the chosen boundary and rationale; code, tests, and the SQLite schema are evidence that the system currently implements it.
- “URL ingestion must preserve retrieval time separately from publication time” is a **constraint or proposed decision** until accepted. Once adopted, it should be an active project/general decision. A source or test demonstrating the distinction is evidence, not the decision itself.
- “A sandboxing strategy failed in Agentic Work OS because of a Windows subprocess boundary” is initially a **project-scoped discovery** supported by a command, log, file, or test. It becomes knowledge only after review and synthesis into a reusable claim. It is not a decision unless someone records an action such as “do not use that boundary.”

The smallest contract is **not** a new directory or top-level record type. Add one validated semantic discriminator to durable knowledge/project records, for example `record_kind: decision`, while leaving scope and storage unchanged. A decision must state the chosen rule in its body, have provenance, use ordinary lifecycle status, and be independently searchable/filterable. Rationale and alternatives can remain body sections. Constraints and assumptions do not yet justify separate types; they can be explicit sections or tags within a decision or knowledge record until code needs distinct behavior.

This should be settled before v0.1 because changing the meaning of `type: project` after records accumulate will be more disruptive than adding a narrow discriminator now.

### Status

`status` is overloaded within ordinary records:

- `draft`, `active`, `deprecated`, and `archived` describe lifecycle/publication eligibility.
- `verified` describes epistemic verification and already requires a separate `verified` date.
- `superseded` describes replacement lineage.

Discovery statuses are a separate, coherent workflow state machine. Reusing the field name is acceptable because validation is type-specific, but ordinary status should not also carry trust.

Smallest correction:

- Keep ordinary `status` as lifecycle: `draft | active | deprecated | superseded | archived`.
- Represent verification only with the optional `verified` date (or a future explicit verification block), independent of lifecycle.
- Keep discovery `status` as its type-specific review workflow for v0.1; renaming it to `review_state` is not worth a migration by itself.
- Derive context trust labels from record type plus verification metadata, not from lifecycle status.

No publication state is needed for a local filesystem v0.1. No general multi-axis state machine is needed.

### Provenance and lineage

The intended chain is representable:

```text
draft knowledge/project
  -> provenance(kind=discovery, reference=<discovery>)
discovery
  -> origin(project/work_item/run)
  -> evidence(kind/reference/captured/digest)
evidence
  -> record ID or opaque file/command/test/URL reference
```

Promotion preserves this chain and corpus validation checks it. That is a solid base.

The problem is redundant encoding. Promotion records the same edge in four places: the target's `provenance`, the target's `sources`, the discovery's `related`, and the promote review event's `target`. The validator keeps them synchronized, but the semantics differ only weakly and a crash can update only part of the set.

Use this minimal semantic split:

- `provenance`: derivation/origin of the record; this answers “how did this record come to exist?”
- `evidence`: support for a discovery statement; this answers “what supports the observation?”
- review `target`: output of a promotion decision.
- ordinary relationships: domain associations, not required duplicates of provenance.

For promotion, target provenance plus the review target is sufficient to traverse in both directions by scanning or a generated backlink index. The reciprocal `related` and `sources` requirements should be removed unless `sources` is given a distinct documented meaning. `kind: record` and `kind: discovery` provenance should resolve through corpus validation. Provenance and evidence may share one parser/value shape without becoming the same concept.

Provenance is therefore **coherent in the happy path but over-specified**, not fundamentally broken.

### Relationships

Current relationship inventory:

- `related`: weak association with no declared direction or symmetry.
- `sources`: directed input/support/lineage, but promotion uses a discovery as a source while provenance already expresses the same edge.
- `supersedes`: directed replacement relationship.
- provenance references: derivation links, mostly opaque.
- discovery evidence record references: support links.
- discovery review target: workflow output link.
- project scope: implicit membership, not an ID relationship.

Typed relationship objects are **not needed now**. The current named fields already represent the only distinctions used by code. A generic edge ontology would add serialization and traversal complexity without product behavior.

Before backlinks or merge-to-existing, define direction and invariants for the existing fields, reject self/cyclic lineage where semantically invalid, and stop duplicating promotion lineage. Introduce typed edge objects later only if edges need their own provenance, dates, confidence, or behavior such as contradiction handling.

### Trust model

The intended trust model in plain language is:

1. Inbox is untrusted and unindexed.
2. Sources are captured raw claims with provenance, searchable for inspection but not established knowledge.
3. Proposed/rejected/promoted discoveries remain audit records; only retained project discoveries may enter context, and they remain labeled observations.
4. Draft durable records are candidates, not verified facts.
5. Active durable records are current, but current is not the same as verified.
6. Verification is explicit.
7. Context and review output are generated views and never knowledge.

The implementation enforces only the discovery part of that explanation. All standard `draft`, `active`, and `verified` records are context-eligible; raw sources are deliberately scored; only retained discoveries receive a trust label. Ordinary search returns every indexed status, which is acceptable for audit if compact results continue to expose type/status.

Before v0.1, either exclude sources from default context or label them as raw/untrusted and require an explicit inclusion path. Given the current no-new-context-features boundary, exclusion is the smaller correction. Context should also label draft/unverified durable records rather than imply that canonical means true.

## Module and boundary findings

### Context subsystem

`context.py` is understandable because its stages are visible, functions are named in domain language, and the end-to-end tests are good. Its size alone is not a defect.

Policy changes are nonetheless coupled across several locations:

- eligibility lives in `USABLE_STATUSES`, `_resolve_project`, `_context_eligible`, and FTS query arguments;
- trust labels are constructed in `_document_candidate` and rendered in two places;
- scope filtering differs between direct FTS and relationship traversal;
- skill parsing/validation is embedded in the same subsystem;
- ranking combines type, lifecycle status, retrieval evidence, project scope, and relationship expansion.

A developer cannot safely change trust or scope policy in one place today. The smallest useful separation is:

1. **eligibility and trust classification** — one policy producing eligible scopes/types and a required trust label;
2. **candidate retrieval** — FTS, one-hop expansion, and skill discovery;
3. **ranking and budget selection**;
4. **package rendering**.

Do not create generic services/managers/factories. A small context-selection module and a skill parser are sufficient after the semantic policy is fixed.

### Discovery subsystem

`discovery.py` contains two different architectural layers:

- the discovery domain: review lifecycle, related-record review, packet rendering, and promotion semantics;
- a filesystem transaction mechanism: advisory lock, stage copy, snapshots, exclusive create, commit, rollback, and post-commit verification.

This is the clearest module boundary debt. The infrastructure is unavailable to ingest/index, yet it accounts for much of the module and tests. Mutation coordination belongs at the workspace boundary, not the discovery boundary.

### Workspace, validation, and index

The local/corpus validation split is sound. Full traversal is repeated for most commands, but the corpus is currently small and correctness is more valuable than a cache of parsed records. Repeated traversal is necessary complexity for v0.1, not a performance defect.

Validation should remain callable from domain APIs, as it is now; it must not move into CLI-only checks. Add project identity, relationship lineage, workspace version, skill, and resolved-path checks at their existing obvious boundaries rather than introducing another validator hierarchy.

The index module correctly treats SQLite as rebuildable. `validate_index` compares the full searchable representation to Markdown before context/review. The Markdown catalog is not similarly checked, but no executable behavior depends on it; a stale catalog is a human-facing derived-state issue recoverable with `kos index`.

### CLI

The CLI is thin and appropriately boring. Command structure maps to the three loops. No API/server/MCP boundary is needed before the domain contract stabilizes.

## Persistence and mutation findings

### State classification

| State | Classification |
| --- | --- |
| `knowledge-os.toml` | Canonical workspace configuration |
| Managed Markdown in `sources/`, `knowledge/`, `projects/`, `memory/`, `syntheses/`, `discoveries/` | Canonical durable corpus records |
| `skills/*/SKILL.md` | Canonical operational guidance, outside the knowledge-record schema |
| Repository docs and directory READMEs | Canonical documentation, outside the knowledge corpus |
| `indexes/catalog.md` | Derived, human-readable catalog |
| `indexes/catalog.sqlite3` | Derived, rebuildable FTS cache |
| Context package | Generated/temporary, stdout |
| Discovery review packet | Generated/temporary, stdout |
| Staged workspace copies | Temporary validation/commit material |
| Mutation snapshots | Temporary in-memory byte snapshots |
| Advisory lock file | Temporary coordination artifact |

If every index and generated packet disappears, the durable corpus remains complete. `kos lint` can still validate it and `kos index` can reconstruct retrieval. This desired property holds.

### Mutation safety and crash behavior

Single-file `atomic_write` is proportionate. The discovery mutation path, however, copies the whole corpus, builds staged indexes, snapshots live outputs, writes up to four files, validates live state, and rolls back caught failures. It provides strong behavior for exceptions tested in-process, but it does not provide crash atomicity.

The result is both **over-engineered locally and under-engineered globally**:

- Over-engineered because derived indexes are treated as part of a rollback transaction even though they are rebuildable.
- Under-engineered because the lock applies only to discovery; ingest and direct index rebuilds can race on canonical files or the fixed `.catalog.sqlite3.tmp` path.
- Still incomplete because an abrupt stop after creating a promotion target but before updating the discovery can leave a lint-valid target pointing at a still-proposed discovery. The current promotion validator activates only when the discovery says `promoted`.

This is close to building a database transaction engine on the filesystem, without obtaining database crash guarantees.

Use **Option B plus Option C**:

1. Put one advisory mutation lock at the workspace boundary and use it for ingest, discovery mutations, and index replacement.
2. Validate the intended canonical result before commit.
3. Keep canonical writes minimal and individually atomic/exclusive.
4. Treat index rebuild as derived-state maintenance after canonical commit. If it fails, report a stale/absent index and recover with `kos index`; do not roll canonical truth back merely to preserve a cache snapshot.
5. Accept that two-record promotion is not crash-atomic for local single-user v0.1, document the exact partial states and recovery commands, and add a behavior test for recovery.

Do **not** build a write-ahead journal before v0.1. A journal creates another durable protocol, recovery state machine, and migration surface. Reconsider only after real crash evidence, non-local synchronization, or multi-process writes make manual recovery unacceptable.

## Filesystem contract findings

The top-level layout is strong and is part of the product interface. Each current directory has a readable responsibility. No reorganization is justified.

Path and metadata intentionally reinforce each other through directory/type and filename/ID invariants. Scope belongs in metadata because both general and project membership participate in retrieval. The weak point is that `projects/` currently encodes both project membership and an implicit project identity/overview convention, while `knowledge/` records are not actually constrained to general scope. Require an exact overview record whose ID equals the scope suffix, remove the arbitrary fallback, and enforce the documented general scope for `type: knowledge`.

The root-level corpus is currently empty while the codebase's architectural decisions live under `docs/`. That is acceptable for repository documentation, but decisions intended for Knowledge OS retrieval should use the future decision semantic rather than remain split indefinitely.

Symlinks require one proportionate integrity rule: managed paths must resolve inside the workspace, or symlinked managed records must be rejected. Current traversal follows file symlinks; later `workspace.relative(path.resolve())` can fail or external contents can be indexed. No broader sandbox is needed.

## Skill model findings

Skills are procedural knowledge plus discovery metadata. They are not executable plugins: the body instructs an agent to use existing CLI commands. This is the correct v0.1 model and can scale to dozens of skills without a plugin framework.

The metadata (`name`, `description`, optional tags) is sufficient for deterministic discovery. The two-term threshold is crude but explainable and testable. Do not add manifests, registries, loaders, or dependency resolution.

Minimal corrections:

- move parsing/validation out of context selection;
- include all skills in `kos lint`, not only at context time;
- require non-empty bodies and preferably directory name equal to skill name;
- keep selection metadata searchable while leaving body text out of activation matching.

No skill schema version is needed yet if the workspace schema version governs the parser.

## Agent usability findings

### What works

- `AGENTS.md`, `SYSTEM.md`, directory READMEs, and generated index banners expose the filesystem contract quickly.
- `kos search` and `kos inspect` support progressive disclosure.
- Generated context clearly identifies itself and exposes selection reasons, score, path, provenance, and budget.
- Discovery commands give an agent an explicit durable return path without silently upgrading observations to knowledge.
- Stale indexes fail closed for context/review.
- Agentic Work OS ownership is explicit and uncoupled.

### What requires inference

- An agent cannot reliably infer whether `active` means current, trusted, or verified.
- It cannot tell that a raw source may enter context without reading implementation.
- It cannot know what establishes a project identity because the exact overview is only preferred, not required.
- It must infer whether `sources` is provenance, evidence, or an ordinary relationship.
- It must discover that skills are not covered by lint.
- Safe mutation guarantees differ by command even though documentation describes a general safe loop.

After the P0/P1 corrections, the repository meets the stated agent-native standard without hidden memory or an opaque database.

## Human usability findings

Humans can browse the corpus, read frontmatter, inspect compact search results, render full records, and inspect deterministic review/context output. YAML is strict enough to catch errors early, and errors usually include the affected path and invariant.

The main human costs are semantic rather than interface-related:

- status cannot be interpreted without type-specific knowledge;
- promotion lineage appears in several fields;
- project overview identity is conventional rather than enforced;
- generic inspect hides relationships and discovery details unless a separate command is used;
- abrupt-crash recovery says to inspect affected records but cannot identify a partial promotion automatically.

No GUI is warranted. Clearer metadata, lint output, and explicit recovery examples are enough for v0.1.

## Complexity audit

### Necessary complexity

- Strict YAML parsing and corpus-wide validation.
- Global ID and relationship resolution.
- A rebuildable FTS cache and stale-cache detection.
- Deterministic selection, budgeting, and rendering.
- A separate discovery trust lifecycle and explicit promotion.
- Single-file atomic replacement and exclusive creation.

### Acceptable temporary complexity

- Full workspace traversal on commands.
- Lexical scoring constants and whole-item greedy budgeting.
- Separate discovery and ordinary status sets, provided their semantics are documented.
- Human-readable catalog plus SQLite cache.

### Architecture debt

- Trust/scope/project-resolution policy spread through context selection.
- Project type serving as both project identity and arbitrary project-scoped content.
- Verification embedded in lifecycle status.
- Promotion lineage duplicated across provenance and relationships.
- Mutation infrastructure embedded in discovery instead of workspace ownership.
- Skill validation embedded in context.
- Workspace schema version present but inert.

### Premature complexity

- Whole-corpus staging and rollback of rebuildable indexes for every discovery mutation.
- Tests that guarantee exact cache-byte rollback rather than the more important invariant that canonical truth remains valid and indexes are explicitly rebuildable.

The code does not contain generic factories, plugin abstractions, a graph layer, or dependency-heavy frameworks. Accidental complexity is concentrated rather than systemic.

## Test and integrity findings

The 26 current tests are strong executable specifications of the implemented loops. They cover malformed metadata, idempotent ingest, compact search, relationships, project/verified dates, invalid-corpus mutation refusal, discovery evidence and lifecycle, deterministic review, promotion scope/lineage, caught-failure rollback, exclusive creation, context determinism, FTS explanations, budget behavior, stale indexes, nested workspace discovery, and malformed skills.

The suite is behavior-heavy and generally preferable to implementation-unit tests. The discovery fault tests are the exception: they lock in the current transaction mechanism more strongly than the product boundary requires.

Missing architectural tests, in priority order:

1. Raw sources cannot appear as established/unlabeled context.
2. Cross-project relationships cannot broaden context scope without an explicit future contract.
3. Every project scope resolves to one exact usable project overview.
4. Verification is independent from lifecycle status and is rendered as trust evidence.
5. Deleting all derived indexes leaves lint valid and permits a complete rebuild.
6. Partial-promotion recovery is deterministic and documented.
7. Ingest/index/discovery share one mutation lock or otherwise cannot corrupt derived state.
8. Self/cyclic `sources` and `supersedes` lineage is rejected where appropriate.
9. Workspace schema versions are accepted/rejected explicitly.
10. `kos lint` validates all skills.
11. Managed symlinks cannot escape the workspace root.
12. Record-format compatibility is tested against one committed v1 fixture corpus.

Security posture is otherwise proportionate: YAML uses `safe_load`, IDs prevent destination traversal, writes derive destinations from validated IDs, SQLite queries are parameterized, and no subprocess/shell execution exists. Arbitrary input paths are read only at explicit user request. The main integrity issue is managed symlink traversal; the main confidentiality issue is that raw-source provenance and body can currently be packaged for an external agent without a trust or inclusion gate.

## Backward compatibility and evolution

Filesystem formats will become durable before the code API does. The best time to correct status, project identity, trust, decision, and lineage semantics is now.

The workspace already declares `version = 1`, the context package declares `kos-context/v1`, and SQLite sets `PRAGMA user_version = 1`. Only the context and SQLite versions are enforced in practice. Make the workspace version the schema authority for managed records and skills. Do not add per-record schema versions or migration infrastructure yet.

Strict rejection of unknown top-level fields is useful because it prevents silent schema drift. A one-time explicit update of the small fixture corpus is enough for the v0.1 corrections. Add migration tooling only when more than a small, reviewable set of durable records exists.

The context package contract should keep its version. Ranking weights and review packet prose need not be frozen as public APIs, but determinism, trust labeling, item boundaries, provenance, and budget accounting are contract behavior.

## Evaluation of proposed and future work

| Item | Decision | Rationale |
| --- | --- | --- |
| Crash-recovery journal | **Reject for v0.1** | Adds a durable recovery protocol while the product is local/single-user and derived state is rebuildable. Reconsider only with real crash evidence or remote concurrency. |
| Unified workspace locking | **Do now** | Small correction to make ingest, discovery, and index mutation semantics consistent and protect the fixed temporary index path. Combine with mutation simplification. |
| Merge proposal/diff artifact | **Defer** | Merge semantics depend on decisions, provenance, supersession, and relationship contracts that are not yet frozen. |
| Retrieval benchmark | **Do soon** | Valuable before embeddings or ranking changes, but it should measure the corrected trust/scope eligibility policy. |
| URL ingestion | **Defer** | First freeze source provenance fields, publication-vs-retrieval time, and context trust behavior. |
| PDF ingestion | **Defer** | It is a source variant and should follow, not precede, a stable source model. |
| Backlinks | **Do soon** | Rebuildable backlinks are useful after current relationship meanings are clarified; no graph store is needed. |
| Maintenance/lint improvements | **Do now** | Workspace version, project identity, skill validation, lineage, and symlink checks close v0.1 integrity gaps. |
| Merge-to-existing | **Defer** | Requires semantic reconciliation and conflict policy, not lexical matching. |
| Decisions | **Do now** | The concept already exists inconsistently; freeze the smallest semantic discriminator before more records accumulate. |
| MCP/API boundary | **Defer** | Stabilize CLI/domain semantics first. The current provider-only function boundary is enough. |
| Human UI | **Reject for v0.1** | Filesystem and CLI remain adequate; a UI would not solve the semantic findings. |
| Embeddings | **Defer** | No retrieval benchmark demonstrates need; deterministic retrieval is currently sufficient for the implemented scope. |
| Agentic Work OS integration | **Defer** | Preserve the current ownership separation until Knowledge OS contracts are stable. |

## Architectural debt

### P0 — must fix before further features

#### Context trust boundary is incomplete

- **Problem:** Raw sources and unverified/draft ordinary records can enter context with no trust classification.
- **Consequence:** An external agent can receive a raw claim in the same presentation as established durable knowledge, violating the central epistemic boundary.
- **Smallest correction:** Exclude sources from default v0.1 context; label every included ordinary item according to verification metadata and lifecycle; retain the existing explicit label for retained discoveries. Add behavior tests.

#### Project context boundary is not an invariant

- **Problem:** Any usable scoped record may become the project overview, and one-hop links can cross into another project.
- **Consequence:** Context can be anchored by the wrong concept and can leak unrelated/project-private material across scopes.
- **Smallest correction:** Require exactly one usable project overview with `id == <scope project id>` and `type: project`; enforce general scope for `type: knowledge`; remove fallback; constrain ordinary relationship expansion to `general` plus the requested project. Add tests for these failures.

### P1 — should fix before v0.1

#### Decision semantics are implicit

- **Problem:** Decisions live either outside the corpus or as indistinguishable project records.
- **Consequence:** Agents cannot retrieve, supersede, or reason about decisions consistently.
- **Smallest correction:** Add one validated/indexed semantic discriminator such as `record_kind: decision` for knowledge/project records; do not add a directory, graph, or separate state machine.

#### Ordinary status mixes lifecycle and verification

- **Problem:** `verified` is a lifecycle status and a dated epistemic property; `superseded` adds lineage to the same axis.
- **Consequence:** Eligibility, trust, and ranking depend on ambiguous state and will become harder to migrate.
- **Smallest correction:** Remove `verified` from lifecycle status, retain the verification date as an independent property, and define lifecycle statuses explicitly. Keep discovery's type-specific workflow status.

#### Promotion lineage is redundant

- **Problem:** One promotion edge is stored in provenance, `sources`, `related`, and review history.
- **Consequence:** More invariants, special-case validation, and partial states without more explanatory power.
- **Smallest correction:** Make target provenance plus review target authoritative; remove required reciprocal generic links unless a distinct meaning is documented. Resolve canonical provenance references.

#### Mutation ownership and guarantees are inconsistent

- **Problem:** Discovery owns a transaction-like mechanism; ingest/index do not share its lock; derived caches participate in rollback.
- **Consequence:** Complexity is high where it buys only caught-exception guarantees and low where concurrent commands can actually race.
- **Smallest correction:** Move one mutation lock to workspace ownership, use canonical-first minimal atomic writes, rebuild derived indexes afterward, and document/test partial-promotion recovery. Do not add a journal.

#### Workspace and skill schema validation is incomplete

- **Problem:** Workspace version is ignored and skills are validated only during context generation.
- **Consequence:** Invalid or future-format workspaces can appear valid; agents learn about malformed operational guidance too late.
- **Smallest correction:** Parse/enforce workspace schema v1 and include skill metadata/body/path invariants in lint through one shared skill parser.

#### Managed path integrity is incomplete

- **Problem:** Managed traversal follows file symlinks without ensuring resolved paths remain under the workspace.
- **Consequence:** External content can be indexed or path rendering can fail unexpectedly.
- **Smallest correction:** Reject symlinked managed records or reject any managed path whose resolved location escapes the workspace. Add one cross-platform behavior test where supported.

### P2 — acceptable to defer

- Split context selection from budgeting/rendering after policy correction; do not refactor solely for file size.
- Add generated backlinks after relationship semantics are frozen.
- Decide whether synthesis and memory need stronger type-specific metadata after real records reveal requirements.
- Improve inspect output for ordinary relationships if humans need it.
- Replace transaction-mechanism fault tests with recovery/invariant tests when mutation is simplified.
- Add a retrieval benchmark before changing ranking or considering embeddings.

## Explicit answers

1. **Do we need a first-class decision concept now?** Yes, at the semantic metadata level. Use the smallest validated/indexed discriminator inside existing knowledge/project storage; do not create a new subsystem.
2. **Is status overloaded?** Yes. Verification is mixed with lifecycle, and supersession adds lineage. Separate verification from ordinary lifecycle status; keep discovery's type-specific workflow status.
3. **Is provenance modeled coherently?** The discovery-to-promotion chain is coherent and validated, but it is redundantly encoded. Preserve provenance and evidence as distinct concepts, then remove duplicate generic links.
4. **Do we need typed relationships now?** No. Clarify and validate the existing named fields first. Typed edge objects are justified only when edges need metadata or distinct behavior.
5. **Is context architecture becoming over-coupled?** Yes at the policy level, not because of file length. Trust, eligibility, scope, retrieval, relationship expansion, ranking, skills, budgeting, and rendering cannot all be changed independently.
6. **Is mutation safety over-engineered or under-engineered?** Both: over-engineered for caught discovery/cache failures, under-engineered across workspace mutation entry points and abrupt termination.
7. **Should we build a crash journal?** No. Use a workspace lock, minimal canonical writes, rebuildable derived state, and explicit local recovery for v0.1.
8. **What should the next actual development round be?** A semantic-boundary correction round: seal context trust/project scope first, then freeze status, decision, provenance, workspace version, and mutation ownership. Add no ingestion formats or retrieval features in that round.

## Recommended v0.1 boundary

Freeze these as the stable core after P0/P1 corrections:

- Filesystem and managed Markdown are durable truth.
- Workspace schema v1 governs record and skill formats.
- Global IDs, exact project identity, scope, provenance, and cross-record integrity are lintable invariants.
- Local text ingest creates raw, provenance-bearing sources without conferring trust.
- Catalog and SQLite FTS are deterministic, disposable, rebuildable indexes.
- Search is an audit/retrieval tool and exposes record type/status.
- Context is read-only, deterministic, bounded, project-scoped, trust-labeled, and non-canonical.
- Discoveries are canonical observations with evidence and explicit review workflow.
- Retention remains project-scoped reviewed observation state.
- Promotion remains promote-new into a draft with direct lineage; no merge or supersession decision is automated.
- Skills remain lightweight procedural Markdown discovered by metadata and validated by lint.
- Mutation is local/single-user, coordinated by one advisory lock, individually atomic where practical, and explicitly not multi-file crash-atomic.
- Agentic Work OS remains outside the runtime boundary.

Do not freeze ranking weights, review-packet prose, internal staging implementation, or a plugin/API surface as architectural contracts.

## Next 3–5 issues

1. **Seal context trust and project scope.** Exclude raw sources by default, label verification/trust, require the exact project overview, and prevent cross-project relationship expansion.
2. **Freeze metadata semantics.** Separate verification from lifecycle status, add the minimal decision discriminator, define project identity, and simplify promotion lineage.
3. **Simplify and unify mutation safety.** Move the lock to workspace ownership, make canonical writes minimal, treat indexes as post-commit derived state, and test documented crash recovery without a journal.
4. **Complete v1 integrity validation.** Enforce workspace version, validate skills in lint, reject unsafe managed symlinks, and reject invalid self/cyclic lineage.
5. **Establish a small retrieval benchmark.** Measure deterministic retrieval, trust/scope exclusion, and package stability before backlinks, ranking changes, or embeddings.

After these issues, the architecture is coherent enough to freeze and extend. Before them, adding URL/PDF ingestion, merge semantics, MCP, embeddings, UI, or execution integration would harden ambiguous contracts rather than build on a stable core.
