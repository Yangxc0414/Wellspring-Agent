import { methodForTask, SESSION_METHOD, type MethodRegistryData, type MethodRegistryMethod } from "./methodModel.ts";
import { demoStagePlan, stageLabel } from "./demoPlayer.ts";
import { claimSignatureLabel } from "./claimSignature.ts";
import type { ResearchTask } from "./types.ts";

/**
 * Cross-task comparison for empirical research sessions (design/150).
 *
 * The MDD story in one view: the SAME governance slots are instantiated
 * differently by different empirical tasks — S1 is corpus assembly for
 * repository mining and retrieval for a protocol validation; the baseline
 * policy differs (paired delta vs mean-only under a not_verifiable
 * min_delta); the claim scope differs. Everything here is derived from the
 * tasks' own fields and transcripts — no new numbers, no invented labels.
 */

/** Deterministic comparison order (most concrete empirical run first). */
export const COMPARE_TASK_ORDER = ["ese-ms-20261118-03", "e2e-closed-loop", "full-chain-demo"];

export interface TaskCompareRow {
  taskId: string;
  name: string;
  method: MethodRegistryMethod | null;
  /** Evidence source: the run's dataset, or the coverage profile for runs without one. */
  dataset: string | null;
  metric: string | null;
  seeds: string | null;
  /** How the baseline is treated — this is where methods differ hardest. */
  baseline: string | null;
  claim: {
    id: string;
    badge: string;
    scope: string;
    text: string;
  } | null;
  /** Stage slots the session actually walked (canonical order, verbatim tags). */
  stagesWalked: string[];
  /** The first staged message's opening line — the slot's activity in this task's own words. */
  firstStageQuote: string | null;
  /** Gates that still need a human or are blocked. */
  openGates: string[];
  /** design/161: tags unique to this task's method among the compared tasks —
   * the essential-difference markers, computed not curated. */
  uniqueTags: string[];
}

function firstLine(text: string): string {
  const line = text.split("\n").find((part) => part.trim().length > 0) ?? text;
  return line.replace(/^#+\s*/, "").replace(/\*\*/g, "").trim();
}

function truncate(text: string, max: number): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function compareEmpiricalTasks(
  tasks: ResearchTask[],
  registry: MethodRegistryData | null
): TaskCompareRow[] {
  const byId = new Map(tasks.map((task) => [task.id, task]));
  const rows: TaskCompareRow[] = [];
  for (const taskId of COMPARE_TASK_ORDER) {
    const task = byId.get(taskId);
    if (!task) continue;
    const claim = task.evidence.find((item) => item.kind === "claim");
    const claimLabel = claimSignatureLabel(claim);
    const stagesWalked = demoStagePlan(task.messages);
    const firstStaged = task.messages.find((item) => item.stage === stagesWalked[0]);
    const openGates = task.gates
      .filter((gate) => gate.status === "needs_human" || gate.status === "blocked")
      .map((gate) => gate.id);
    rows.push({
      taskId: task.id,
      name: task.name,
      method: methodForTask(task, registry),
      uniqueTags: [],
      dataset: task.run?.dataset ?? null,
      metric: task.run?.metric ?? task.protocol?.metric ?? null,
      seeds: task.run
        ? Array.isArray(task.run.seeds)
          ? task.run.seeds.join(", ")
          : String(task.run.seeds)
        : task.protocol
          ? String(task.protocol.seeds)
          : null,
      baseline: task.run
        ? task.run.baseline === null || task.run.baseline === undefined
          ? "无配对基线读数——只报均值/差值与检验，不宣称超过基线"
          : `配对基线 ${task.run.baseline}`
        : task.protocol?.baseline ?? null,
      claim: claim
        ? {
            id: claim.id,
            badge: claimLabel.badge,
            scope: claim.scope,
            text: truncate(claim.text, 96)
          }
        : null,
      stagesWalked,
      firstStageQuote: firstStaged ? truncate(firstLine(firstStaged.text), 64) : null,
      openGates
    });
  }
  // design/161: tags held by this method but by NO other compared method —
  // the essential-difference markers made computable.
  const tagOwners = new Map<string, Set<number>>();
  rows.forEach((row, rowIndex) => {
    for (const tag of row.method?.tags ?? []) {
      const owners = tagOwners.get(tag) ?? new Set<number>();
      owners.add(rowIndex);
      tagOwners.set(tag, owners);
    }
  });
  rows.forEach((row) => {
    row.uniqueTags = [...(row.method?.tags ?? [])].filter(
      (tag) => (tagOwners.get(tag)?.size ?? 0) === 1
    );
  });
  return rows;
}

/** The two seeded empirical methods whose protocol fields contrast best. */
export const COMPARE_METHOD_ORDER = ["repository-mining", "controlled-experiment"];

export function compareMethodProfiles(
  registry: MethodRegistryData | null
): Array<{ id: string; nameZh: string; protocolFields: string[]; blockers: string[]; cannotSupport: string[] }> {
  if (!registry) return [];
  return COMPARE_METHOD_ORDER.map((id) => {
    const method = registry.methods.find((item) => item.id === id);
    if (!method) return null;
    return {
      id: method.id,
      nameZh: method.name_zh,
      protocolFields: method.protocol_fields,
      blockers: method.checks.filter((check) => check.severity === "blocker").map((check) => check.id),
      cannotSupport: method.cannot_support
    };
  }).filter((row): row is NonNullable<typeof row> => row !== null);
}

/** Guard so the UI never renders a comparison built from an unmapped task. */
export function isComparableTask(taskId: string): boolean {
  return taskId in SESSION_METHOD;
}

export { stageLabel };
