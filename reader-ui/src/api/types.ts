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
}

export interface NavPayload {
  workspace_name: string;
  projects: NavProject[];
  skills: { name: string; description: string }[];
  repo_docs: { path: string; title: string }[];
  record_index: RecordIndexEntry[];
}

export interface HomePayload {
  title: string;
  subtitle: string;
  waiting_on_you: RecordSummary[];
  in_force: RecordSummary[];
  recently_changed: RecordSummary[];
  projects: { id: string; title: string }[];
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
  trust: PropertyRow;
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
}

export interface EditableMetadata {
  title: string;
  tags: string[];
  related: string[];
  sources: string[];
}

export interface DecisionActions {
  accept: boolean;
  withdraw: boolean;
  /** The active decision this draft would replace, when it declares one. */
  supersede: { id: string; title: string; status: string; content_sha256: string | null } | null;
  propose_replacement: boolean;
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
  trust_phrase: string;
  project_title: string | null;
}

export interface EverythingPayload {
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
