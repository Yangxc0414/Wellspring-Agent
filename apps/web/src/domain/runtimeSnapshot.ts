import type {
  AutoStage,
  Coverage,
  EvidenceItem,
  EvidencePackage,
  Gate,
  GateStatus,
  Protocol,
  ResearchTask,
  RunRecord,
  RuntimeSource
} from "./types";

interface RuntimeGap {
  code?: string;
  message?: string;
}

interface RuntimeSpan {
  span_id?: string;
  source_id?: string;
  section?: string;
  text?: string;
}

export interface RuntimeDemo {
  run_id?: string;
  topic?: string;
  status?: string;
  fixture_mode?: boolean;
  gates?: Array<{ gate?: string; status?: string; reason?: string }>;
  modules?: Record<string, unknown>;
  evidence_packages?: EvidencePackage[];
}

type Loose = Record<string, unknown>;

function object(value: unknown): Loose {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Loose) : {};
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function number(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function array<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function mapGateStatus(value: string): GateStatus {
  if (value === "ready" || value === "pass") return "pass";
  if (value === "needs_human") return "needs_human";
  if (value === "blocked") return "blocked";
  if (value === "pending") return "pending";
  return "not_started";
}

function spanRefsForMessage(spans: RuntimeSpan[], message: string): string[] {
  const matched = spans
    .filter((span) => span.source_id && message.includes(span.source_id))
    .map((span) => text(span.span_id))
    .filter(Boolean);
  return Array.from(new Set(matched)).slice(0, 4);
}

function buildEvidence(demo: RuntimeDemo): EvidenceItem[] {
  const modules = object(demo.modules);
  const literature = object(modules.literature);
  const coverage = object(literature.coverage);
  const brief = object(literature.brief);
  const spans = array<RuntimeSpan>(literature.spans);
  const idea = object(modules.idea);
  const run = object(modules.run);
  const runEvidence = object(run.evidence);
  const claimDraft = object(run.claim_draft_record);
  const evidence: EvidenceItem[] = [];

  const gaps = [
    ...array<RuntimeGap | string>(coverage.gaps),
    ...array<RuntimeGap | string>(brief.gaps)
  ];
  gaps.forEach((gap, index) => {
    const message = typeof gap === "string"
      ? gap
      : text(gap.message) || text(gap.code) || "coverage gap";
    const code = typeof gap === "string" ? gap : text(gap.code);
    evidence.push({
      id: `GAP-${String(index + 1).padStart(3, "0")}`,
      kind: "gap",
      status: "open",
      text: message,
      scope: `S1/${text(demo.run_id) || "runtime"}`,
      refs: spanRefsForMessage(spans, message),
      note: code
    });
  });

  array<Loose>(idea.candidates).forEach((candidate, index) => {
    const priorArt = text(candidate.prior_art_scope);
    const hasContrast = array<string>(candidate.contrast_refs).length > 0;
    evidence.push({
      id: text(candidate.idea_id) || `CAND-${index + 1}`,
      kind: "hypothesis",
      status: "candidate",
      text: `${text(candidate.title)}\n${text(candidate.hypothesis)}`.trim(),
      scope: "S2–S3 / needs G1",
      refs: array<string>(candidate.evidence_refs).slice(0, 6),
      note: [
        text(candidate.falsification),
        priorArt ? `prior-art ${priorArt}` : "",
        hasContrast ? "A/B contrast" : ""
      ].filter(Boolean).join(" · ")
    });
  });

  if (text(claimDraft.statement)) {
    evidence.push({
      id: "CLAIM-DRAFT",
      kind: "claim",
      status: "unsigned",
      text: text(claimDraft.statement),
      scope: text(claimDraft.scope) || "S5 / needs human",
      refs: [text(runEvidence.artifact_id), ...array<string>(claimDraft.evidence_refs)].filter(Boolean),
      note: "runtime 只产 claim draft；必须离线人签，不能在网页签署。"
    });
  }

  return evidence;
}

function buildProtocol(demo: RuntimeDemo): Protocol | null {
  const modules = object(demo.modules);
  const design = object(modules.experiment);
  if (!text(design.hypothesis) && !text(design.primary_metric)) return null;
  return {
    hypothesis: text(design.hypothesis) || "待人工补全",
    baseline: text(design.baseline) || "待人工补全",
    metric: text(design.primary_metric) || "待人工补全",
    seeds: number(design.seeds) || 3,
    controls: array<string>(design.controls)
  };
}

function buildRun(demo: RuntimeDemo): RunRecord | null {
  const modules = object(demo.modules);
  const run = object(modules.run);
  const capsule = object(run.capsule);
  if (!text(capsule.run_id)) return null;
  const evidence = object(run.evidence);
  const metrics = array<Loose>(capsule.metrics_by_seed);
  const baselineValue = metrics
    .map((item) => item.baseline_accuracy ?? item.baseline_r2)
    .find((value) => typeof value === "number");
  return {
    id: text(capsule.run_id),
    dataset: text(capsule.dataset_id),
    seeds: array<number>(capsule.seeds).length,
    metric: text(capsule.metric_name),
    mean: number(capsule.mean),
    baseline: typeof baselineValue === "number" ? baselineValue : null,
    ea: text(evidence.artifact_id),
    status: text(capsule.status)
  };
}

function buildStages(demo: RuntimeDemo): AutoStage[] {
  const modules = object(demo.modules);
  const literature = object(modules.literature);
  const synthesis = object(modules.synthesis);
  const idea = object(modules.idea);
  const experiment = object(modules.experiment);
  const run = object(modules.run);
  const figure = object(modules.figure);
  const paper = object(modules.paper);
  const status = (done: boolean): AutoStage["status"] => (done ? "done" : "pending");
  const runDone = Boolean(text(object(run.capsule).run_id));
  const claimUnsigned = Boolean(text(object(run.claim_draft_record).statement));
  return [
    { id: "S1", label: "文献检索", cmd: "retrieval.query", output: "runtime evidence", status: status(array<RuntimeSpan>(literature.spans).length > 0) },
    { id: "S1b", label: "跨来源综合", cmd: "literature.synthesize", output: "theme × source matrix", status: status(array<Loose>(synthesis.themes).length > 0) },
    { id: "S2–S3", label: "假设收敛", cmd: "idea.frame", output: "runtime candidates", status: status(array<Loose>(idea.candidates).length > 0) },
    { id: "S4", label: "设计冻结", cmd: "design.freeze", output: "G2 design draft", status: status(Boolean(text(experiment.hypothesis))) },
    { id: "S5a", label: "复现执行", cmd: "run.work", output: "runtime RunCapsule", status: status(runDone) },
    { id: "S5b", label: "证据判定", cmd: "judge.verify", output: "claim draft needs human", status: claimUnsigned ? "waiting" : "pending", gate: true },
    { id: "S6", label: "结果图", cmd: "figure.render", output: "figure manifest", status: status(Boolean(text(figure.figure_id))) },
    { id: "S8–S12", label: "写作槽位", cmd: "paper.bind", output: "paper.md + slots", status: status(array<Loose>(paper.draft).length > 0) },
    { id: "S13–S16", label: "闭包检查", cmd: "closure.check", output: "not run by runtime", status: "skipped" },
    { id: "META", label: "自进化提案", cmd: "rsi.propose", output: "not run by runtime", status: "skipped" }
  ];
}

export function applyRuntimeSnapshot(
  task: ResearchTask,
  demo: RuntimeDemo,
  source: RuntimeSource
): Partial<ResearchTask> {
  const modules = object(demo.modules);
  const literature = object(modules.literature);
  const coverage = object(literature.coverage);
  const hits = array<Loose>(literature.hits);
  const spans = array<RuntimeSpan>(literature.spans);
  const coveragePatch: Coverage = {
    sources: number(coverage.sources_found) || hits.length,
    spans: number(coverage.spans_extracted) || spans.length,
    gaps: array<RuntimeGap>(coverage.gaps).length + array<RuntimeGap | string>(object(literature.brief).gaps).length,
    abstractOnly: hits.filter((hit) => hit.full_text === false).length
  };
  const gates: Gate[] = array<{ gate?: string; status?: string; reason?: string }>(demo.gates).map((gate) => ({
    id: text(gate.gate) || "GATE",
    status: mapGateStatus(text(gate.status)),
    reason: text(gate.reason)
  }));
  const protocol = buildProtocol(demo);
  const run = buildRun(demo);
  const stages = buildStages(demo);
  const completedStages = stages
    .map((stage, index) => (stage.status === "done" ? index : -1))
    .filter((index) => index >= 0);

  return {
    goal: text(demo.topic) || task.goal,
    coverage: coveragePatch,
    gates: gates.length ? gates : task.gates,
    evidence: buildEvidence(demo),
    evidencePackages: Array.isArray(demo.evidence_packages)
      ? array<EvidencePackage>(demo.evidence_packages)
      : task.evidencePackages,
    protocol: protocol ?? task.protocol,
    protocolFrozen: text(object(modules.protocol).status) === "frozen",
    run: run ?? task.run,
    autoStages: stages,
    completedStages,
    stage: stages[6]?.status === "done" ? 6 : task.stage,
    status: "active",
    runtime: {
      source,
      runId: text(demo.run_id),
      appliedAt: new Date().toISOString()
    },
    updatedAt: new Date().toISOString()
  };
}

export function defaultRuntimeSource(task: ResearchTask): RuntimeSource {
  const topic = `${task.goal} ${task.name}`;
  if (/[\u4e00-\u9fff]/.test(topic)) return "fixture";
  return "real_corpus";
}

export function runtimeSourceLabel(source: RuntimeSource): string {
  if (source === "openalex") return "OpenAlex 摘要检索（无全文 → 不生成 span）";
  if (source === "real_corpus") return "冻结 CC-BY 真实正文（BM25）";
  if (source === "local") return "本地 PDF/TXT/MD 全文（保留页码）";
  return "fixture 演示语料（不可引用）";
}

export function runtimeRunState(card?: {
  status?: string;
  stoppedAt?: string;
  taskStatus?: string;
}): string {
  if (!card) return "WAITING";
  if (card.status === "failed" || card.taskStatus === "failed") return "FAILED";
  if (card.status === "queued") return "QUEUED";
  if (card.status === "running") return "RUNNING";
  if (card.stoppedAt || card.taskStatus === "needs_human") return "NEEDS HUMAN";
  return "COMPLETED";
}
