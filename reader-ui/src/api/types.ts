// Types mirroring the JSON shapes knowledge_os/reader/api/*.py sends.
// Every sentence in these payloads is already finished prose from the
// Python side (language.py / strings.py); this file never re-derives
// meaning from a raw field, it only names the shape the API returns.

export type Tone = "green" | "amber" | "yellow" | "grey" | "violet" | null;

export interface Pill {
  label: string;
  tone: Tone;
}

export interface RecordSummary {
  id: string;
  title: string;
  type: string;
  record_kind: string | null;
  is_decision: boolean;
  status_pill: Pill | null;
  project: string | null;
  updated: string;
  sentence?: string;
  accepted_display?: string | null;
  updated_display?: string;
  updated_exact?: string | null;
}

export interface BrokenEntry {
  path: string;
  message: string;
}

export interface HealthSummary {
  lint_ok: boolean;
  lint_message: string;
  issue_count: number;
  issues: { path: string; message: string; record_id: string | null }[];
  index_available: boolean;
  index_stale: boolean;
  search_disabled: boolean;
  search_disabled_reason: string | null;
}

export interface WorkspacePayload {
  name: string;
  health: HealthSummary;
}

export interface TreeNode {
  name: string;
  /** The folder's path inside its project; "" for the project's top level. */
  path: string;
  /** False for a folder that only groups project records filed outside the
   * project directory (such as observations); it cannot be moved or used as
   * a move target. */
  in_project: boolean;
  overview: RecordSummary | null;
  records: RecordSummary[];
  broken: BrokenEntry[];
  children: TreeNode[];
}

export interface NavProject {
  id: string;
  title: string;
  tree: TreeNode;
}

export interface RecordIndexEntry {
  id: string;
  title: string;
  kind: string;
  status_pill: Pill | null;
  project: string | null;
  /** The quick switcher's group: a key of `language.quick_find_groups`. */
  group: string;
  /** What the entry is, in plain words ("Proposed decision", "Skill"). */
  kind_label: string;
}

export interface NavPayload {
  workspace_name: string;
  projects: NavProject[];
  skills: { name: string; description: string }[];
  repo_docs: { path: string; title: string }[];
  record_index: RecordIndexEntry[];
  /** The sidebar's Decide entry: its label and how many proposals wait. */
  decide: { label: string; count: number };
  /** Shell-wide copy with no page payload of its own to come from: the
   * quick-find placeholder, and the not-found/load-error fallbacks every
   * record-backed page shows the same way. `not_found_body` is a template;
   * fill its `{record_id}` placeholder with the requested id. */
  language: {
    quick_find_placeholder: string;
    quick_find_label: string;
    quick_find_hint: string;
    /** Template; fill its `{query}` placeholder with what was typed. */
    quick_find_no_matches: string;
    quick_find_searching: string;
    /** Group key -> heading; `text` heads pages found only by their body. */
    quick_find_groups: Record<string, string>;
    not_found_title: string;
    not_found_body: string;
    load_error: string;
    /** Shown instead of the browser's own network-failure message (e.g. the
     * raw "Failed to fetch") when a request never reached the core at all. */
    network_error: string;
    /** The sidebar's drag handle: accessible name and pointer hint. */
    sidebar_resize_label: string;
    sidebar_resize_hint: string;
    /** Showing one folder of a project tree on its own. */
    tree_focus_folder: string;
    tree_focus_trail_label: string;
    tree_show_whole_project: string;
  };
}

export interface HomePayload {
  title: string;
  subtitle: string;
  waiting_on_you: RecordSummary[];
  in_force: RecordSummary[];
  recently_changed: RecordSummary[];
  projects: { id: string; title: string }[];
  sections: { waiting_on_you: string; in_force: string; recently_changed: string; projects: string };
  decide_link: string;
}

export interface Breadcrumb {
  label: string;
  href: string;
}

export interface PropertyRow {
  label: string;
  value: string | string[] | null;
  pill?: Pill | null;
  raw?: string;
}

export interface PropertiesBlock {
  status: PropertyRow;
  /** null for a decision: acceptance is what matters there, not the
   * verified date, so the row is omitted rather than shown unconfirmed. */
  trust: PropertyRow | null;
  applies_to: PropertyRow;
  updated: PropertyRow;
  source: PropertyRow;
}

export interface TechnicalDetails {
  status: string;
  trust_label: string;
  scope: string;
  record_kind: string | null;
  path: string;
  content_sha256: string;
  provenance: { kind: string; reference: string; captured: string | null; sha256: string | null }[];
}

export type Heading = [level: number, text: string, anchor: string];

export interface RelationView {
  field: string;
  record_id: string;
  title: string | null;
  resolved: boolean;
  href: string | null;
  label: string;
}

export interface LineageCallout {
  kind: "superseded_by" | "supersedes";
  text: string;
  compare_href: string;
}

export interface GroupPayload {
  header: string;
  empty_text: string;
  records: RecordSummary[];
}

export interface ProjectPayload {
  id: string;
  title: string;
  breadcrumb: Breadcrumb[];
  properties: PropertiesBlock;
  technical_details: TechnicalDetails;
  groups: { governing: GroupPayload; proposed: GroupPayload; historical: GroupPayload };
  overview_body_html: string;
  overview_headings: Heading[];
  tree: TreeNode;
  observations: GroupPayload;
  raw_material: GroupPayload;
  related_general: GroupPayload;
  related_skills: { name: string; description: string }[];
}

export interface RecordPayload {
  id: string;
  title: string;
  type: string;
  record_kind: string | null;
  is_decision: boolean;
  breadcrumb: Breadcrumb[];
  properties: PropertiesBlock;
  technical_details: TechnicalDetails;
  lineage: LineageCallout[];
  body_html: string;
  headings: Heading[];
  inbound: RelationView[];
  outbound: RelationView[];
  editing: EditingBlock;
  /** Decision words and the "How decisions work" guide; null for a non-decision. */
  decision_language: DecisionLanguage | null;
}

export interface EditableMetadata {
  title: string;
  tags: string[];
  related: string[];
  sources: string[];
}

/** One line in a confirmation dialog: what a decision is now and what it becomes. */
export interface DecisionChange {
  subject: string | null;
  from: string;
  to: string;
}

/** A confirmation dialog's finished text, composed on the Python side. */
export interface DecisionDialog {
  title: string;
  body: string;
  confirm: string;
  history: string;
  changes: DecisionChange[];
}

export interface DecisionActions {
  accept: boolean;
  withdraw: boolean;
  /** The decision in force this proposal would replace, when it declares one. */
  supersede: { id: string; title: string; status: string; content_sha256: string | null } | null;
  propose_replacement: boolean;
  /** The sentence above the buttons, or null when no action applies. */
  summary: string | null;
  dialogs: { accept?: DecisionDialog; withdraw?: DecisionDialog; supersede?: DecisionDialog };
}

export interface DecisionLanguage {
  labels: {
    accept: string;
    accept_replacement: string;
    withdraw: string;
    replace_with: string;
    compare: string;
    compare_short: string;
    how_it_works: string;
    reason_label: string;
    reason_placeholder: string;
    cancel: string;
    working: string;
    conflict: string;
  };
  guide: {
    title: string;
    intro: string;
    undo: string;
    states: { key: "proposed" | "in_force" | "replaced" | "withdrawn"; label: string; text: string }[];
  };
}

/** One row of the Decide inbox (GET /api/decisions/proposed). */
export interface ProposedDecision {
  id: string;
  title: string;
  excerpt: string;
  project: { id: string; title: string };
  proposed_by: { source: string; label: string; kind: string | null };
  proposed_at: string;
  proposed_display: string | null;
  proposed_exact: string | null;
  replaces: { id: string; title: string; sentence: string | null } | null;
  effect: string;
  status_pill: Pill | null;
  content_sha256: string | null;
  actions: DecisionActions;
}

export interface DecidePayload {
  title: string;
  intro: string;
  count: number;
  count_label: string | null;
  project: string | null;
  filter_label: string;
  all_projects_label: string;
  projects: { id: string; title: string; count: number }[];
  items: ProposedDecision[];
  empty: { title: string; body: string };
  open_label: string;
  language: DecisionLanguage;
}

/** Machine data for the editor and the decision buttons (never shown as prose). */
export interface EditingBlock {
  editable: boolean;
  path: string;
  project_id: string | null;
  folder: string;
  raw_body: string | null;
  metadata: EditableMetadata | null;
  content_sha256: string | null;
  body_change_needs_confirmation: boolean;
  decision_actions: DecisionActions | null;
}

export interface WriteResult {
  id: string;
  status: string;
  path: string;
  content_sha256: string;
  index: { refreshed: boolean; count: number | null; error: string | null };
  /** The local Git commit made for this write, or why none was made. */
  commit: CommitInfo | null;
}

export interface CommitInfo {
  committed: boolean;
  sha: string | null;
  message: string | null;
  skipped: string | null;
  detail: string | null;
}

/** A structure change: a created project or folder, or a moved or renamed
 * page or folder. `changed` lists every file created, moved, or rewritten
 * (links to a moved file are rewritten), all recorded in one commit. */
export interface StructureResult {
  id: string | null;
  title: string | null;
  status: string | null;
  path: string;
  content_sha256: string | null;
  project: string;
  folder: string;
  scope_changed: boolean;
  changed: { id: string | null; old_path: string | null; path: string; content_sha256: string }[];
  index: { refreshed: boolean; count: number | null; error: string | null };
  commit: CommitInfo | null;
}

export interface SupersedeResult extends WriteResult {
  replaced: Omit<WriteResult, "index" | "commit">;
}

export interface WriteFailure {
  error: string;
  detail: string;
  current_sha256?: string;
  issues?: { path: string; message: string }[];
}

/** GET /api/sync/status: the repository as it is on this computer; never
 * contacts the remote. */
export interface SyncStatus {
  /** Where the guided setup stands (issue #56); null only from an older core. */
  setup: SyncSetupSummary | null;
  available: boolean;
  reason: string | null;
  detail: string | null;
  branch: string | null;
  upstream: string | null;
  remotes: string[];
  ahead: number;
  behind: number;
  uncommitted: number;
  merging: boolean;
  conflicts: number;
  last_sync: string | null;
  identity: { name: string; email: string } | null;
  warnings: string[];
}

/** The guided sync setup's state: `init` (not in Git or no commit),
 * `remote` (no remote), `publish` (no upstream), `ready`, or a state the app
 * cannot set up (`git_missing`, `source_repo`, `nested`, `detached`,
 * `repo_error`). `sentence` explains it (null when ready); `label` is the
 * sync bar's short text. */
export interface SyncSetupSummary {
  state: string;
  sentence: string | null;
  label: string | null;
}

/** GET /api/sync/setup: the summary plus what the setup steps need. All
 * copy comes from `language` (strings.SYNC_SETUP_LABELS); templates hold
 * `{count}`, `{branch}`, `{name}`, `{email}`, or `{url}`. */
export interface SyncSetup extends SyncSetupSummary {
  branch: string | null;
  remote: string | null;
  remote_url: string | null;
  identity: { name: string; email: string } | null;
  language: Record<string, string>;
}

export interface SyncSetupResponse {
  setup: SyncSetup;
  status: SyncStatus;
}

export interface SyncSetupInitResult extends SyncSetupResponse {
  created_repository: boolean;
  files: number;
  sha: string;
}

export interface SyncRemoteCheck {
  url: string;
  empty: boolean;
  branches: string[];
  branch: string | null;
  related: boolean | null;
}

export interface SyncConnectResult extends SyncSetupResponse {
  state: "published" | "synced";
  remote: string;
  branch: string;
  pushed: number;
  pulled: number;
  reindexed: boolean;
  index_error: string | null;
}

export interface SyncResult {
  state: "synced";
  pulled: number;
  pushed: number;
  reindexed: boolean;
  index_error: string | null;
  status: SyncStatus;
}

export interface SyncFailure extends WriteFailure {
  conflicts?: string[];
  status?: SyncStatus;
}

export interface ConflictFile {
  path: string;
  ours: string | null;
  theirs: string | null;
  working: string | null;
  binary: boolean;
  resolved: boolean;
}

export interface ConflictsPayload {
  files: ConflictFile[];
  status: SyncStatus;
}

export interface ResolveResult {
  path: string;
  remaining: string[];
  issues: { path: string; message: string }[];
  status: SyncStatus;
}

export interface CompareSide {
  id: string;
  title: string;
  sentence?: string;
  status_pill: Pill | null;
}

export interface DiffBlock {
  kind: "equal" | "added" | "removed" | "changed";
  left_html: string | null;
  right_html: string | null;
}

export interface Comparison {
  heading: string;
  state: "ok" | "missing" | "not_decision";
  detail: string | null;
  left: CompareSide | null;
  right: CompareSide | null;
  blocks: DiffBlock[];
  summary: string | null;
}

export interface ComparePayload {
  record: RecordSummary;
  status_text: string;
  comparisons: Comparison[];
  no_comparison_text: string;
}

export interface SkillPayload {
  name: string;
  title?: string;
  description?: string;
  tags?: string[];
  trust_label?: string;
  body_html?: string;
  headings?: Heading[];
  references?: { path: string; title: string; readable: boolean; detail: string | null; href: string | null }[];
  broken: { label: string; detail: string } | null;
}

export interface DocPayload {
  path: string;
  title: string;
  unmanaged_label: string;
  body_html: string;
  headings: Heading[];
}

export interface SearchResult {
  id: string;
  title: string;
  type: string;
  type_label: string;
  status: string;
  status_label: string;
  record_kind: string | null;
  record_kind_label: string;
  trust_label: string;
  scope: string;
  project: string | null;
  project_id: string | null;
  snippet_html: string;
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface SearchPayload {
  query: string;
  filters: Record<string, string>;
  filter_labels: Record<string, string>;
  filter_options: Record<string, FilterOption[]>;
  search_available: boolean;
  disabled_reason: string | null;
  results: SearchResult[];
  result_count: number;
  result_count_label: string;
}

export interface EverythingEntry extends RecordSummary {
  type_label: string;
  /** null for a decision: see PropertiesBlock.trust. */
  trust_phrase: string | null;
  project_title: string | null;
}

export interface EverythingPayload {
  title: string;
  intro: string;
  entries: EverythingEntry[];
  broken: BrokenEntry[];
  skills: { name: string; description: string }[];
  filters: Record<string, string>;
  filter_labels: Record<string, string>;
  filter_options: Record<string, FilterOption[]>;
  sort: string;
  dir: "asc" | "desc";
}

export interface ApiError {
  detail: string;
}
