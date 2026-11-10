import type { AutomationPlan, EvidencePackage, MemoryKind } from "../domain/types";
import type { AutopilotSnapshot, ClosureInventory, ProjectExperimentInventory, ProjectSummary } from "../domain/types";

import { authHeaders, describeAuthRefusal } from "./runtimeAuth";

const runtimeBase = (import.meta.env.VITE_RUNTIME_URL ?? "").replace(/\/$/, "");

export interface RunCreateInput {
  topic: string;
  task_type?: "" | "auto" | "literature_review" | "hypothesis_design" | "experiment_validation" | "full_research";
  deliverable?: string;
  language?: "" | "zh" | "en";
  venue_type?: "zh_core_journal" | "en_conference" | "en_journal" | "zh_thesis";
  grant_scheme?: "" | "nsfc" | "nssfc" | "generic";
  figure_style?: "comic" | "roman" | "modern";
  max_sources?: number;
  real_corpus?: boolean;
  local_corpus?: boolean;
  openalex?: boolean;
  mailto?: string;
  planner?: string;
  run_dataset?: "" | "iris" | "breast_cancer" | "chemlab";
  run_seeds?: number;
  flow_mode?: "" | "review" | "strict";
  g1_decision_file?: string;
  protocol_file?: string;
  claim_file?: string;
  bibliography_file?: string;
  run_dir?: string;
}

export interface RunJob {
  job_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  request: RunCreateInput;
  events_count: number;
  error: string;
  events_url?: string;
  stream_url?: string;
  artifacts_url?: string;
  result?: {
    run_id?: string;
    task_id?: string;
    job_dir?: string;
    status?: string;
    route?: string;
    deliverable?: string;
    fixture_mode?: boolean;
    warnings?: string[];
    gates?: Array<{ gate: string; status: string; reason: string }>;
    checks?: Array<{ name: string; status: string; detail: string }>;
    modules?: Record<string, string | null>;
    spec_versions?: Record<string, string>;
    artifacts?: Record<string, string>;
    evidence_packages?: EvidencePackage[];
    support_audit?: {
      status?: string;
      method?: string;
      counts?: Record<string, number>;
      citation_modes?: Record<string, number>;
      path?: string;
    };
    flow_mode?: "review" | "strict";
    stopped_at?: string;
    max_sources?: number;
    run_seeds?: number;
    requested_run_seeds?: number;
    observation_id?: string;
    active_policy?: { policy_id?: string; patch?: Record<string, unknown> } | null;
    active_s5_lease?: { lease_id?: string; seeds?: number; scope?: string } | null;
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
  };
}

export interface RunEvent {
  seq: number;
  ts: string;
  type: string;
  stage: string | null;
  message: string;
  data?: Record<string, unknown>;
}

export interface RunEvents {
  job_id: string;
  status: string;
  terminal: boolean;
  events: RunEvent[];
}

export interface RunArtifact {
  path: string;
  size: number;
  kind: string;
  url: string;
}

export interface ModelCallRecord {
  at: string;
  profile_id: string;
  provider_id: string;
  model: string;
  thinking: Record<string, unknown>;
  ok: boolean;
  latency_ms: number;
  usage: Record<string, number>;
  request_id: string;
  error: string;
}

export interface RuntimeHealth {
  status: string;
  service: string;
  mode: string;
  research_mode?: "test" | "production";
  production_ready?: boolean;
  model_readiness?: {
    required_modules: string[];
    modules: Record<string, {
      wired: boolean;
      bound_profile: string;
      provider: string;
      key_configured: boolean;
      consumer: string;
    }>;
    production_ready: boolean;
    blocking: string[];
    warnings?: string[];
    boundary: string;
  };
  version: string;
  human_sign: boolean;
  rsi_read_only: boolean;
  queue: { pending: number; max_pending: number };
  real_corpus: boolean;
  local_corpus?: boolean;
  model_gateway: boolean;
  model_store?: string | null;
  default_rsi_ledger?: string | null;
  cors_origins: string[];
}

export interface AgentRecord {
  id: string;
  name: string;
  stage: string;
  version: string;
  status: string;
  owner: string;
  outputs: string[];
  tools: string[];
  gates: string[];
  invariants: string[];
  spec: string | null;
}

export interface AgentRegistrySnapshot {
  schema_version: string;
  source: string;
  generated_at: string;
  count: number;
  agents: AgentRecord[];
  boundary: string;
}

export interface CommandRecord {
  id: string;
  group: string;
  label: string;
  syntax: string;
  description: string;
  safety: "read_only" | "local_write" | "network_opt_in" | "human_gate" | "catalog_only";
}

export interface CommandCatalogSnapshot {
  schema_version: string;
  generated_at: string;
  count: number;
  commands: CommandRecord[];
  boundary: string;
}

export interface SkillCandidate {
  candidate_id: string;
  kind: string;
  target: string;
  facet: string | null;
  constraint?: string;
  patch: string;
  rationale: string;
  predicted_effect: string;
  status: string;
  scope: string;
  governance: {
    auto_admitted: boolean;
    required: string[];
    immutable: string[];
    note: string;
  };
}

export interface OrchestrationRole {
  id: string;
  name: string;
  stage: string;
  module: string;
  mode: string;
  facets?: string[];
  budget?: number;
  checks?: string[];
  check_labels?: string[];
  deferred_checks?: string[];
  advisory_only?: boolean;
  writes?: string[];
  inputs?: string[];
  outputs?: string[];
  gates?: string[];
  parallel_group?: string;
  gate_owner?: string;
  note?: string;
  forbidden?: string[];
  executes?: boolean;
}

export interface OrchestrationHandoff {
  from: string;
  to: string;
  contract: string;
  mode: string;
  gate?: string;
  fields?: string[];
  note?: string;
  merge?: string;
}

export interface OrchestrationPlan {
  schema_version: string;
  action?: string;
  template?: boolean;
  topic?: string;
  source?: string;
  topology: string;
  roles: OrchestrationRole[];
  lanes: {
    parallel: { roles: string[]; max_workers: number; name?: string; write_scope?: string };
    fan_in: { role: string; depends_on?: string[]; merge_keys: string[]; name?: string };
    sequential: string[];
    independent: string[];
  };
  handoffs: OrchestrationHandoff[];
  human_gates: Array<{ id: string; after: string; reason: string }>;
  budget?: {
    total_sources: number;
    groups: Array<{ role_id: string; facets: string[]; sources: number }>;
  };
  stop_at?: string;
  blocked_at?: string;
  does_not_execute?: string[];
  evolution_policy?: {
    enabled: boolean;
    scopes: Record<string, boolean>;
    locked: string[];
    boundary: string;
  };
  memory?: {
    mode?: string;
    observed_runs: number;
    cold_start: boolean;
    rationale: string[];
    skill_candidate: SkillCandidate | null;
    boundary: string;
  };
  boundary: string;
}

export interface LiteratureFacetMemory {
  attempts: number;
  covered_runs: number;
  spans: number;
  queries: number;
}

export interface LiteratureModeMemory {
  runs: number;
  sources: number;
  full_text: number;
  spans: number;
  queries: number;
  last_run_id: string;
  last_seen: string;
  facets: Record<string, LiteratureFacetMemory>;
  gaps: Record<string, number>;
  saturations: Record<string, number>;
}

export interface LiteratureTopicMemory {
  topic_id: string;
  question: string;
  updated_at: string;
  modes: Record<string, LiteratureModeMemory>;
  recent_runs: Array<{
    run_id: string;
    role: string;
    mode: string;
    at: string;
    facets: string[];
    sources: number;
    full_text: number;
    spans: number;
    queries: number;
    coverage_score: number;
    saturation: string;
    gaps: string[];
    fixture_mode: boolean;
  }>;
}

export interface LiteratureMemorySnapshot {
  schema_version: string;
  count: number;
  topics: LiteratureTopicMemory[];
  boundary: string;
  generated_at?: string;
}

export interface CustomAgentRecord {
  id: string;
  name: string;
  role: string;
  role_label: string;
  purpose: string;
  enabled: boolean;
  advisory_only: boolean;
  writes: string[];
  stages: string[];
  stage: string;
  checks: string[];
  check_labels: string[];
  tools: string[];
  outputs: string[];
  created_at: string;
  updated_at: string;
}

export interface CustomAgentSnapshot {
  schema_version: string;
  generated_at: string;
  count: number;
  agents: CustomAgentRecord[];
  checks: Array<{ id: string; label: string; stage: string; tool: string; output: string; description: string }>;
  roles: Array<{ id: string; label: string }>;
  boundary: string;
}

export interface CustomAgentInput {
  name: string;
  role: string;
  purpose: string;
  checks: string[];
  enabled: boolean;
}

export interface EvolutionScope {
  id: string;
  label: string;
  kind: string;
  description: string;
  enabled: boolean;
  effective: boolean;
  allowed_by_master: boolean;
}

export interface EvolutionPolicySnapshot {
  schema_version: string;
  generated_at: string;
  enabled: boolean;
  scopes: EvolutionScope[];
  locked: Array<{ id: string; label: string; reason: string }>;
  updated_at: string;
  boundary: string;
}

export interface RuntimeSkillRecord {
  id: string;
  name: string;
  description: string;
  instructions: string;
  tools: string[];
  version: string;
  license: string;
  origin: string;
  content_hash: string;
  source: "imported" | "custom";
  enabled: boolean;
  execution: string;
  untrusted: boolean;
  risk_flags: string[];
  has_scripts: boolean;
  created_at: string;
  updated_at: string;
}

export interface RuntimeSkillSnapshot {
  schema_version: string;
  generated_at: string;
  count: number;
  skills: RuntimeSkillRecord[];
  boundary: string;
}

export interface SkillUsageSnapshot {
  schema_version: string;
  updated_at: string;
  count: number;
  skills: Record<string, {
    total: number;
    pass: number;
    warn: number;
    fail: number;
    blocked: number;
    needs_input: number;
    last_at: string;
  }>;
  entries: Array<{
    usage_id: string;
    skill_id: string;
    version: string;
    task_id: string;
    status: string;
    recorded_at: string;
  }>;
  boundary: string;
}

export interface SignerSnapshot {
  schema_version: string;
  count: number;
  signers: Array<{
    signer_id: string;
    name: string;
    key_id: string;
    created_at: string;
    active: boolean;
  }>;
  boundary: string;
}

export interface SkillVersionSnapshot {
  schema_version: string;
  active: Record<string, string>;
  available: Record<string, string[]>;
  history: Array<Record<string, unknown>>;
  boundary: string;
}

export interface OrchestrationRunSnapshot {
  run_id: string;
  topic: string;
  source: string;
  fixture_mode: boolean;
  scouts: Array<{
    role_id: string;
    name: string;
    facets: string[];
    budget: number;
    status: string;
    sources: number;
    full_text: number;
    spans: number;
    queries: number;
    saturation: string;
    coverage_score: number;
    gap_codes: string[];
  }>;
  merged: {
    sources: number;
    full_text: number;
    spans_count: number;
    queries: number;
    covered_facets: number;
    planned_facets: number;
    coverage_score: number;
    saturation: string;
    facet_coverage: Array<{
      facet: string;
      label: string;
      queries: number;
      sources: number;
      span_count: number;
      covered: boolean;
    }>;
    gaps: Array<{ code: string; message: string }>;
    scout_gaps: Record<string, string[]>;
  };
  idea: {
    run_id: string;
    status: string;
    candidates: Array<{
      idea_id: string;
      title: string;
      hypothesis: string;
      falsification: string;
      evidence_refs: string[];
      lens: string;
      evidence_count: number;
      source_count: number;
      novelty_status: string;
      testability: string;
      prior_art_scope?: string;
      prior_art_delta?: string;
      kill_criteria?: string;
      contrast_refs?: string[];
    }>;
    shortlist?: {
      ranked: Array<{
        rank: number;
        idea_id: string;
        evidence_count: number;
        source_count: number;
        prior_art_scope: string;
        novelty_status: string;
        testability: string;
        has_kill_criteria: boolean;
        has_contrast: boolean;
      }>;
      selection: string;
      criteria: string[];
      boundary: string;
    } | null;
    brief: {
      candidate_count: number;
      source_count: number;
      multi_ref_candidates: number;
      multi_source_candidates: number;
      lenses: Record<string, number>;
      gaps: string[];
      summary: string;
    } | null;
    warnings: string[];
  };
  custom_agents?: Array<{
    id: string;
    name: string;
    role_label: string;
    stage: string;
    checks: string[];
    check_labels: string[];
    tools: string[];
    outputs: string[];
    enabled: boolean;
    advisory_only: boolean;
    writes: string[];
  }>;
  advisory_notes?: Array<{
    id: string;
    agent_id: string;
    agent_name: string;
    check: string;
    check_label: string;
    status: string;
    summary: string;
    details: string[];
    boundary: string;
  }>;
  policy?: {
    enabled: boolean;
    scopes: Record<string, boolean>;
    locked: string[];
    memory_applied: boolean;
    suppressed_candidate: SkillCandidate | null;
    boundary: string;
  };
  memory: {
    recorded: {
      run_id: string;
      role: string;
      mode: string;
      sources: number;
      full_text: number;
      spans: number;
      queries: number;
      coverage_score: number;
      saturation: string;
      gaps: string[];
      fixture_mode: boolean;
    };
    next_focus: Array<{ facet: string; priority: number; reason: string }>;
    boundary: string;
  };
  skill_candidate: SkillCandidate | null;
  warnings: string[];
  boundary: string;
}

export interface RuntimeMemoryEntry {
  id: string;
  text: string;
  kind: MemoryKind;
  scope: string;
  source: string;
  created_at: string;
}

export interface RuntimeMemorySnapshot {
  schema_version: string;
  count: number;
  entries: RuntimeMemoryEntry[];
  boundary: string;
}

export interface RuntimeArchiveMeta {
  id: string;
  title: string;
  task_id: string;
  note: string;
  created_at: string;
  bytes: number;
}

export interface RuntimeArchiveSnapshot {
  schema_version: string;
  count: number;
  items: RuntimeArchiveMeta[];
  boundary: string;
}

export interface SnapshotResult<T> {
  data: T;
  source: "runtime" | "snapshot";
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 2600): Promise<T> {
  if (__STATIC_ONLY__) throw new Error("runtime disabled in static build");
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(runtimeBase + path, {
      ...init,
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...authHeaders(),
        ...(init?.headers ?? {})
      }
    });
    if (!response.ok) {
      const detail = await response.text().catch(() => "");
      const refusal = describeAuthRefusal(response.status, detail);
      throw new Error(refusal || `${response.status} ${detail.slice(0, 160)}`.trim());
    }
    return (await response.json()) as T;
  } finally {
    window.clearTimeout(timer);
  }
}

async function snapshot<T>(file: string): Promise<T> {
  const url = new URL(`${import.meta.env.BASE_URL}${file}`, document.baseURI).toString();
  const response = await fetch(url);
  if (!response.ok) throw new Error(`snapshot ${file} unavailable (${response.status})`);
  return (await response.json()) as T;
}

async function liveThenSnapshot<T>(path: string, file: string): Promise<SnapshotResult<T>> {
  try {
    return { data: await request<T>(path), source: "runtime" };
  } catch {
    return { data: await snapshot<T>(file), source: "snapshot" };
  }
}

export async function probeRuntime(): Promise<RuntimeHealth> {
  return request<RuntimeHealth>("/api/health");
}

export async function loadAgents(): Promise<SnapshotResult<AgentRegistrySnapshot>> {
  return liveThenSnapshot<AgentRegistrySnapshot>("/api/workspace/agents", "agent-registry.json");
}

export async function loadCommands(): Promise<SnapshotResult<CommandCatalogSnapshot>> {
  return liveThenSnapshot<CommandCatalogSnapshot>("/api/workspace/commands", "command-catalog.json");
}

export async function loadOrchestrationTopology(): Promise<SnapshotResult<OrchestrationPlan>> {
  return liveThenSnapshot<OrchestrationPlan>("/api/orchestrator/topology", "orchestration-topology.json");
}

export async function loadLiteratureMemory(): Promise<SnapshotResult<LiteratureMemorySnapshot>> {
  return liveThenSnapshot<LiteratureMemorySnapshot>("/api/literature/memory", "literature-memory.json");
}

export async function loadOrchestrationRun(): Promise<OrchestrationRunSnapshot> {
  return snapshot<OrchestrationRunSnapshot>("orchestration-run.json");
}

export async function loadCustomAgents(): Promise<SnapshotResult<CustomAgentSnapshot>> {
  return liveThenSnapshot<CustomAgentSnapshot>("/api/agents/custom", "custom-agents.json");
}

export async function createCustomAgent(input: CustomAgentInput): Promise<CustomAgentRecord> {
  return request<CustomAgentRecord>("/api/agents/custom", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function updateCustomAgent(
  id: string,
  patch: Partial<Pick<CustomAgentInput, "name" | "purpose" | "checks" | "enabled">>
): Promise<CustomAgentRecord> {
  return request<CustomAgentRecord>(`/api/agents/custom/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(patch)
  });
}

export async function deleteCustomAgent(id: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/agents/custom/${encodeURIComponent(id)}`, {
    method: "DELETE"
  });
}

export async function loadEvolutionPolicy(): Promise<SnapshotResult<EvolutionPolicySnapshot>> {
  return liveThenSnapshot<EvolutionPolicySnapshot>("/api/evolution/policy", "evolution-policy.json");
}

export async function updateEvolutionPolicy(input: {
  enabled?: boolean;
  scopes?: Record<string, boolean>;
}): Promise<EvolutionPolicySnapshot> {
  return request<EvolutionPolicySnapshot>("/api/evolution/policy", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function loadRuntimeSkills(): Promise<RuntimeSkillSnapshot> {
  return request<RuntimeSkillSnapshot>("/api/skills");
}

export async function loadSkillUsage(): Promise<SkillUsageSnapshot> {
  return request<SkillUsageSnapshot>("/api/skills/usage");
}

export async function loadSkillVersions(): Promise<SkillVersionSnapshot> {
  return request<SkillVersionSnapshot>("/api/skills/versions");
}

export async function loadSigners(): Promise<SignerSnapshot> {
  return request<SignerSnapshot>("/api/signers");
}

export async function importRuntimeSkills(
  skills: Array<{
    name: string;
    description: string;
    instructions: string;
    tools: string[];
    version?: string;
    license?: string;
    origin?: string;
    source?: "imported" | "custom";
  }>
): Promise<{ accepted: number; rejected: Array<{ name: string; reason: string }>; snapshot: RuntimeSkillSnapshot }> {
  return request<{
    accepted: number;
    rejected: Array<{ name: string; reason: string }>;
    snapshot: RuntimeSkillSnapshot;
  }>("/api/skills/import", {
    method: "POST",
    body: JSON.stringify({ skills })
  });
}

export async function toggleRuntimeSkill(id: string, enabled: boolean): Promise<RuntimeSkillRecord> {
  return request<RuntimeSkillRecord>(`/api/skills/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify({ enabled })
  });
}

export async function loadRuntimeMemory(): Promise<RuntimeMemorySnapshot> {
  return request<RuntimeMemorySnapshot>("/api/workspace/memory");
}

export async function createRuntimeMemory(input: {
  text: string;
  kind: MemoryKind;
  scope: string;
  source: string;
}): Promise<RuntimeMemoryEntry> {
  return request<RuntimeMemoryEntry>("/api/workspace/memory", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function deleteRuntimeMemory(id: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/workspace/memory/${encodeURIComponent(id)}`, {
    method: "DELETE"
  });
}

export async function loadRuntimeArchive(): Promise<RuntimeArchiveSnapshot> {
  return request<RuntimeArchiveSnapshot>("/api/workspace/archive");
}

export async function createRuntimeArchive(input: {
  title: string;
  task_id: string;
  note: string;
  payload: Record<string, unknown>;
}): Promise<RuntimeArchiveMeta> {
  return request<RuntimeArchiveMeta>("/api/workspace/archive", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function deleteRuntimeArchive(id: string): Promise<void> {
  await request<{ deleted: boolean }>(`/api/workspace/archive/${encodeURIComponent(id)}`, {
    method: "DELETE"
  });
}

export async function requestAutomationPlan(input: {
  topic: string;
  max_sources: number;
  run_dataset: "" | "iris" | "breast_cancer" | "chemlab";
  run_seeds: number;
}): Promise<AutomationPlan> {
  return request<AutomationPlan>("/api/workspace/actions/automation-plan", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function runBackendSkill(
  skillId: "literature-brief" | "hypothesis-triage" | "protocol-review" | "evidence-boundary",
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return request<Record<string, unknown>>("/api/workspace/actions/skill", {
    method: "POST",
    body: JSON.stringify({ skill_id: skillId, payload })
  });
}

export function runtimeBaseLabel(): string {
  return runtimeBase || "same-origin /api";
}

export function runtimeUrl(path: string): string {
  return `${runtimeBase}${path}`;
}

export async function createRun(input: RunCreateInput): Promise<RunJob> {
  return request<RunJob>("/api/runs", {
    method: "POST",
    body: JSON.stringify(input)
  });
}

export async function getRun(jobId: string): Promise<RunJob> {
  return request<RunJob>(`/api/runs/${encodeURIComponent(jobId)}`);
}

export async function loadRunArtifacts(jobId: string): Promise<RunArtifact[]> {
  const body = await request<{ job_id: string; artifacts: RunArtifact[] }>(
    `/api/runs/${encodeURIComponent(jobId)}/artifacts`,
    undefined,
    8000
  );
  return body.artifacts;
}

export interface EvolutionObservation {
  observation_id?: string;
  topic?: string;
  status?: string;
  q0_status?: string;
  max_sources?: number;
  route?: string;
  fixture_mode?: boolean;
  created_at?: string;
  observation_error?: string;
}

export interface EvolutionObservations {
  summary: {
    count?: number;
    fixture_count?: number;
    by_status?: Record<string, number>;
    by_q0?: Record<string, number>;
    recent?: EvolutionObservation[];
  };
  observations: EvolutionObservation[];
  boundary: string;
}

export interface EvolutionActive {
  active: {
    policy_id?: string;
    target?: string;
    patch?: Record<string, unknown>;
    expires_at?: string;
    human_reason?: string;
    source_eval?: Record<string, unknown>;
    /** Re-read of the source lease on every consumption; revocation reaches the runtime here. */
    lease_state?: string;
  } | null;
  expired: boolean;
  history_count?: number;
  /** Times an active policy was dropped because its lease no longer held. Demotion is automatic. */
  auto_deactivations?: number;
  boundary: string;
}

export async function loadEvolutionObservations(limit = 10): Promise<EvolutionObservations> {
  return request<EvolutionObservations>(
    `/api/evolution/observations?limit=${encodeURIComponent(String(limit))}`,
    undefined,
    5000
  );
}

export async function loadEvolutionActive(): Promise<EvolutionActive> {
  return request<EvolutionActive>("/api/evolution/active", undefined, 5000);
}

export async function loadRuns(limit = 20): Promise<RunJob[]> {
  const body = await request<{ jobs: RunJob[] }>(
    `/api/runs?limit=${encodeURIComponent(String(limit))}`
  );
  return body.jobs;
}

export async function loadProjects(): Promise<ProjectSummary[]> {
  const body = await request<{ projects: ProjectSummary[] }>("/api/projects", undefined, 8000);
  return body.projects;
}

export async function loadProjectExperiments(
  projectDir: string
): Promise<ProjectExperimentInventory> {
  return request<ProjectExperimentInventory>(
    `/api/project-experiments?project_dir=${encodeURIComponent(projectDir)}`,
    undefined,
    15000
  );
}

export async function loadProjectClosures(projectDir: string): Promise<ClosureInventory> {
  return request<ClosureInventory>(
    `/api/project-closures?project_dir=${encodeURIComponent(projectDir)}`,
    undefined,
    15000
  );
}

export async function loadAutopilotStatus(projectDir: string): Promise<AutopilotSnapshot> {
  return request<AutopilotSnapshot>(
    `/api/autopilot-status?project_dir=${encodeURIComponent(projectDir)}`,
    undefined,
    15000
  );
}

export async function loadModelCalls(): Promise<ModelCallRecord[]> {  const body = await request<{ calls: ModelCallRecord[] }>("/api/models/calls");
  return body.calls;
}

export async function loadRunEvents(jobId: string, after = 0): Promise<RunEvents> {
  return request<RunEvents>(
    `/api/runs/${encodeURIComponent(jobId)}/events?after=${encodeURIComponent(String(after))}`,
    undefined,
    6000
  );
}

export async function loadRunArtifactJson<T>(artifactUrl: string): Promise<T> {
  const response = await fetch(runtimeUrl(artifactUrl), { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`artifact ${response.status}`);
  return (await response.json()) as T;
}

export interface RsiEvalStory {
  split: string;
  status: string;
  metrics: Record<string, number>;
  n: number;
  simulation?: boolean;
  claim_eligible?: boolean;
  note?: string;
}

export interface RsiGateStory {
  id: string;
  label: string;
  state: string;
  detail?: string;
  metrics?: Record<string, number>;
}

export interface RsiEpisodeStory {
  episode_id: string;
  candidate_id: string;
  kind: string;
  target: string;
  patch: string;
  rationale: string;
  predicted_effect: string;
  predicted_metrics: Record<string, number>;
  scope: string;
  parent_id: string;
  created_at: string;
  decision: string;
  reason: string;
  simulation: boolean;
  claim_eligible: boolean;
  notes: string[];
  actuals: Record<string, number>;
  public_eval: RsiEvalStory;
  hidden_eval: RsiEvalStory;
  near_ood_eval: RsiEvalStory;
  regression_eval: RsiEvalStory;
  lease: { lease_id: string; scope: string; ttl_days: number; effective_status: string; status: string } | null;
  confirmation: { status: string; passed: boolean; split: string; delta: Record<string, number>; note?: string } | null;
  gates: RsiGateStory[];
  stage: string;
}

export interface RsiStory {
  schema_version: string;
  generated_at: string;
  read_only: boolean;
  ledger_path?: string;
  source_fingerprint?: string;
  base?: string;
  provenance?: { simulation_episodes?: number; episodes?: number; source?: string };
  summary: {
    headline: string;
    episodes: number;
    pending: number;
    approved: number;
    rejected: number;
    active_leases: number;
    confirmed: number;
    regressed: number;
    capability_claims: number;
    calibration: string;
    decided?: number;
    rejection_rate?: number | null;
    gate_verdict?: string;
    simulation_episodes?: number;
  };
  selected_episode_id: string | null;
  timeline: Array<{ id: string; label: string; state: string; detail: string }>;
  episodes: RsiEpisodeStory[];
  stage_process: Array<{
    stage: string;
    targets: string[];
    candidates: string[];
    status: string;
    evidence: string;
    detail: string;
  }>;
  tracking: {
    status: string;
    coverage: number;
    episodes_with_actuals: number;
    compared_episodes: number;
    metrics: Record<string, { n: number; mae: number; bias: number; direction_agreement: number }>;
  };
  warnings: string[];
  next_questions: string[];
  boundary: string;
}

export interface GovernancePreflight {
  schema_version: string;
  status: string;
  blockers: string[];
  checks: {
    spec_self_consistency: { checked: number; stale: Array<{ spec: string; problem: string }> };
    registry: { status: string; agents_exported?: number; agents_live?: number; changed?: Array<{ id: string; exported?: string; live?: string }> };
    tool_surfaces: { status: string; tools: number; problems: string[] };
  };
  faces: { mcp_tools: number; http_tools: number; cli_commands: number };
  boundary: string;
}

export async function loadGovernancePreflight(): Promise<GovernancePreflight> {
  return request<GovernancePreflight>("/api/research/preflight");
}

export async function fetchRsiStory(): Promise<SnapshotResult<RsiStory>> {
  return liveThenSnapshot<RsiStory>("/api/rsi/story", "rsi-story.json");
}
