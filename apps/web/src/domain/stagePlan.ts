/**
 * 执行流程 × 研究方法：把「方法声明的研究编排」投影成 RESEARCH FLOW 的两条轨道
 * （design/169）。
 *
 * 背景：面板原先只读会话里的 stage 标签，于是每个任务都长得一样——一条
 * S1→…→META 的通用流水线。但方法注册表里，十个方法绑定两种组合接线，
 * 阶段顺序本来就不同：验证式「假设先于方案」，探索式「方案先于假设、假设事后
 * 从证据归纳」（Easterbrook et al. 2008；Creswell 2014）。所以这里把
 * `stagePlanFor`（method_registry.stage_plan 的前端镜像）落成面板数据：
 *
 *  - plan：本方法声明走过的阶段，顺序由 composition.wiring 决定，每步带
 *    registry 的 stage_task（本方法在这一阶段要做什么）与接线理由；
 *  - governance：闭包（S13-S16）与经验（META）不属于任何方法的 fit_stages，
 *    是治理固定层——所有方法都走，因此单独一条轨道，不混进「方法差异」；
 *  - extras：会话实际走过、但本方法计划不含的阶段。执行器当前仍全阶段执行
 *    （design/165 的边界），所以它们真实存在；把它们显式列出来，而不是从
 *    列表里删掉——删掉会让面板假装流程已经按方法剪裁过。
 *
 * 纯投影：不读盘、不改注册表、不产生 Claim，也不改变任何门禁语义。
 */

import { AUTO_STAGE_CATALOG } from "./catalog.ts";
import { demoStagePlan, stageLabel } from "./demoPlayer.ts";
import { STAGE_MODULE_CONTRACTS } from "./gateContracts.ts";
import {
  stagePlanFor,
  type MethodRegistryData,
  type MethodRegistryMethod
} from "./methodModel.ts";
import type { Message } from "./types";

/** 治理固定层：不属于方法差异，所有会话都必须走。 */
export const GOVERNANCE_STAGES = new Set(["S13-S16", "META"]);

/** 哪个阶段里坐着哪道门（与方法无关，由治理定义）。 */
export const GATE_FOR_SLOT: Record<string, string> = {
  "S2-S3": "G1",
  S4: "G2",
  S5b: "人签",
  "S13-S16": "G5"
};

/** 会话标签用 `S5a` 表示执行，注册表槽位叫 `S5`；其余只差一个连字符。 */
const SLOT_ALIASES: Record<string, string> = { S5a: "S5" };

/** 阶段 id 的规范形：en dash / em dash 一律归一成 ASCII 连字符。 */
export function normalizeStageId(raw: string): string {
  return raw.trim().replace(/[–—−]/g, "-");
}

/**
 * 会话标签 → 注册表槽位。返回 null 表示注册表没有对应槽位（如 META，或
 * 未来新增但尚未建模的阶段）——调用方必须如实显示「未映射」，不能猜。
 */
export function slotForStage(raw: string, known: Set<string>): string | null {
  const id = normalizeStageId(raw);
  if (known.has(id)) return id;
  const alias = SLOT_ALIASES[id];
  return alias && known.has(alias) ? alias : null;
}

const COMMANDS: Record<string, string> = Object.fromEntries(
  AUTO_STAGE_CATALOG.map((stage) => [normalizeStageId(stage.id), stage.cmd])
);

/** 该槽位在 CLI 里的命令；S5 槽位复用 S5a 的 `run.work`，S1b 没有命令。 */
export function slotCommand(slot: string): string | null {
  if (COMMANDS[slot]) return COMMANDS[slot];
  if (slot === "S5") return COMMANDS.S5a ?? null;
  return null;
}

/** 槽位 → STAGE_MODULE_CONTRACTS 的键（契约表沿用了会话标签的写法）。 */
const CONTRACT_KEYS: Record<string, string> = {
  S5: "S5a",
  "S2-S3": "S2–S3",
  "S8-S12": "S8–S12",
  "S13-S16": "S13–S16"
};

export function contractKeyFor(slot: string): string | null {
  const key = CONTRACT_KEYS[slot] ?? slot;
  return STAGE_MODULE_CONTRACTS[key] ? key : null;
}

export interface MethodFlowStep {
  slot: string;
  /** 注册表里的阶段名（方法层叫法），缺失时退回会话层标签。 */
  name: string;
  /** 本方法在这一阶段的任务卡（registry.stage_tasks[slot]）。 */
  task: string;
  gate: string | null;
  /** 产出该槽位的接线要素与理由（解释「为什么这个阶段排在这里」）。 */
  element: string | null;
  rationale: string | null;
  /** fit_stages 声明了、但组合接线没走到：诚实的扩展缝，不算计划内。 */
  uncovered: boolean;
  /** 会话里落在这一槽位上的 stage 标签（S5 可能来自 S5a）。 */
  sessionStageIds: string[];
  messageCount: number;
}

export interface MethodFlowExtra {
  id: string;
  label: string;
  reason: "out_of_plan" | "unmapped";
  messageCount: number;
}

export interface MethodFlowOrderMismatch {
  planned: string[];
  actual: string[];
  /** 第一个不一致的下标。 */
  at: number;
}

export interface MethodFlow {
  methodId: string;
  methodName: string;
  methodNameEn: string;
  compositionId: string;
  compositionLabel: string;
  compositionSub: string;
  iterationKind: string;
  iterationDetail: string;
  /** 本方法声明的编排（按接线顺序，含未覆盖缝）。 */
  steps: MethodFlowStep[];
  /** 会话走到的治理固定阶段（闭包 / 经验），全部方法共有。 */
  governance: MethodFlowStep[];
  /** 会话走过、但本方法计划与治理层都不含的阶段。 */
  extras: MethodFlowExtra[];
  /** 计划内、本会话没有消息的阶段。 */
  missing: string[];
  /** 计划顺序与会话实际顺序是否一致；不一致时给出第一处分歧。 */
  orderMismatch: MethodFlowOrderMismatch | null;
}

function countMessages(messages: Message[], slotOf: (stage: string) => string | null, slot: string) {
  let count = 0;
  for (const message of messages) {
    if (!message.stage) continue;
    // A slotless stage (META) still owns messages: match the tag itself, not
    // just the registry slot, otherwise the governance row renders as empty.
    if (slotOf(message.stage) === slot || normalizeStageId(message.stage) === slot) count += 1;
  }
  return count;
}

/**
 * 把「方法声明」与「会话实际」接成面板数据。registry 缺失或方法无组合绑定时
 * 返回 null——调用方必须退回只按会话标签渲染，并说明为什么。
 */
export function buildMethodFlow(
  method: MethodRegistryMethod,
  registry: MethodRegistryData,
  messages: Message[]
): MethodFlow | null {
  const plan = stagePlanFor(method, registry);
  if (!plan) return null;
  const composition = (registry.compositions ?? []).find((item) => item.id === plan.compositionId);
  const known = new Set((registry.stages ?? []).map((stage) => normalizeStageId(stage.id)));
  const names = new Map(
    (registry.stages ?? []).map((stage) => [normalizeStageId(stage.id), stage.name])
  );
  const slotOf = (stage: string) => slotForStage(stage, known);
  const elementFor = (slot: string) => {
    for (const step of composition?.wiring ?? []) {
      const slots = (composition?.slot_map?.[step.element] ?? []).map(normalizeStageId);
      if (slots.includes(slot)) return step;
    }
    return null;
  };

  const tagsBySlot = new Map<string, string[]>();
  for (const tag of demoStagePlan(messages)) {
    const slot = slotOf(tag);
    if (!slot) continue;
    tagsBySlot.set(slot, [...(tagsBySlot.get(slot) ?? []), tag]);
  }

  const steps: MethodFlowStep[] = plan.stages.map((step) => {
    const slot = normalizeStageId(step.slot);
    const element = elementFor(slot);
    return {
      slot,
      name: names.get(slot) ?? stageLabel(slot),
      task: step.task,
      gate: GATE_FOR_SLOT[slot] ?? null,
      element: element?.element ?? null,
      rationale: element?.rationale ?? null,
      uncovered: Boolean(step.uncovered),
      sessionStageIds: tagsBySlot.get(slot) ?? [],
      messageCount: countMessages(messages, slotOf, slot)
    };
  });

  const plannedSlots = new Set(steps.filter((step) => !step.uncovered).map((step) => step.slot));

  const governance: MethodFlowStep[] = [];
  const extras: MethodFlowExtra[] = [];
  for (const tag of demoStagePlan(messages)) {
    const slot = slotOf(tag);
    const isMeta = normalizeStageId(tag) === "META";
    if ((slot && GOVERNANCE_STAGES.has(slot)) || isMeta) {
      const id = slot ?? "META";
      if (governance.some((step) => step.slot === id)) continue;
      governance.push({
        slot: id,
        name: names.get(id) ?? stageLabel(tag),
        task: "",
        gate: GATE_FOR_SLOT[id] ?? null,
        element: "经验",
        rationale: null,
        uncovered: false,
        sessionStageIds: [tag],
        messageCount: countMessages(messages, slotOf, id)
      });
      continue;
    }
    if (slot && plannedSlots.has(slot)) continue;
    extras.push({
      id: tag,
      label: stageLabel(tag),
      reason: slot ? "out_of_plan" : "unmapped",
      messageCount: countMessages(messages, slotOf, slot ?? normalizeStageId(tag))
    });
  }

  // 计划顺序 vs 会话顺序：只看计划内的槽位，治理层与计划外不参与。
  const actual: string[] = [];
  for (const tag of demoStagePlan(messages)) {
    const slot = slotOf(tag);
    if (slot && plannedSlots.has(slot) && !actual.includes(slot)) actual.push(slot);
  }
  const expected = steps
    .filter((step) => !step.uncovered)
    .map((step) => step.slot)
    .filter((slot) => actual.includes(slot));
  let at = -1;
  const span = Math.max(actual.length, expected.length);
  for (let index = 0; index < span; index += 1) {
    if (actual[index] !== expected[index]) {
      at = index;
      break;
    }
  }

  return {
    methodId: method.id,
    methodName: method.name_zh,
    methodNameEn: method.name_en,
    compositionId: plan.compositionId,
    compositionLabel: plan.label,
    compositionSub: composition?.sub ?? "",
    iterationKind: method.iteration_rule?.kind ?? "",
    iterationDetail: method.iteration_rule?.detail ?? "",
    steps,
    governance,
    extras,
    missing: steps.filter((step) => step.messageCount === 0).map((step) => step.slot),
    orderMismatch: at >= 0 ? { planned: expected, actual, at } : null
  };
}
