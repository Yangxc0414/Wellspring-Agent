import type { GateCommandInput } from "./gateCommands.ts";
import { claimSignCommand, closureSignCommand, g1DecisionCommand, protocolFreezeCommand } from "./gateCommands.ts";

/**
 * Human-gate contracts, transcribed from the backend's own sources — AGENTS.md
 * §4/§5 and the module SPEC files (run v0.8.0, writing v0.9.0, closure/lineage,
 * idea-review). This file is a READ-ONLY projection for the frontend dialogs:
 * it may not invent invariants; every line must be traceable to one of those
 * sources. The browser still never performs a gate — the dialogs collect the
 * human's decision and reason, and surface the exact CLI command (gateCommands.ts
 * mirrors research_agent/cli.py) plus a copyable decision record.
 */

export type HumanGateId = "G1" | "G2" | "S5b" | "G5";

export interface GateContract {
  id: HumanGateId;
  /** Stage label the gate sits between. */
  stage: string;
  eyebrow: string;
  title: string;
  /** What this gate asks the human to decide (the dialog's questions). */
  lede: string;
  /** Hard invariants the backend enforces around this gate (from SPECs). */
  contract: string[];
  /** Backend owner: module ids / files, for provenance. */
  owner: string;
  /** CLI command builder mirroring research_agent/cli.py. */
  command: (input: GateCommandInput, decision: GateDecision) => string;
}

/** What the human chose in the dialog. The browser only *collects* this. */
export interface GateDecision {
  /** G1: selected candidate id (e.g. CAND-H1 / IDEA-02). */
  ideaId?: string;
  /** The mandatory human_reason every CLI sign command requires. */
  humanReason?: string;
}

export const GATE_CONTRACTS: Record<HumanGateId, GateContract> = {
  G1: {
    id: "G1",
    stage: "S2–S3 → S4",
    eyebrow: "G1 · HUMAN GATE",
    title: "候选收敛：由人定主假设",
    lede:
      "S2–S3 产出的候选假设不是 claim。G1 由人完成语义收敛：选定主假设与竞争假设，收敛结果写入 g1-decision.json，之后才能进入 S4 设计冻结。",
    contract: [
      "候选/想法不能直接写 Claim、EA 或进入设计（modules/idea · AGENTS.md §5）",
      "独立预审（advance/revise/reject）只是结构信号，不是新颖性证明（idea_review）",
      "agent 不得代签 G1；收敛决策由人做出并留 human_reason（pipeline strict 模式在 needs_g1 处停下）",
      "词法新颖性 ≠ 文献新颖性；收敛前需人工核对查新（design/13）"
    ],
    owner: "modules/idea · modules/orchestrator · research_agent/pipeline.py (flow g1)",
    command: (input, decision) => g1DecisionCommand(input, decision.ideaId, decision.humanReason)
  },
  G2: {
    id: "G2",
    stage: "S4 → S5a",
    eyebrow: "G2 · HUMAN GATE",
    title: "协议冻结：协议先于数据",
    lede:
      "假设、基线、主指标、seeds、对照组在此定死并哈希绑定 ProtocolCard。冻结之后执行器只做提取与统计，无权改写协议；没有冻结协议，run 模块拒绝执行。",
    contract: [
      "没有冻结协议不得执行：protocol_sha256 必须与 ProtocolCard 的 design_sha256 一致（modules/run SPEC）",
      "主指标冻结后不可改写；改协议 = 重新走 G2，而不是改完继续跑",
      "设计审计（design_audit）blockers=0 才具备冻结条件（modules/ccfa-audit）",
      "冻结产物是 protocol-card.json；strict 模式在 needs_g2 处停下等这份文件"
    ],
    owner: "modules/run · modules/experiment · research_agent/cli.py (protocol freeze)",
    command: (input, decision) => protocolFreezeCommand(input, decision.humanReason)
  },
  S5b: {
    id: "S5b",
    stage: "S5a → S6",
    eyebrow: "S5b · HUMAN GATE",
    title: "claim 签署：statement 与 human_reason 由人定稿",
    lede:
      "RunCapsule 与 EA 已封存，claim draft 是 draft_needs_human。只有人能把它变成 supported 的 ClaimRecord——本对话框沿用人签面板（复制 CLI 命令 / 导入已签产物 / 静态 DEMO 预览）。",
    contract: [
      "claim 只能绑定已存在的 EA，且 scope 必须严格匹配（modules/run SPEC）",
      "结构化断言在签署前从 metrics 产物重算，重算不一致直接拒绝签署",
      "human_reason 必填且非空；空理由的签署请求被 CLI 拒绝",
      "委托签（[delegated:autopilot]）不是人签：submission=false，不能外推（design/136）"
    ],
    owner: "modules/run · research_agent/cli.py (run claim)",
    command: (input, decision) => claimSignCommand(input, decision.humanReason)
  },
  G5: {
    id: "G5",
    stage: "S13–S16 → 导出",
    eyebrow: "G5 · HUMAN GATE",
    title: "闭合签署：机制闭环 ≠ 人签发生",
    lede:
      "closure 检查全部通过后报告 ready，但导出与署名仍要等人在本地 CLI 签署 closure-signature。盘上若有一份 [delegated:autopilot] 的 signature.json，它不是人签，G5 在治理语义上仍是 needs_human。",
    contract: [
      "closure 逐项检查 claim / EA / 签名 / 沿袭一致性，任一不一致即 blocked（modules/closure）",
      "obligations 是 append-only：未完成的义务不会被静默勾掉",
      "lineage 变更传播：上游数据/代码变更把下游产物标 stale 并暂停导出（modules/lineage）",
      "签名只在本地 CLI 产生；网页不代签、不解锁导出"
    ],
    owner: "modules/closure · modules/lineage · research_agent/cli.py (closure sign)",
    command: (input, decision) => closureSignCommand(input, decision.humanReason)
  }
};

export const GATE_ORDER: HumanGateId[] = ["G1", "G2", "S5b", "G5"];

/** Which gate a transcript gate card refers to. Q0 cards route to S5b (the
 * claim gate) — Q0 is the same panel in the existing ClaimGateDialog. Case
 * insensitive on purpose: "S5b" must not become "S5B" and miss the table. */
export function gateIdForCard(cardGate: string): HumanGateId | null {
  const id = cardGate.trim();
  if (id.toUpperCase() === "Q0") return "S5b";
  const hit = GATE_ORDER.find((gate) => gate.toLowerCase() === id.toLowerCase());
  return hit ?? null;
}

/** Stage → owning backend module one-liner, for the flow panel's contract lines.
 * Transcribed from AGENTS.md §5 边界表 and modules/README.md; keeps module ids
 * verbatim so a viewer can jump to the SPEC. */
export const STAGE_MODULE_CONTRACTS: Record<string, { module: string; invariants: string[] }> = {
  S1: {
    module: "modules/literature",
    invariants: [
      "摘要-only 只作 SourceHit 线索，不生成 span、不进入 claim",
      "fixture 语料必须显式标 fixture:true，输出带 fixture_mode 警告",
      "coverage gap 单独登记；六面向覆盖（core/survey/method/evaluation/limitation/recent）不足时显式提示补检索"
    ]
  },
  "S2–S3": {
    module: "modules/idea + innovation_review",
    invariants: [
      "候选不是 claim；G1 人工收敛前不进入设计",
      "词法预审三问：grounding / falsifiability / testability",
      "先查领域与方法两条文献线；Tier-1 激进与 Tier-2 稳妥并排给出"
    ]
  },
  S4: {
    module: "modules/experiment + ccfa-audit",
    invariants: [
      "协议先于数据：设计审计 blockers=0 才具备 G2 冻结条件",
      "codegen 只生成不自跑；执行需人工 approve + --allow-execute",
      "数据指标只从用户表格与 spec 重算，不使用模型编造值"
    ]
  },
  S5a: {
    module: "modules/run",
    invariants: [
      "无冻结协议不执行：protocol_sha256 与 ProtocolCard 绑定",
      "RunCapsule / EA 不可变；EA 用 sha256 钉住结果文件",
      "失败产出 status=failed，绝不零填充指标；per-seed 数值可复算",
      "run contract：缺配对基线时 min_delta 标 not_verifiable，不印 delta"
    ]
  },
  S5b: {
    module: "modules/run (claim) + judge",
    invariants: [
      "claim 只绑定已有 EA 且 scope 严格匹配；断言先重算后签署",
      "human_reason 必填；委托签不是人签",
      "未签 claim → 写作包 allowed_result_numbers 为空，Results 出现数字即阻断"
    ]
  },
  S6: {
    module: "modules/figure (figure_workflow)",
    invariants: [
      "图绑定 EA；manifest 记录 scene/provenance",
      "上游数据变更 → 受影响图标 stale 并暂停导出"
    ]
  },
  "S8–S12": {
    module: "modules/writing (writing_pack/writing_audit)",
    invariants: [
      "写作包是只读投影：不创建 Claim/EA/Gate/Signature/Closure",
      "只允许引用登记过的 reference_id；不发明标题与 DOI",
      "槽位只接受已签 claim / EA / closure 引用；Limitations 必须作者亲写",
      "submission_ready 恒为 false，最高 ready_for_human_review"
    ]
  },
  "S13–S16": {
    module: "modules/closure + lineage",
    invariants: [
      "closure 检查全过才 ready；obligations append-only",
      "lineage 17 节点哈希清单；变更传播标 stale 并阻断导出",
      "签名只在本地 CLI；导出清单与 closure checks 哈希绑定"
    ]
  },
  META: {
    module: "modules/rsi (lease-gated runtime)",
    invariants: [
      "候选默认 disabled；lease 由人授予后才生效",
      "只改注册过的策略参数（检索预算 / S5 seeds），不训练权重、不改 claim 层",
      "dry-run / public-hidden / regression 证据齐全才可准入；新版不追认旧结果"
    ]
  }
};
