export type Mode = "research" | "experiment" | "writing" | "auto";
export type RuntimeSource = "fixture" | "real_corpus" | "local" | "openalex";
export type RuntimeTaskType = "auto" | "literature_review" | "hypothesis_design" | "experiment_validation" | "full_research";
export type RuntimeFlowMode = "review" | "strict";
export type AccessMode = "read_only" | "ask" | "full";
export type ContextTab = "brief" | "run" | "evidence" | "projects" | "evolution" | "eval";
export type SettingsSection =
  | "general"
  | "appearance"
  | "shortcuts"
  | "model"
  | "memory"
  | "agents"
  | "commands"
  | "plugins"
  | "evolution"
  | "runtime"
  | "usage"
  | "lineage"
  | "archive"
  | "data"
  | "guide"
  | "about";
export type TaskStatus = "active" | "blocked" | "done";
export type GateStatus = "pass" | "needs_human" | "pending" | "not_started" | "blocked";
export type StageStatus = "pending" | "running" | "done" | "waiting" | "skipped";

export interface WorkspaceFolder {
  name: string;
  files: number;
  bytes: number;
  importedAt: string;
}

export interface ContextAttachment {
  id: string;
  kind: "file" | "folder";
  name: string;
  source: "local" | "workspace";
  files: number;
  bytes: number;
  note?: string;
}

export interface WorkspaceFileEntry {
  path: string;
  name: string;
  size: number;
  lastModified: number;
  extension: string;
  handle?: FileSystemFileHandle;
  file?: File;
}

export interface WorkspaceFileScan {
  name: string;
  entries: WorkspaceFileEntry[];
  bytes: number;
  truncated: boolean;
  source: "handle" | "files";
}

export interface Workspace {
  id: string;
  name: string;
  note: string;
  folder?: WorkspaceFolder;
}

export type SkillSource = "builtin" | "custom" | "imported";

export interface ReviewFinding {
  id: string;
  reviewer: string;
  check: string;
  label: string;
  status: "pass" | "warn" | "deferred" | "blocked";
  summary: string;
}

export interface ReviewPackResult {
  id: string;
  generatedAt: string;
  reviewers: number;
  findings: ReviewFinding[];
  summary: string;
  note: string;
}
export type SkillActivation = "auto" | "manual" | "off";

export interface Skill {
  id: string;
  name: string;
  description: string;
  instructions: string;
  tools: string[];
  activation: SkillActivation;
  source: SkillSource;
  version: string;
  createdAt?: string;
  origin?: string;
  license?: string;
}

export interface SkillDraft {
  name: string;
  description: string;
  instructions: string;
  tools: string[];
  origin?: string;
}

export type PermissionKind = "start_auto" | "step_auto" | "run_experiment" | "approve_candidate" | "approve_tool";

export interface PermissionRequest {
  id: string;
  kind: PermissionKind;
  taskId: string;
  title: string;
  detail: string;
  targetId?: string;
}

export interface Gate {
  id: string;
  status: GateStatus;
  reason: string;
}

export interface Coverage {
  sources: number;
  spans: number;
  gaps: number;
  abstractOnly: number;
}

export interface RuntimeLoop {
  feedback?: {
    constraints_applied: number;
    loops: string[];
    effects: string[];
  };
  idea?: {
    status?: string;
    selection?: string;
    candidates: Array<{
      idea_id: string;
      title: string;
      hypothesis: string;
      falsification?: string;
      prior_art_scope?: string;
      novelty_status?: string;
    }>;
    ranked?: Array<{
      idea_id?: string;
      rank?: number;
      title?: string;
      evidence_count?: number;
      source_count?: number;
      prior_art_scope?: string;
      novelty_status?: string;
      testability?: string;
      has_kill_criteria?: boolean;
      has_contrast?: boolean;
    }>;
  };
  design?: {
    status?: string;
    idea_id?: string;
    hypothesis?: string;
    baseline?: string;
    primary_metric?: string;
    controls?: string[];
    seeds?: number;
    warnings?: string[];
  };
  paper?: {
    status?: string;
    section_count?: number;
    slots: Array<{
      slot_id: string;
      section?: string;
      status: string;
      required_evidence?: string;
    }>;
  };
  figure?: {
    figure_id?: string;
    kind?: string;
    schematic?: boolean;
    evidence_refs?: string[];
  };
  claimRegistry?: {
    entries: number;
    coverage_rate?: number;
    verified_anchor_rows?: number;
  };
  closure?: {
    status?: string;
    unresolved?: string[];
    checks?: number;
  };
  observationId?: string;
  activePolicyId?: string;
  appliedPolicy?: {
    policy_id?: string;
    patch?: Record<string, unknown>;
  };
  activeLease?: {
    lease_id?: string;
    seeds?: number;
    scope?: string;
  };
  writing?: {
    status?: string;
    submission_ready?: boolean;
    blockers?: string[];
    externalGates?: Record<string, { status?: string; issue_count?: number }>;
  };
  experiments?: Array<{
    experiment_id: string;
    idea_id?: string;
    next_action?: string;
    stages?: Record<string, string>;
  }>;
  blockers?: string[];
  nextActions?: Array<{
    gate?: string;
    owner?: string;
    command: string;
  }>;
}

export interface ProjectSummary {
  project_id: string;
  name: string;
  project_dir: string;
  experiment_count: number;
}

export interface ProjectExperiment {
  experiment_id: string;
  idea_id?: string;
  run_id?: string;
  design_status?: string;
  package?: string;
  stages?: Record<string, string>;
  next_action?: string;
  evidence_summary?: {
    status?: string;
    mean?: number | null;
    std?: number | null;
    cv_folds?: number | null;
  };
  error?: string;
}

export interface ProjectExperimentInventory {
  schema_version?: string;
  project_id?: string;
  name?: string;
  count: number;
  experiments: ProjectExperiment[];
  boundary?: string;
}

export interface ClaimDraftPrompt {
  status: string;
  statement: string;
  scope: string;
  /** Exact --assertion value proposed by the system; empty when the capsule had no per-seed metric. */
  assertion: string;
  reading: string;
  command: string;
  cwd: string;
  boundary: string;
}

export interface ClosureRow {
  profile: string;
  closure_status: string;
  next: string;
  run_id?: string;
  /** Present only while the run is unsigned: what a human would sign, and the exact command. */
  claim_draft?: ClaimDraftPrompt | null;
  experiment_id?: string;
  study_dir?: string;
  dataset?: string;
  signed?: boolean;
  underpowered?: boolean;
  has_signed_claim?: boolean;
  has_signature?: boolean;
  /** True when the signature records a policy-bounded autopilot, not a human signer. */
  delegated?: boolean;
  study_design?: {
    status: string;
    ccfa_level: string;
    blockers: string[];
  } | null;
  support_panel_status?: string;
  verdict?: StudyVerdict;
  origin?: "absent" | "bound" | "stale" | string;
  idea_id?: string;
  idea_title?: string;
  falsification?: string;
}

export interface StudyComparison {
  comparison: string;
  state: "positive" | "negative" | "undecidable" | "unavailable" | string;
  mean_diff: number | null;
  ci95: [number, number] | null;
  reason: string;
  /** Seeds the same design would need at this effect size; null when the study cannot say. */
  seeds_for_80pct?: number | null;
}

export interface StudyVerdict {
  available: boolean;
  comparisons: StudyComparison[];
  counts: Record<string, number>;
  decidable?: number;
  undecidable?: number;
}

export interface ReplicationRow {
  status: string;
  direction?: string;
  decided_in?: string[];
  generalizes?: boolean;
}

export interface OverturnedAssertion {
  design_key: string;
  dataset: string;
  comparison: string;
  reason: string;
  decided_at: { directory: string; seeds: number; state: string; mean_diff?: number; ci95?: (number | null)[] };
  at_higher_power: { directory: string; seeds: number; state: string; mean_diff?: number; ci95?: (number | null)[] };
}

export interface ReplicationSummary {
  packages?: number;
  status_counts?: Record<string, number>;
  warnings?: string[];
  overturned?: OverturnedAssertion[];
  power_ladders?: number;
  power_audit?: {
    ladders?: number;
    decided_at_lower_power?: number;
    overturned?: number;
    reversal_rate?: number | null;
    reading?: string;
  };
  groups?: {
    design_key: string;
    datasets: string[];
    seed_counts?: Record<string, number>;
    comparisons?: Record<string, ReplicationRow>;
  }[];
  unreplicated?: {
    design_key: string;
    datasets: string[];
    reason: string;
  }[];
  boundary?: string;
}

export interface ClosureInventory {
  schema_version?: string;
  project_dir: string;
  canonical_run: ClosureRow[];
  local_experiment: ClosureRow[];
  search_study: ClosureRow[];
  replication?: ReplicationSummary | null;
  present_profiles?: string[];
  boundary?: string;
}

export interface AutopilotStep {
  step: string;
  status: string;
  detail: string;
}

export interface AutopilotSnapshot {
  schema_version: string;
  policy: {
    policy_id?: string;
    policy_sha256?: string;
    authorized_by?: string;
    expires_at?: string;
    endpoint?: string;
  };
  run_id: string;
  status: "completed" | "stopped" | "missing" | string;
  stopped_at: string;
  reasons: string[];
  created_at: string;
  steps: AutopilotStep[];
  claim: { claim_id?: string; sha256?: string; assertion?: string };
  signature: { signature_id?: string; report_id?: string; submission?: boolean };
  bundle: { path: string; verified: boolean; signed: boolean; artifact_count: number };
  lineage: { status?: string; verify?: string };
  delegation: { delegated?: boolean; signer_id?: string; signer_name?: string; not_a_human_signature?: boolean };
  history: Array<{
    policy_id?: string;
    run_id: string;
    status: string;
    claim_id?: string;
    signature_id?: string;
    bundle?: string;
    created_at?: string;
  }>;
  boundary: string;
}

export interface EvidenceItem {
  id: string;
  kind: "gap" | "hypothesis" | "claim";
  status: "open" | "candidate" | "unsigned" | "signed" | "blocked";
  text: string;
  scope: string;
  refs: string[];
  note?: string;
  /**
   * Where a "signed" claim state came from. A browser click must never be read as a
   * human signature, so demo previews and imported CLI artifacts are labelled at the
   * data level; absent means the legacy/CLI-backed state (read-only snapshot).
   */
  origin?: "cli" | "cli-import" | "demo";
}

export interface EvidencePackage {
  id: string;
  stage: string;
  label: string;
  status: "ready" | "partial" | "needs_human" | "needs_signature" | "missing" | "blocked" | "not_run";
  detail: string;
  boundary: string;
  refs: string[];
}

export interface Protocol {
  hypothesis: string;
  baseline: string;
  metric: string;
  seeds: number;
  controls: string[];
}

export interface RunRecord {
  id: string;
  dataset: string;
  seeds: number;
  metric: string;
  mean: number;
  baseline: number | null;
  ea: string;
  status: string;
}

export interface AutomationPlanStage {
  id: string;
  label: string;
  owner: string;
  gates: string[];
  human_gate: boolean;
  outputs: string[];
}

export interface AutomationPlan {
  schema_version: string;
  action: string;
  generated_at: string;
  topic: string;
  mode: string;
  fingerprint: string;
  stages: AutomationPlanStage[];
  human_gates: Array<{ id: string; after: string; reason: string }>;
  stop_at: string;
  budget: Record<string, number | string>;
  adaptive_literature: {
    strategy: string;
    facets: Array<{ id: string; label: string; target_sources: number }>;
    coverage_plan: boolean;
  };
  run: { dataset: string | null; seeds: number; available: boolean };
  boundary: string;
}

export type InterventionKind = "engineering" | "domain";

export interface Intervention {
  id: string;
  label: string;
  kind: InterventionKind;
  note: string;
  at: string;
}

export interface EvaluationState {
  baselinePaper: number | null;
  baselineReproduced: number | null;
  hiddenAccessCount: number;
  validationSelections: number;
  evalRuleHash: string;
  audit: "pending" | "pass" | "flagged";
  trainCost: number | null;
  inferenceCost: number | null;
  interventions: Intervention[];
}

export interface EvolutionCandidate {
  id: string;
  target: string;
  patch: string;
  rationale: string;
  predicted: string;
  evidence: string;
  lease: string;
  status: "pending" | "active" | "rejected" | "rolled_back";
}

export interface EvolutionState {
  status: "idle" | "proposed" | "active" | "rejected" | "rolled_back";
  candidate: EvolutionCandidate | null;
  lease: string;
  history: Array<{ at: string; text: string }>;
}

export interface AutoStage {
  id: string;
  label: string;
  cmd: string;
  output: string;
  status: StageStatus;
  gate?: boolean;
}

export interface AutoState {
  running: boolean;
  paused: boolean;
  index: number;
  cycle: number;
  gate: "" | "claim";
  gateApproved: boolean;
}

export interface Guidance {
  id: string;
  text: string;
  at: string;
  status: "pending" | "applied";
  appliedAt?: string;
}

export interface Plugin {
  id: string;
  name: string;
  preset: "github" | "custom" | "local";
  transport: "streamable-http" | "stdio";
  url: string;
  auth: "oauth" | "env" | "none";
  readonly: boolean;
  toolsets: string[];
  status: "ready" | "disabled";
  note: string;
}

export interface ToolCall {
  id: string;
  pluginId: string;
  server: string;
  tool: string;
  args: string;
  status: "proposed" | "approved" | "denied";
  at: string;
  result?: string;
}

export interface ModelStop {
  value: string | number;
  label: string;
  detail: string;
}

export interface ModelProfile {
  id: string;
  name: string;
  short: string;
  provider: string;
  contextWindow: number;
  maxOutput: number;
  kind: "effort" | "budget" | "unsupported";
  defaultStop: string | number | null;
  stops: ModelStop[];
  note: string;
  providerId?: string;
  modelId?: string;
  apiFormat?: "openai_chat" | "openai_responses" | "anthropic_messages" | "openai_compatible";
  baseUrl?: string;
  apiKeyEnv?: string;
  inputTypes?: string[];
  capabilities?: string[];
  reasoningParam?: string;
  sourceUrl?: string;
  custom?: boolean;
}

export interface ModelSettings {
  profileId: string;
  contextLimit: number;
  maxReply: number;
  thinkingStop: string | number | null;
  compression: "off" | "auto" | "aggressive";
  threshold: number;
  keepRecent: number;
  summaryTokens: number;
}

export type MessageRole = "system" | "user" | "agent";

export type Card =
  | {
      type: "plan";
      queries: string[];
      scope: string;
      budget: string;
      note: string;
    }
  | {
      type: "sources";
      items: Array<{ title: string; meta: string; status: "ok" | "warn" }>;
      note: string;
    }
  | {
      type: "idea";
      gap: string;
      candidates: Array<{ id: string; text: string }>;
      note: string;
    }
  | {
      type: "protocol";
      hypothesis: string;
      baseline: string;
      metric: string;
      seeds: number;
      controls: string[];
      status: string;
    }
  | {
      type: "run";
      id: string;
      dataset: string;
      seeds: number;
      metric: string;
      mean: number;
      baseline: number;
      status: string;
      ea: string;
    }
  | {
      type: "gate";
      gate: string;
      title: string;
      reason: string;
      status: GateStatus;
    }
  | {
      type: "evolution";
      candidate: EvolutionCandidate;
    }
  | {
      type: "skill";
      skillId: string;
      name: string;
      version: string;
      status: "ok" | "needs_input" | "blocked";
      summary: string;
      steps: Array<{
        label: string;
        status: "done" | "pending" | "blocked";
        note: string;
      }>;
      note: string;
    }
  | {
      type: "runtime-run";
      jobId: string;
      jobDir?: string;
      status: "queued" | "running" | "completed" | "failed";
      events: number;
      runId?: string;
      fixtureMode?: boolean;
      source?: RuntimeSource;
      taskType?: RuntimeTaskType;
      dataset?: string;
      route?: string;
      taskStatus?: string;
      flowMode?: "review" | "strict";
      stoppedAt?: string;
      stage?: string;
      lastEvent?: string;
      eventLog?: Array<{
        seq: number;
        type: string;
        stage?: string | null;
        message: string;
        ts?: string;
      }>;
      gates?: Array<{ gate: string; status: string; reason: string }>;
      evidencePackages?: EvidencePackage[];
      supportAudit?: {
        status?: string;
        method?: string;
        counts?: Record<string, number>;
        citation_modes?: Record<string, number>;
        path?: string;
      };
      warnings: string[];
      artifacts: Array<{ path: string; size: number; kind: string; url: string }>;
      error?: string;
      failure?: {
        schema_version?: string;
        error_type?: string;
        error?: string;
        retryable?: boolean;
        suggested_action?: string;
        warnings?: string[];
        boundary?: string;
      };
      note: string;
    }
  | ({ type: "review-pack" } & ReviewPackResult)
  | {
      type: "skill-use";
      skillId: string;
      name: string;
      version: string;
      reason: string;
      mode: "auto" | "explicit";
      status: "ok" | "needs_input" | "blocked";
      summary: string;
      steps: Array<{
        label: string;
        status: "done" | "pending" | "blocked";
        note: string;
      }>;
      note: string;
    }
  | {
      type: "writing";
      slots: Array<{
        id: string;
        label: string;
        status: "bound" | "pending" | "locked";
        note: string;
      }>;
      note: string;
    }
  | {
      type: "tool";
      server: string;
      tool: string;
      status: ToolCall["status"];
      args: string;
      result?: string;
    };

export interface Message {
  id: string;
  role: MessageRole;
  at: string;
  text: string;
  card?: Card;
}

export interface ResearchTask {
  id: string;
  name: string;
  goal: string;
  domain: string;
  mode: Mode;
  access: AccessMode;
  status: TaskStatus;
  workspaceId: string;
  createdAt: string;
  updatedAt: string;
  stage: number;
  completedStages: number[];
  harness: { version: string; budget: number; label: string };
  model: ModelSettings;
  usage: Record<string, TokenUsage>;
  usageDays: Record<string, Record<string, TokenUsage>>;
  guidance: Guidance[];
  plugins: string[];
  toolCalls: ToolCall[];
  budget: { used: number; total: number };
  gates: Gate[];
  coverage: Coverage;
  evidence: EvidenceItem[];
  evidencePackages?: EvidencePackage[];
  protocol: Protocol | null;
  protocolFrozen: boolean;
  run: RunRecord | null;
  runtime?: { source: RuntimeSource; runId?: string; appliedAt: string };
  runtimeLoop?: RuntimeLoop;
  autoPlan?: AutomationPlan | null;
  evaluation: EvaluationState;
  evolution: EvolutionState;
  auto: AutoState;
  autoStages: AutoStage[];
  reviewPack?: ReviewPackResult;
  messages: Message[];
}

export interface TokenUsage {
  prompt: number;
  completion: number;
  requests: number;
}

export type ShortcutAction =
  | "commandPalette"
  | "newSession"
  | "openSettings"
  | "focusComposer"
  | "toggleContext"
  | "openSkills"
  | "openModel"
  | "openEvidence"
  | "openEval";

export type ShortcutMap = Record<ShortcutAction, string>;

export interface Preferences {
  autoExpandRunning: boolean;
  autoScroll: boolean;
  reduceMotion: boolean;
  fontScale: number;
  shortcuts: ShortcutMap;
}

export type MemoryKind = "decision" | "preference" | "constraint" | "note";

export interface MemoryEntry {
  id: string;
  text: string;
  kind: MemoryKind;
  scope: string;
  source: string;
  createdAt: string;
  syncedAt?: string;
}

export interface SettingsOrigin {
  kind: "welcome" | "task";
  taskId: string;
  label: string;
}

export interface UIState {
  contextTab: ContextTab;
  search: string;
  expandedWorkspaces: Record<string, boolean>;
  sidebarOpen: boolean;
  contextOpen: boolean;
  contextCollapsed: boolean;
  welcomeOpen: boolean;
  skillsOpen: boolean;
  draftAccess: AccessMode;
  draftProfileId: string;
  skillDraft: SkillDraft | null;
  permissionRequest: PermissionRequest | null;
  newTaskOpen: boolean;
  newTaskMode: Mode;
  modelOpen: boolean;
  pluginsOpen: boolean;
  paletteOpen: boolean;
  settingsOpen: boolean;
  settingsSection: SettingsSection;
  settingsOrigin: SettingsOrigin;
  filesOpen: boolean;
  filesWorkspaceId: string;
  focusComposerTick: number;
  claimGateOpen: boolean;
}

export interface PersistedWorkspace {
  version: number;
  selectedTaskId: string;
  activeWorkspaceId: string;
  preferences: Preferences;
  workspaces: Workspace[];
  tasks: ResearchTask[];
  plugins: Plugin[];
  skills: Skill[];
  memory: MemoryEntry[];
  archivedTaskIds: string[];
}

export interface WorkspaceSnapshot extends PersistedWorkspace {
  ui: UIState;
}
