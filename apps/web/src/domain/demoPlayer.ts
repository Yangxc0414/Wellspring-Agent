import type { DemoPlayerState, DemoStoryline, Message } from "./types";

export type { DemoPlayerState, DemoStoryline } from "./types";

/**
 * One-click full-flow demo player (一键演示完整流程).
 *
 * The player REPLAYS an already-completed seeded session message by message.
 * It is a presentation pointer, not an execution engine: nothing is written to
 * disk, no task field (gates/evidence/claim) is mutated, and the demo "sign"
 * only exists inside the player's in-memory state (reset on refresh), exactly
 * like FlowDemo's 模拟人签. All narration lines describe mechanisms — no new
 * numbers are introduced anywhere; numbers shown during playback come from the
 * seeded transcripts themselves (real storyline: 0.956 / iris 150x4 / seeds
 * 17,18,19 are quoted verbatim from runtime_data/e2e-closed-loop artifacts).
 */

export interface DemoStorylineMeta {
  id: DemoStoryline;
  /** The seeded session whose transcript is replayed. */
  taskId: string;
  label: string;
  sub: string;
  /** Honesty line: the three things that must be stated together (design/136). */
  basisNote: string;
  /** Stage where auto-play pauses for the claim human gate. */
  gateStage: string;
  /** Teaching storyline may offer 模拟人签（演示）; the real one must not — the
   * on-disk signature there is a delegated one and simulating a human sign
   * would blur exactly the distinction design/136 drew. */
  allowDemoSign: boolean;
}

export const DEMO_STORYLINES: Record<DemoStoryline, DemoStorylineMeta> = {
  teaching: {
    id: "teaching",
    taskId: "full-chain-demo",
    label: "教学版",
    sub: "完整九阶段 · 材料案例",
    basisNote: "演示数据 · 代理指标 · 不产生真实签名",
    gateStage: "S5b",
    allowDemoSign: true
  },
  real: {
    id: "real",
    taskId: "e2e-closed-loop",
    label: "真实闭环",
    sub: "Iris 协议验证 · 真实执行回放",
    basisNote: "真实执行 · fixture 语料 · 委托签非人签",
    gateStage: "S5b",
    allowDemoSign: false
  },
  ese: {
    id: "ese",
    taskId: "ese-ms-20261118-03",
    label: "ESE 闭环",
    sub: "真实仓库挖掘 · 3 repos / 5132 commits",
    basisNote: "真实执行 · 启发式标签 · claim 未人签",
    gateStage: "S5b",
    allowDemoSign: false
  }
};

export const DEMO_STORYLINE_ORDER: DemoStoryline[] = ["teaching", "real", "ese"];

/** Canonical stage labels, shared by the progress rail. Ids match the `stage`
 * tags already written on seeded transcript messages (and FlowDemo's STAGES). */
export const STAGE_LABELS: Record<string, string> = {
  S1: "文献检索",
  "S2–S3": "假设收敛",
  S4: "设计冻结",
  S5a: "复现执行",
  S5b: "证据判定",
  S6: "结果图",
  "S8–S12": "写作槽位",
  "S13–S16": "闭包检查",
  META: "自改进提案"
};

export function stageLabel(stageId: string): string {
  return STAGE_LABELS[stageId] ?? stageId;
}

/** FlowDemo's nine teaching stages, in panel order — ids match the stage tags
 * on the full-chain-demo transcript, so the panel can be driven by the player. */
export const TEACHING_STAGE_IDS = [
  "S1",
  "S2–S3",
  "S4",
  "S5a",
  "S5b",
  "S6",
  "S8–S12",
  "S13–S16",
  "META"
] as const;

export function teachingStageIndex(stageId: string | null): number {
  if (!stageId) return -1;
  return TEACHING_STAGE_IDS.indexOf(stageId as (typeof TEACHING_STAGE_IDS)[number]);
}

/** Ordered unique stage tags present in a transcript. Teaching yields the full
 * nine (S1→META); the real replay yields seven (no S6 figure, no META). */
export function demoStagePlan(messages: Message[]): string[] {
  const stages: string[] = [];
  for (const item of messages) {
    if (item.stage && !stages.includes(item.stage)) stages.push(item.stage);
  }
  return stages;
}

export interface DemoStageSpan {
  stage: string;
  first: number;
  last: number;
}

/**
 * Message index ranges per stage. Untagged messages (user turns, system notes)
 * are absorbed into the preceding staged message's span, so stepping/revealing
 * by stage never hides them. Messages before the first stage tag have no span.
 */
export function demoStageSpans(messages: Message[]): DemoStageSpan[] {
  const spans: DemoStageSpan[] = [];
  let current: DemoStageSpan | null = null;
  messages.forEach((item, index) => {
    if (item.stage && (!current || current.stage !== item.stage)) {
      current = { stage: item.stage, first: index, last: index };
      spans.push(current);
    } else if (current) {
      current.last = index;
    }
  });
  return spans;
}

export function createDemoPlayerState(storyline: DemoStoryline): DemoPlayerState {
  const meta = DEMO_STORYLINES[storyline];
  return {
    storyline,
    taskId: meta.taskId,
    revealCount: 0,
    stageId: null,
    stageTick: 0,
    playing: true,
    signed: false,
    finished: false
  };
}

/** Dwell per revealed message: cards need reading time, plain text less. */
export const DEMO_DWELL_TEXT_MS = 2600;
export const DEMO_DWELL_CARD_MS = 4200;

export function demoDwell(message: Message | undefined): number {
  if (!message) return DEMO_DWELL_TEXT_MS;
  return message.card ? DEMO_DWELL_CARD_MS : DEMO_DWELL_TEXT_MS;
}

/** The human-gate pause fires right after a gate-stage message is revealed. */
export function isDemoGateStage(storyline: DemoStoryline, stageId: string | null): boolean {
  if (!stageId) return false;
  return stageId === DEMO_STORYLINES[storyline].gateStage;
}

/**
 * Per-stage narration, written for the presenter. Every line describes what the
 * corresponding seeded messages actually say — teaching lines carry no numbers
 * at all; real lines quote only numbers already in that transcript.
 */
export const DEMO_NARRATION: Record<DemoStoryline, Record<string, string>> = {
  teaching: {
    S1: "把问题拆成可检索的子查询，先定义「什么算证据」——摘要只作线索，不生成 span。",
    "S2–S3": "从 coverage gap 生成候选假设；G1 人工收敛，候选不是 claim。",
    S4: "协议先于数据：主指标与 seeds 在 G2 冻结，执行器无权改写。",
    S5a: "本地执行写入 RunCapsule，EA 用 sha256 钉住结果；数值是演示代理指标。",
    S5b: "证据齐了但断言待人签——签名只能在本地 CLI 产生，网页不代签。",
    S6: "结果图绑定 EA；上游数据变更会把图标 stale 并暂停导出。",
    "S8–S12": "写作槽位只接受已签 claim / EA / closure 引用；Results 签署前保持 locked。",
    "S13–S16": "closure 核对 claim / EA / 签名 / 沿袭的一致性；G5 必须人签。",
    META: "有效经验写成方法补丁候选；lease 由人授予后才生效。"
  },
  real: {
    S1: "真实执行的起点：fixture 语料只覆盖 2/6 检索面向，覆盖缺口如实登记。",
    "S2–S3": "两个候选帧经独立预审（advance=0 / revise=2），G1 人工收敛到 IDEA-02。",
    S4: "协议卡 design_sha256 绑定后 G2 判 pass；主指标 accuracy 不可改写。",
    S5a: "真实本地执行：iris 150×4、seeds 17/18/19、平均 accuracy 0.956；EA 不可变。",
    S5b: "签署是 autopilot 委托签（submission=false）——不是人签；这条 claim 不能外推。",
    "S8–S12": "8 个章节槽位全部有绑定状态；Results 只引已签 claim，不重算数值。",
    "S13–S16": "closure 16 项检查 ready；G5 仍是 needs_human——机制闭环了，人签没有发生。"
  },
  ese: {
    S1: "ESE 的 S1 是语料组装：四条可检验子问题 + 3 仓库 HEAD 固定 + 启发式标签。",
    "S2–S3": "四条 RQ 收敛为一条可检验断言（合并样本 + 分层）；G1 由人确认。",
    S4: "跑数之前冻结协议：分层与置换计划、固定种子；capsule 绑定 protocol sha256。",
    S5a: "真实执行 3 repos / 5132 commits：合并 0.3749，缺陷修复 0.4136 vs 其它 0.3672（+0.0464，p=0.015）。",
    S5b: "分层揭示 click 内方向反转——statement 只能写三仓库合并口径；claim 待人工签署。",
    S6: "本轮未产出绑定 EA 的结果图；图不脱离 EA 单独引用。",
    "S8–S12": "claim 人签前写作槽位不上数：allowed_result_numbers 为空，Results/Abstract locked。",
    "S13–S16": "closure 待执行、signature 待人工：run claim → closure ese-check → closure ese-sign，都在本地 CLI。",
    META: "过程经验写入记忆（引用必须带分层口径）；无可准入的参数改进，不生成自进化候选。"
  }
};

export function demoNarration(storyline: DemoStoryline, stageId: string | null): string {
  if (!stageId) return "回放开始：从第一条消息起，按阶段逐步演示完整闭环。";
  return DEMO_NARRATION[storyline][stageId] ?? `${stageId} ${stageLabel(stageId)}`;
}

/** Persistent honesty line shown on the player bar while revealing. */
export const DEMO_BANNER =
  "演示模式 · 回放已完成的会话：不调用模型、不执行实验、不写盘、不生成签名；右侧面板显示最终状态。";

/** Closing line once the transcript is fully revealed. */
export const DEMO_FINISHED_NOTE = "回放结束：全部消息已揭示。签名与经验采纳在真实流程中均由人在本地 CLI 完成。";

export function demoGateHint(storyline: DemoStoryline): string {
  switch (storyline) {
    case "teaching":
      return "停在 claim 人工门：证据齐了，statement 与 human_reason 仍由人定稿。";
    case "real":
      return "停在 S5b：盘上的签名是 autopilot 委托签（submission=false），不是人签。";
    case "ese":
      return "停在 S5b：claim 已起草（只能写分层口径），statement 与 human_reason 由人定稿——网页不代签。";
  }
}
