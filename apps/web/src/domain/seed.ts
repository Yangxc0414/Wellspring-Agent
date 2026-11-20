import { AUTO_STAGE_CATALOG, DEFAULT_PREFERENCES, builtinSkills, clampModel, defaultModelSettings, modelSettingsForProfile, seedGithubPlugin } from "./catalog";
import type {
  MemoryEntry,
  AccessMode,
  AutoStage,
  Card,
  ContextAttachment,
  EvaluationState,
  EvidenceItem,
  EvolutionCandidate,
  Gate,
  Message,
  Mode,
  PersistedWorkspace,
  ResearchTask,
  TokenUsage,
  Workspace
} from "./types";
import { formatBytes, isoDate, isoDateOffset, isoNow, uid } from "./utils";

export const WORKSPACES: Workspace[] = [
  { id: "materials", name: "材料实验室", note: "钙钛矿 / 稳定性" },
  { id: "agent", name: "Agent 研究", note: "自改进 / archive" },
  { id: "thesis", name: "毕业设计", note: "写作 / 证据" }
];

/**
 * What each seeded session is *for* in a demo. Shown in the sidebar instead of
 * a meaningless relative date, so a viewer can tell the whole-chain walkthrough
 * from a real study replay and from a lightweight example at a glance.
 * Entries with a `hint` also explain, on hover, why the session is in the demo.
 */
export const DEMO_LABELS: Record<
  string,
  { label: string; hint: string; tone: "demo" | "pending" | "example" }
> = {
  "full-chain-demo": {
    label: "全流程演示",
    tone: "demo",
    hint: "教学演示：从文献检索一路走到结论签署与自改进，九个阶段逐条可展开；点「模拟人签」演示待签→已签。状态只在页面内存，刷新即回待签。"
  },
  "ese-ms-20261118-03": {
    label: "真实研究·待签",
    tone: "pending",
    hint: "真实 ESE 研究回放（ESE-MS-20261118-03）：3 个仓库 / 5132 提交，缺陷修复比例 +0.046，分层后 click 方向反转；claim / closure / signature 仍待人签。"
  },
  perovskite: {
    label: "示例·调研",
    tone: "example",
    hint: "静态示例：span-only 文献检索与 gap→候选假设，停在 G1 人工收敛前。"
  },
  archives: {
    label: "示例·调研",
    tone: "example",
    hint: "静态示例：自改进 agent 的 archive 使用，只有检索计划，未进入执行。"
  },
  "evidence-writing": {
    label: "示例·写作",
    tone: "example",
    hint: "静态示例：证据驱动写作槽位；没有已签 claim 前，结果与摘要保持 locked。"
  },
  "proposal-review": {
    label: "示例·命题",
    tone: "example",
    hint: "静态示例：毕设命题设计与反思，用于说明证据边界与验证顺序。"
  }
};

function system(text: string, at = "08:31:40"): Message {
  return { id: uid("msg"), role: "system", at, text };
}

function agent(text: string, card?: Card, at = "08:32:02"): Message {
  return { id: uid("msg"), role: "agent", at, text, card };
}

function user(text: string, at = "08:32:10"): Message {
  return { id: uid("msg"), role: "user", at, text };
}

/** Tag a message with its flow stage so a flow node can jump to it in the thread. */
function withStage(message: Message, stage: string): Message {
  return { ...message, stage };
}

function freshStages(): AutoStage[] {
  return AUTO_STAGE_CATALOG.map((stage) => ({ ...stage, status: "pending" }));
}

type UsageInput = Record<string, [prompt: number, completion: number, requests: number]>;

function seedUsage(days: Array<{ offset: number; models: UsageInput }>): Pick<ResearchTask, "usage" | "usageDays"> {
  const usageDays: Record<string, Record<string, TokenUsage>> = {};
  const usage: Record<string, TokenUsage> = {};
  for (const day of days) {
    const key = isoDateOffset(day.offset);
    const bucket = usageDays[key] ?? {};
    for (const [profileId, [prompt, completion, requests]] of Object.entries(day.models)) {
      const total = usage[profileId] ?? { prompt: 0, completion: 0, requests: 0 };
      usage[profileId] = {
        prompt: total.prompt + prompt,
        completion: total.completion + completion,
        requests: total.requests + requests
      };
      const dayUsage = bucket[profileId] ?? { prompt: 0, completion: 0, requests: 0 };
      bucket[profileId] = {
        prompt: dayUsage.prompt + prompt,
        completion: dayUsage.completion + completion,
        requests: dayUsage.requests + requests
      };
    }
    usageDays[key] = bucket;
  }
  return { usage, usageDays };
}

function defaultGates(): Gate[] {
  return [
    { id: "Q0", status: "pending", reason: "coverage / claim admission 未运行" },
    { id: "G1", status: "needs_human", reason: "候选假设需要人工收敛" },
    { id: "G2", status: "not_started", reason: "设计 + 协议尚未冻结" },
    { id: "S5", status: "not_started", reason: "尚未执行 run" },
    { id: "G5", status: "blocked", reason: "没有 EA / Claim / Closure" }
  ];
}

export function emptyEvaluation(): EvaluationState {
  return {
    baselinePaper: null,
    baselineReproduced: null,
    hiddenAccessCount: 0,
    validationSelections: 0,
    evalRuleHash: "—",
    audit: "pending",
    trainCost: null,
    inferenceCost: null,
    interventions: []
  };
}

function demoEvaluation(): EvaluationState {
  return {
    baselinePaper: 300,
    baselineReproduced: 286,
    hiddenAccessCount: 0,
    validationSelections: 6,
    evalRuleHash: "sha256:7c41e2",
    audit: "pending",
    trainCost: 2.4,
    inferenceCost: 1,
    interventions: [
      {
        id: "INT-01",
        label: "baseline reproduction",
        kind: "engineering",
        note: "固定训练/验证/测试划分；以复现基线 286h 作为比较起点",
        at: "2026-10-24T08:04:00"
      },
      {
        id: "INT-02",
        label: "hydration-aware split",
        kind: "domain",
        note: "按湿热循环批次分组，避免同批样品跨训练/验证泄漏",
        at: "2026-10-24T08:12:00"
      },
      {
        id: "INT-03",
        label: "passivation mechanism",
        kind: "domain",
        note: "双分子钝化层 / 界面缺陷密度作为机制假设，而非仅调参",
        at: "2026-10-24T08:20:00"
      },
      {
        id: "INT-04",
        label: "seed budget",
        kind: "engineering",
        note: "3 seeds；没有扩大集成，控制训练与推理成本",
        at: "2026-10-24T08:28:00"
      }
    ]
  };
}

export function planCard(queries: string[], scope: string, budget: string, note: string): Card {
  return { type: "plan", queries, scope, budget, note };
}

function sourcesCard(): Card {
  return {
    type: "sources",
    items: [
      { title: "Huang et al. · 2024 · Joule", meta: "full text · 6 spans", status: "ok" },
      { title: "Wang et al. · 2023 · ACS Energy Lett.", meta: "full text · 4 spans", status: "ok" },
      { title: "Chen et al. · 2025 · Adv. Mater.", meta: "full text · 2 spans", status: "ok" },
      { title: "Liu et al. · 2022 · Sol. RRL", meta: "abstract only · 0 span", status: "warn" }
    ],
    note: "12 个可定位 span；1 条摘要-only 来源只能作为线索。"
  };
}

function ideaCard(): Card {
  return {
    type: "idea",
    gap: "湿热循环后的定量对照缺失：现有来源只报告初始 PCE 与 T80，没有钝化层/未钝化层的配对比较。",
    candidates: [
      { id: "H1", text: "双分子钝化层降低界面缺陷密度，从而延长湿热条件下的 T80。" },
      { id: "H2", text: "钝化层的疏水性（而非缺陷密度）是湿热稳定性的主因。" }
    ],
    note: "候选不是 claim；需要 G1 人工收敛，再进入 S4 设计。"
  };
}

function protocolCard(): Card {
  return {
    type: "protocol",
    hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
    baseline: "未钝化对照",
    metric: "T80（小时）· 初始 PCE",
    seeds: 3,
    controls: ["未钝化", "单分子钝化"],
    status: "G2 needs_human"
  };
}

export function writingCard(options: {
  claimSigned?: boolean;
  protocolFrozen?: boolean;
} = {}): Card {
  const { claimSigned = false, protocolFrozen = false } = options;
  return {
    type: "writing",
    slots: [
      {
        id: "S8.methods",
        label: "Methods · 协议与 seeds",
        status: protocolFrozen ? "bound" : "pending",
        note: protocolFrozen ? "绑定已冻结协议；主指标不可改写" : "需要 G2 协议冻结"
      },
      {
        id: "S9.results",
        label: "Results · 主结果",
        status: claimSigned ? "bound" : "locked",
        note: claimSigned ? "绑定已签 claim 与 EA" : "没有已签 claim；数值不得先填"
      },
      {
        id: "S10.figure",
        label: "Figure · 主图",
        status: claimSigned ? "bound" : "locked",
        note: claimSigned ? "绑定 EA-7c41 / figure manifest" : "先有 EA 才能绑定图"
      },
      {
        id: "S11.abstract",
        label: "Abstract · 结论",
        status: claimSigned ? "bound" : "locked",
        note: claimSigned ? "只陈述已签 claim 的范围" : "claim 未签，摘要保持 locked"
      },
      {
        id: "S12.related",
        label: "Related · 引用",
        status: "pending",
        note: "2 条 citation.related 待补；closure 仍会拦住导出"
      },
      {
        id: "S12.limitations",
        label: "Limitations · 作者声明",
        status: "pending",
        note: "必须由作者写，不能由 agent 代填"
      }
    ],
    note: "槽位只接受已签 claim / EA / closure 引用；正文不会先于证据填数。"
  };
}

export function makeCandidate(): EvolutionCandidate {
  return {
    id: "CAND-RSI-014",
    target: "literature.query_planner",
    patch: "broad retrieval 前追加 review 子查询；预算从 6 调为 3。",
    rationale: "transfer 任务 coverage 偏薄，gap 数连续两轮为 0。",
    predicted: "多 1 篇全文、多 1 个可定位 span；不改变 claim 边界。",
    evidence: "public 3/3 · hidden 2/2 · regression 0 · near-OOD 待复核",
    lease: "未授予",
    status: "pending"
  };
}

const PROTOCOL = {
  hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
  baseline: "未钝化对照",
  metric: "T80（小时）· 初始 PCE",
  seeds: 3,
  controls: ["未钝化", "单分子钝化"]
};

const EVIDENCE: EvidenceItem[] = [
  {
    id: "GAP-001",
    kind: "gap",
    status: "open",
    text: "湿热循环后的配对定量对照缺失。",
    scope: "S1/perovskite",
    refs: ["SPAN-021"],
    note: "4 篇来源中只有 2 篇报告 T80。"
  },
  {
    id: "CAND-H1",
    kind: "hypothesis",
    status: "candidate",
    text: "双分子钝化层降低界面缺陷密度 → 延长 T80。",
    scope: "S2/perovskite",
    refs: ["SPAN-014", "SPAN-021"]
  },
  {
    id: "CAND-H2",
    kind: "hypothesis",
    status: "candidate",
    text: "疏水性而非缺陷密度是湿热稳定性的主因。",
    scope: "S2/perovskite",
    refs: ["SPAN-009"]
  }
];

// 一个默认就已归档的任务：让「归档管理」在首次打开时就展示完整的
// 归档 → 恢复/下载 流程，而不是三个 0 计数（与侧栏 6 个活跃任务对齐）。
export function seedArchivedTask(): ResearchTask {
  return {
    ...seedThesisTask(
      "materials-archive-demo",
      "湿热稳定性对照组设计",
      "为钙钛矿任务设计湿热稳定性对照组、样本量与停止规则。",
      "2026-10-21T10:30:00"
    ),
    workspaceId: "materials",
    domain: "实验设计",
    createdAt: "2026-10-19",
    updatedAt: "2026-10-21T10:30:00",
    stage: 4,
    completedStages: [0, 1, 2, 3]
  };
}

function seedPerovskite(): ResearchTask {
  return {
    id: "perovskite",
    name: "钙钛矿界面钝化",
    goal: "验证界面钝化对湿热稳定性的影响，并留下可追溯的证据链。",
    domain: "材料科学",
    mode: "research",
    access: "ask",
    status: "active",
    workspaceId: "materials",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T08:32:00",
    stage: 1,
    completedStages: [0],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([
      { offset: -28, models: { "gpt-5": [3200, 480, 1] } },
      { offset: -21, models: { "gpt-5": [4100, 680, 1] } },
      { offset: -18, models: { "claude-sonnet": [4200, 540, 1] } },
      { offset: -14, models: { "gpt-5": [5300, 820, 1] } },
      { offset: -10, models: { "qwen-local": [2100, 460, 1] } },
      { offset: -7, models: { "gpt-5": [5000, 900, 1] } },
      { offset: -4, models: { "claude-sonnet": [5400, 700, 1] } },
      { offset: 0, models: { "gpt-5": [7200, 1380, 1] } }
    ]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 12, total: 40 },
    gates: [
      { id: "Q0", status: "pass", reason: "12 spans / 2 gaps recorded" },
      { id: "G1", status: "needs_human", reason: "2 个候选假设等待收敛" },
      { id: "G2", status: "not_started", reason: "尚未冻结设计" },
      { id: "S5", status: "not_started", reason: "尚未执行 run" },
      { id: "G5", status: "blocked", reason: "没有 Claim / Closure" }
    ],
    coverage: { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 },
    evidence: EVIDENCE.map((item) => ({ ...item, refs: [...item.refs] })),
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: demoEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages().map((stage, index) => (index === 0 ? { ...stage, status: "done" } : stage)),
    messages: [
      system("STATIC WORKSPACE · 示例状态；不调用模型、不执行真实实验、不产生真实 claim。"),
      agent("项目已接入。我会先把问题拆成可检索的子问题，再决定是否值得进入实验。", planCard(
        ["界面钝化 湿热稳定性", "perovskite passivation damp heat", "passivation layer defect density"],
        "2020–2026 · 中英双语 · 只读公开摘要/全文",
        "6 sources · span-only",
        "摘要-only 只作 SourceHit；没有全文不生成 span，也不进入 claim。"
      )),
      user("先调研界面钝化与长期稳定性的证据，重点看湿热稳定性。"),
      agent(
        "**检索完成** · 4 sources\n\n- 3 条全文，1 条摘要-only\n- 12 个可定位 span\n- 2 个 coverage gap\n\n> 摘要-only 只作线索，不进入 claim。",
        sourcesCard()
      ),
      agent(
        "### 关键 gap\n湿热循环后的配对定量对照缺失。\n\n- 足以支撑一个可否证的假设\n- 还不够支撑 claim\n\n> 候选不是 claim；需要 G1 人工收敛。",
        ideaCard()
      )
    ]
  };
}

function seedArchives(): ResearchTask {
  return {
    id: "archives",
    name: "自改进 agent 的 archive 使用",
    goal: "理解自改进 coding agent 如何选择、保留与复用 archive 中的历史版本。",
    domain: "机器学习",
    mode: "research",
    access: "ask",
    status: "active",
    workspaceId: "agent",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T08:20:00",
    stage: 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([
      { offset: -5, models: { "gpt-5": [3700, 560, 1] } },
      { offset: -1, models: { "gpt-5": [3700, 560, 1] } }
    ]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 4, total: 30 },
    gates: defaultGates(),
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages(),
    messages: [
      system("STATIC WORKSPACE · 示例状态；不调用模型、不执行真实实验。"),
      user("自改进 agent 到底怎么使用 archive？我想先做一轮文献调研。"),
      agent(
        "我会先区分三类 archive，再判断哪些机制有可核验证据：\n\n- 代码版本 archive\n- 轨迹 / 反思 archive\n- 评测结果 archive\n\n> 先形成 span，再谈复用机制。",
        planCard(
          ["self-improving agent archive", "Darwin Gödel Machine stepping stones", "agent memory reuse lineage"],
          "2024–2026 · arXiv / 会议",
          "6 sources · span-only",
          "先宽后深；摘要-only 来源不生成 span。"
        )
      )
    ]
  };
}

function seedThesisTask(
  id: string,
  name: string,
  goal: string,
  updatedAt: string,
  mode: Mode = "research"
): ResearchTask {
  return {
    id,
    name,
    goal,
    domain: "写作 / 证据",
    mode,
    access: "ask",
    status: "active",
    workspaceId: "thesis",
    createdAt: "2026-10-23",
    updatedAt,
    stage: mode === "writing" ? 6 : 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 0, total: 30 },
    gates: defaultGates(),
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages(),
    messages: [
      system("STATIC WORKSPACE · 示例任务；不调用模型、不执行真实实验。"),
      agent(
        mode === "writing"
          ? `任务已创建：${name}。写作从槽位开始；没有已签 claim 之前，结果与摘要槽位保持 locked。`
          : `任务已创建：${name}。这是毕业设计工作区里的静态示例；可以从调研开始，也可以直接设计实验。`
      ),
      mode === "writing"
        ? agent(
            "先把已签 claim、冻结协议与图 manifest 绑定到槽位；正文不得先于证据填数。",
            writingCard()
          )
        : agent(
            "先明确证据边界，再决定是否进入实验。",
            planCard(
              ["证据闭合 writing agent", "claim span provenance", "中文核刊 结构"],
              "2022–2026 · 中文/英文",
              "4 sources · span-only",
              "摘要-only 只作线索；没有全文不生成 span。"
            )
          )
    ]
  };
}

export function seedEseStudy(): ResearchTask {
  return {
    id: "ese-ms-20261118-03",
    name: "ESE：缺陷修复更常触碰测试？",
    goal: "在 click / requests / httpx 上检验缺陷修复提交是否更常触碰测试，并检查差异能否经分层后成立。",
    domain: "经验软件工程",
    mode: "research",
    access: "ask",
    status: "blocked",
    workspaceId: "thesis",
    createdAt: "2026-11-18",
    updatedAt: "2026-11-18T22:50:00",
    stage: 5,
    completedStages: [0, 1, 2, 3, 4],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 3, total: 30 },
    gates: [
      { id: "Q0", status: "pass", reason: "3 个仓库 HEAD 已固定；协议先于数据冻结" },
      { id: "G1", status: "needs_human", reason: "四条 RQ 已收敛为一条可检验断言" },
      { id: "G2", status: "needs_human", reason: "分层与置换计划已冻结，等待人工确认" },
      { id: "S5", status: "pass", reason: "run-capsule completed · EA immutable" },
      { id: "G5", status: "blocked", reason: "claim / closure / signature 尚未人签" }
    ],
    coverage: { sources: 3, spans: 0, gaps: 1, abstractOnly: 0 },
    evidence: [],
    protocol: null,
    protocolFrozen: true,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages().map((stage, index) => (index <= 4 ? { ...stage, status: "done" } : stage)),
    messages: [
      system(
        "STATIC REPLAY · 回放一次真实 ESE 研究（ESE-MS-20261118-03）。数字来自 runtime_data 产物；claim / closure / signature 仍未人签。",
        "22:41:02"
      ),
      user(
        "研究一个问题：Python 项目里，缺陷修复提交是不是比功能提交更常触碰测试？这个差异经项目分层后还成立吗？",
        "22:41:10"
      ),
      agent(
        "先把它拆成四个可检验的子问题，并在跑数之前把协议冻结。",
        {
          type: "plan",
          queries: [
            "RQ1 触碰 .py 的提交里，有多大比例同时触碰测试？",
            "RQ2 缺陷修复提交与其它提交的比例是否不同？",
            "RQ3 按每仓库中位日期切分，早晚是否不同？",
            "RQ4 按项目 / 提交规模 / 生产代码共变分层后，差异是否仍在？"
          ],
          scope: "click / requests / httpx · 本地 clone · path+message 启发式标签",
          budget: "3 repos · 5132 commits · 置换 1000 次（固定种子）",
          note: "协议先于数据冻结；标签是启发式，不是人工标注。"
        },
        "22:41:26"
      ),
      agent(
        "执行完成：3 个仓库、5132 个提交。",
        {
          type: "sources",
          items: [
            { title: "click", meta: "1328 commits · 0.4428 [0.4163, 0.4696]", status: "ok" },
            { title: "requests", meta: "2824 commits · 0.2691 [0.2531, 0.2858]", status: "ok" },
            { title: "httpx", meta: "980 commits · 0.5878 [0.5567, 0.6182]", status: "ok" }
          ],
          note: "三个仓库都是成熟开源项目；这是便利样本，不是概率抽样。"
        },
        "22:43:05"
      ),
      agent(
        "**合并读数**\n\n- 触碰测试：1924 / 5132 = **0.3749**，95% CI [0.3618, 0.3882]\n- 缺陷修复：352 / 851 = 0.4136；其它：1572 / 4281 = 0.3672\n- 差 **+0.0464**，置换检验双侧 p = **0.015**\n- 时间切分：早期 0.3091 → 晚期 0.4410，差 +0.1319（p = 0.001）\n\n> 合并样本上差异为正。是否每个项目都成立，要分层才知道。",
        undefined,
        "22:43:20"
      ),
      user("分层之后呢？我担心是某个项目把总体拉高了。", "22:44:01"),
      agent(
        "**分层结果：差异不是每个项目都成立**\n\n- click：0.4375 vs 0.4442 → **-0.0067（方向反转）**\n- httpx：0.6264 vs 0.5838 → +0.0426\n- requests：0.3581 vs 0.2513 → +0.1068\n- 提交规模 >5：0.5909 vs 0.6700 → -0.0791\n\n所以能写的只有：“在三仓库合并样本上高 0.046，但 click 内方向反转，因此不适用于单项目。” 不能写“缺陷修复提交更常改测试”。",
        undefined,
        "22:44:18"
      ),
      user("这条现在能签吗？", "22:45:02"),
      agent(
        "还不能。证据链五段只完成了前两段：\n\n- RunCapsule ✓ completed（metric=test_cochange_rate，seeds=[42]）\n- EA ✓ immutable（EA-65d32e114229，source=ese-exec）\n- Claim · 待人工\n- Closure · 待执行\n- Signature · 待人工\n\n后三步都是人签步骤，agent 不代签。",
        {
          type: "gate",
          gate: "G5",
          title: "结论待人工签署",
          reason: "capsule 与 EA 已完成；claim / closure / signature 需要人执行 CLI",
          status: "blocked"
        },
        "22:45:20"
      ),
      system(
        "等待人工：run claim --evidence-source ese-exec → closure ese-check → closure ese-sign。签完后页面的证据链会自动变为 SIGNED。",
        "22:45:30"
      )
    ]
  };
}

export function seedFullChainDemo(): ResearchTask {
  return {
    id: "full-chain-demo",
    name: "完整闭环：从检索到自改进",
    goal: "用一个材料科学案例完整演示 S1→META 闭环：文献检索、假设收敛、设计冻结、执行、判定、写作、闭包、人签与经验复用。",
    domain: "材料科学",
    mode: "research",
    access: "ask",
    status: "blocked",
    workspaceId: "thesis",
    createdAt: "2026-10-24",
    updatedAt: "2026-10-24T10:09:42",
    stage: 8,
    completedStages: [0, 1, 2, 3, 4, 5, 6, 7],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: defaultModelSettings(),
    ...seedUsage([
      { offset: -6, models: { "gpt-5": [3800, 520, 1] } },
      { offset: -3, models: { "claude-sonnet": [4100, 640, 1] } },
      { offset: 0, models: { "gpt-5": [5600, 980, 1] } }
    ]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 6, total: 40 },
    gates: [
      { id: "Q0", status: "pass", reason: "12 spans / 2 gaps recorded" },
      { id: "G1", status: "pass", reason: "H1 收敛；H2 作为竞争假设保留" },
      { id: "G2", status: "pass", reason: "协议已冻结；3 seeds；主指标不可改写" },
      { id: "S5", status: "pass", reason: "RUN-014 · EA-7c41 sealed" },
      { id: "G5", status: "blocked", reason: "claim / closure / signature 待人签" }
    ],
    coverage: { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 },
    evidence: EVIDENCE.map((item) => ({ ...item, refs: [...item.refs] })),
    protocol: { ...PROTOCOL },
    protocolFrozen: true,
    run: {
      id: "RUN-014",
      dataset: "perovskite-passivation",
      seeds: 3,
      metric: "R²（演示代理指标）",
      mean: 0.164,
      baseline: -0.048,
      ea: "EA-7c41",
      status: "completed"
    },
    evaluation: demoEvaluation(),
    evolution: {
      status: "proposed",
      candidate: makeCandidate(),
      lease: "未授予",
      history: [
        { at: "2026-10-24T10:25:00", text: "反思：transfer 任务 coverage 偏薄，gap 数连续两轮为 0。" },
        { at: "2026-10-24T10:26:00", text: "提案：检索前追加 review 子查询；不训练权重，lease 待人授予。" }
      ]
    },
    auto: { running: false, paused: false, index: 8, cycle: 0, gate: "claim", gateApproved: false },
    autoStages: freshStages().map((stage, index) =>
      index <= 7 ? { ...stage, status: "done" } : index === 8 ? { ...stage, status: "waiting" } : stage
    ),
    messages: [
      system(
        "STATIC REPLAY · 教学演示：完整走一遍从文献检索到结论签署与自改进的闭环。数值为演示案例，不调用模型、不执行真实实验、不产生真实签名；真实结果须经 CLI 人签。",
        "10:00:00"
      ),
      user("从一份文献开始，完整演示一遍：系统怎么把问题变成可追溯的结论，再怎么把经验留下来。", "10:00:12"),
      withStage(agent(
        "第一步不是找答案，是把问题拆成可检索的子问题，并先写清楚「什么算证据」。摘要-only 只作线索。",
        planCard(
          ["perovskite interface passivation damp heat", "passivation layer defect density T80", "双分子钝化 湿热稳定性 配对对照"],
          "2020–2026 · 中英双语 · 全文优先，摘要仅作 SourceHit",
          "4 sources · 12 spans · span-only",
          "没有全文不生成 span；coverage gap 单独登记。"
        ),
        "10:00:40"
      ), "S1"),
      user("先查界面钝化与湿热稳定性的证据，重点看有没有配对定量对照。", "10:01:05"),
      withStage(agent(
        "**S1 检索完成** · 4 sources / 12 spans / 2 gaps\n\n- 3 条全文，1 条摘要-only（只登记为线索）\n- 湿热配对对照仍是空白\n\n> 检索产物是 SourceHit + span，不是结论。",
        sourcesCard(),
        "10:02:18"
      ), "S1"),
      withStage(agent(
        "### S2–S3：从 gap 到候选假设\n配对定量对照缺失，足以支撑一个可否证的假设，但还不够支撑 claim。\n\n> 候选不是 claim；G1 必须人工收敛。",
        ideaCard(),
        "10:02:44"
      ), "S2–S3"),
      user("G1：收敛到 H1（钝化层降低缺陷密度 → 延长 T80），H2 作为竞争假设保留。", "10:03:20"),
      withStage(agent(
        "**G1 已收敛** · H1 主假设 / H2 竞争假设。\n\n下一步冻结设计。这一步必须人来确认——预注册一旦定稿，主指标就不能改。",
        {
          type: "gate",
          gate: "G1",
          title: "候选假设已由人工收敛",
          reason: "H1 主假设；H2 竞争假设；候选不写入 claim",
          status: "pass"
        },
        "10:03:38"
      ), "S2–S3"),
      withStage(agent(
        "### S4：设计冻结（预注册）\n协议先于数据：假设、基线、主指标、seeds、对照组都在这里定死。执行器之后只做提取与统计。",
        {
          type: "protocol",
          hypothesis: PROTOCOL.hypothesis,
          baseline: PROTOCOL.baseline,
          metric: PROTOCOL.metric,
          seeds: PROTOCOL.seeds,
          controls: PROTOCOL.controls,
          status: "G2 needs_human（本演示已确认）"
        },
        "10:04:02"
      ), "S4"),
      user("G2：确认协议，按 3 seeds 跑。", "10:04:30"),
      withStage(agent(
        "**G2 已冻结** · 协议哈希绑定；执行器无权改主指标或协议。",
        {
          type: "gate",
          gate: "G2",
          title: "协议已冻结",
          reason: "预注册完成；3 seeds；主指标 T80 不可改写",
          status: "pass"
        },
        "10:04:48"
      ), "S4"),
      withStage(agent(
        "**S5a 执行完成** · RUN-014 / 3 seeds。\n\nR² 0.164（对照 −0.048）。这是演示代理指标；协议主指标 T80 需真实实验。数据与代码版本写入 capsule。",
        {
          type: "run",
          id: "RUN-014",
          dataset: "perovskite-passivation",
          seeds: 3,
          metric: "R²（演示代理指标）",
          mean: 0.164,
          baseline: -0.048,
          status: "completed",
          ea: "EA-7c41"
        },
        "10:05:55"
      ), "S5a"),
      withStage(agent(
        "### S5b：证据判定\nverdict 是两态加一道 underpowered 守卫：区间跨零、样本不足时明确标注「too few to interpret a sign」，不把「没测出差异」写成「无效」。负结果如实保留。",
        {
          type: "gate",
          gate: "S5b",
          title: "判定已产出，断言待人签",
          reason: "EA-7c41 sealed；verdict 可复核；claim 需人工 statement + human_reason",
          status: "needs_human"
        },
        "10:06:20"
      ), "S5b"),
      withStage(agent(
        "**S6 结果图**：SVG 主图与 manifest 绑定 EA；上游数据变更后，受影响的图会被标 stale 并暂停导出，不会拿旧图配新结论。",
        undefined,
        "10:06:35"
      ), "S6"),
      user("写作阶段怎么保证不先填数？", "10:06:50"),
      withStage(agent(
        "**S8–S12 写作槽位**：Results / Figure / Abstract 全部 locked。\n\n槽位只接受已签 claim / EA / closure 引用；正文不会先于证据填数。",
        writingCard({ protocolFrozen: true, claimSigned: false }),
        "10:07:12"
      ), "S8–S12"),
      user("现在能签了吗？", "10:07:40"),
      withStage(agent(
        "还不能由我签。证据链五段：\n\n- 来源 ✓　片段 ✓　运行记录 ✓　证据制品 ✓\n- 断言 · 待人工\n\nclosure 只核对四件产物一致性；签名只能在本地 CLI 产生，网页不代签。",
        {
          type: "gate",
          gate: "G5",
          title: "结论待人签",
          reason: "claim / closure / signature 由人在本地 CLI 执行",
          status: "blocked"
        },
        "10:08:00"
      ), "S13–S16"),
      system(
        "待人工：run claim → closure check → closure sign。签完 Results 槽位解锁、徽章变 SIGNED；未签时不宣称已闭合。",
        "10:08:12"
      ),
      user("这一轮有什么经验能留下给下次用？", "10:08:40"),
      withStage(agent(
        "**META 自改进提案**：把「检索前追加 review 子查询」写进方法插件，不训练模型权重。\n\nlease 未授予前不生效；采纳决定由人做。",
        { type: "evolution", candidate: makeCandidate() },
        "10:09:05"
      ), "META"),
      agent(
        "### 边界与反思\n- 版本迭代不改骨架（S1→META 固定）\n- 单题参数不上长为通用默认\n- 新版本不追认旧结果\n\n↑ 这三条保证「自改进」不会把一次性观察写成永远适用的规则。",
        undefined,
        "10:09:30"
      ),
      system("完整闭环演示结束。签名与经验采纳均由人在 CLI 完成，agent 只产出可复核的候选与证据。", "10:09:42")
    ]
  };
}

export const SEED_MEMORY_ENTRIES: MemoryEntry[] = [
      {
        id: "mem-seed-retrieval",
        text: "钙钛矿任务检索计划固定 2020–2026 中英双语，全文优先；摘要-only 只作线索。",
        kind: "decision",
        scope: "钙钛矿界面钝化",
        source: "任务固定",
        createdAt: "2026-10-24T09:30:00"
      },
      {
        id: "mem-seed-ese",
        text: "ESE 分层数据显示 click 方向反转；引用该结论必须带分层口径。",
        kind: "note",
        scope: "ESE 研究",
        source: "runtime 同步",
        createdAt: "2026-11-05T14:10:00",
        syncedAt: "2026-11-05T14:12:00"
      },
      {
        id: "mem-seed-writing",
        text: "写作槽位只接受已签 claim；未签前 Results 槽位保持 locked。",
        kind: "constraint",
        scope: "证据驱动科研写作系统",
        source: "任务固定",
        createdAt: "2026-10-23T17:00:00"
      }

];

export function createSeedWorkspace(): PersistedWorkspace {
  return {
    version: 1,
    selectedTaskId: "full-chain-demo",
    activeWorkspaceId: "thesis",
    preferences: { ...DEFAULT_PREFERENCES, shortcuts: { ...DEFAULT_PREFERENCES.shortcuts } },
    workspaces: WORKSPACES,
    plugins: [seedGithubPlugin()],
    skills: builtinSkills(),
    tasks: [
      seedFullChainDemo(),
      seedEseStudy(),
      seedPerovskite(),
      seedArchives(),
      seedThesisTask("evidence-writing", "证据驱动科研写作系统", "把 claim 与 span 的绑定做成可审计的写作工作流。", "2026-10-23T16:40:00", "writing"),
      seedThesisTask("proposal-review", "项目命题设计与反思", "收敛毕设命题、边界与验证顺序。", "2026-10-23T15:20:00"),
      seedArchivedTask()
    ],
    memory: SEED_MEMORY_ENTRIES.map((entry) => ({ ...entry })),
    archivedTaskIds: ["materials-archive-demo"]
  };
}

export function createTask(input: {
  name: string;
  goal: string;
  domain: string;
  mode: Mode;
  workspaceId: string;
  access?: AccessMode;
  profileId?: string;
  thinkingStop?: string | number | null;
}): ResearchTask {
  const mode = input.mode;
  const messages: Message[] = [
    system("STATIC WORKSPACE · 新任务；示例状态，不调用模型、不执行真实实验。"),
    agent(`任务已创建：${input.name}。我会先明确问题边界，再选择调研、实验或受治理全自动。`)
  ];
  if (mode === "research") {
    messages.push(
      agent(
        "先给你一个检索计划；确认后再进入 span 与 gap。",
        planCard(
          ["研究问题 关键词", "英文对应检索式", "review / survey 入口"],
          "近五年 · 中英双语 · 公开摘要/全文",
          "4 sources · span-only",
          "摘要-only 只作线索；没有全文不生成 span。"
        )
      )
    );
  } else if (mode === "experiment") {
    messages.push(
      agent(
        "本任务从实验设计开始：S1/S2 已标为 skipped，G1 仍未收敛；结果槽保持 pending，直到 EA 与人签 claim。",
        protocolCard()
      )
    );
  } else if (mode === "writing") {
    messages.push(
      agent(
        "写作从槽位开始：没有已签 claim，结果与摘要槽位保持 locked；可以先去补齐证据，或检查已有边界。",
        writingCard()
      )
    );
  } else {
    messages.push(
      agent("全自动会从 S1 跑到人工门。你可以随时暂停、单步或停止；claim 不会被自动签署。")
    );
  }

  return {
    id: uid("task"),
    name: input.name.trim(),
    goal: input.goal.trim(),
    domain: input.domain,
    mode,
    access: input.access ?? "ask",
    status: "active",
    workspaceId: input.workspaceId,
    createdAt: isoDate(),
    updatedAt: isoNow(),
    stage: mode === "experiment" ? 2 : mode === "writing" ? 6 : 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "incumbent · broad-first" },
    model: clampModel({
      ...modelSettingsForProfile(input.profileId ?? "glm-5.3-flash"),
      ...(input.thinkingStop !== undefined ? { thinkingStop: input.thinkingStop } : {})
    }),
    ...seedUsage([]),
    guidance: [],
    plugins: ["github"],
    toolCalls: [],
    budget: { used: 0, total: 30 },
    gates: mode === "experiment"
      ? [
          { id: "Q0", status: "pending", reason: "尚未运行检索" },
          { id: "G1", status: "needs_human", reason: "尚未收敛假设" },
          { id: "G2", status: "needs_human", reason: "协议等待人工冻结" },
          { id: "S5", status: "not_started", reason: "尚未执行 run" },
          { id: "G5", status: "blocked", reason: "没有 Claim / Closure" }
        ]
      : defaultGates(),
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    evidence: [],
    protocol: mode === "experiment" ? { ...PROTOCOL, controls: [...PROTOCOL.controls] } : null,
    protocolFrozen: false,
    run: null,
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: mode === "experiment"
      ? freshStages().map((stage, index) => (index < 2 ? { ...stage, status: "skipped" as const } : stage))
      : freshStages(),
    messages
  };
}

export function createConversationTask(input: {
  text: string;
  workspaceId: string;
  access: AccessMode;
  profileId?: string;
  thinkingStop?: string | number | null;
  attachments?: ContextAttachment[];
}): ResearchTask {
  const text = input.text.trim();
  const clean = text.replace(/[#*>`]/g, "").replace(/\s+/g, " ");
  const topic = clean.slice(0, 22) || "研究问题";
  const base = createTask({
    name: clean.slice(0, 26) || "新会话",
    goal: text.slice(0, 220),
    domain: "其他",
    mode: "research",
    workspaceId: input.workspaceId,
    access: input.access,
    profileId: input.profileId,
    thinkingStop: input.thinkingStop
  });
  const attachments = input.attachments ?? [];
  const contextNote = attachments.length
    ? system(
        "已附加上下文（仅元数据，不进入证据链）：" +
          attachments
            .map((item) =>
              `${item.kind === "folder" ? "文件夹" : "文件"} ${item.name}（${item.files} 个文件，${formatBytes(item.bytes)}${item.source === "workspace" ? "，工作区登记" : ""}）`
            )
            .join("；")
      )
    : null;
  return {
    ...base,
    messages: [
      system("STATIC WORKSPACE · 新会话；示例状态，不调用模型、不执行真实实验。"),
      user(text),
      ...(contextNote ? [contextNote] : []),
      agent(
        "已收到问题。先把它拆成可检索的子问题：\n\n- 明确研究对象与时间范围\n- 生成中英检索式\n- 先登记 span，再判断 gap\n\n> 摘要-only 不生成 span，也不进入 claim。",
        planCard(
          [topic, `${topic} review`, "英文对应检索式"],
          "近五年 · 中英双语 · 公开摘要/全文",
          "4 sources · span-only",
          "摘要-only 只作线索；没有全文不生成 span。"
        )
      )
    ]
  };
}
