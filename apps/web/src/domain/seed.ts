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
  LiteratureAnnotation,
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
  { label: string; short: string; hint: string; tone: "demo" | "pending" | "example" }
> = {
  "full-chain-demo": {
    label: "全流程演示",
    // Compact form for the sidebar row: a long status pill was stealing the
    // space the title needed, and this is the most important demo task.
    short: "演示·待签",
    tone: "demo",
    hint: "教学演示：从文献检索一路走到结论签署与自改进，九个阶段逐条可展开；点「模拟人签」演示待签→已签。状态只在页面内存，刷新即回待签。"
  },
  "ese-ms-20261118-03": {
    label: "真实研究·闭环回放",
    short: "闭环·待签",
    tone: "pending",
    hint: "真实 ESE 研究的完整闭环回放（ESE-MS-20261118-03，S1→META）：3 仓库 / 5132 提交，合并 +0.046 但 click 内方向反转；S6/S8–S12 如实呈现未产出与 locked；claim / closure / signature 仍待人签。"
  },
  "e2e-closed-loop": {
    label: "端到端闭环·委托签",
    // "待签" is already the gate truth (G5 needs_human); the delegated-signature
    // nuance belongs in the tooltip, not in a second suffix.
    short: "闭环·待签",
    tone: "pending",
    hint: "真实执行的端到端闭环（PIPE-20261110T163849Z-e2bd4a）：S1→G5 全部门禁真实生效、closure 16 项检查 ready；但语料是 fixture（不可作科学结论），G5 的签名是 autopilot 委托签（submission=false），不是人签。"
  },
  perovskite: {
    label: "示例·调研",
    short: "示例·调研",
    tone: "example",
    hint: "静态示例：span-only 文献检索与 gap→候选假设，停在 G1 人工收敛前。"
  },
  archives: {
    label: "示例·调研",
    short: "示例·调研",
    tone: "example",
    hint: "静态示例：自改进 agent 的 archive 使用，只有检索计划，未进入执行。"
  },
  "evidence-writing": {
    label: "示例·写作",
    short: "示例·写作",
    tone: "example",
    hint: "静态示例：证据驱动写作槽位；没有已签 claim 前，结果与摘要保持 locked。"
  },
  "proposal-review": {
    label: "示例·命题",
    short: "示例·命题",
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
      ),
      // This example stops at the plan on purpose. Saying so is what makes it
      // demonstrable: a viewer otherwise assumes the flow died half-way.
      agent(
        "**这一条只到检索计划，不往下走**\n\n- 目的是先说明 archive 有三种（代码版本 / 轨迹反思 / 评测结果），混在一起谈会得到假结论\n- 还没有 span，也没有可检验假设，所以 G1 不开\n\n> 示例到此为止：它用来说明“先分层再调研”，不是一次完整研究。要看完整闭环请开「完整闭环」或「E2E 闭环」。"
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
    // Must move with stage, otherwise the thread chip reads "回放 0/9" while the
    // RUN panel reads "6/9 stages" for the same task.
    completedStages: mode === "writing" ? [0, 1, 2, 3, 4, 5] : [],
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
    // A writing task sits at the写作阶段; leaving every stage pending made RUN
    // say "NEXT S1" while the header said S8–S12.
    autoStages: freshStages().map((stage, index) =>
      mode === "writing" && index < 6 ? { ...stage, status: "done" } : stage
    ),
    messages: [
      system("STATIC WORKSPACE · 示例任务；不调用模型、不执行真实实验。"),
      user(
        mode === "writing"
          ? "这篇论文我想先写 Results 和 Abstract，能不能直接开始？"
          : "我的毕设想做科研智能体，但命题还很散，怎么收敛？"
      ),
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
          ),
      // Every example must end on its gate, otherwise it reads as a finished
      // fragment rather than a step that is deliberately blocked.
      mode === "writing"
        ? agent(
            "**四个槽位全部 locked**\n\n- Methods / Results / Figure / Abstract 都只接受已签 claim、EA、closure 引用\n- 当前没有一条已签 claim，所以没有任何槽位可以填数\n\n> 下一步不是“先写一版”，而是回 S5 完成 claim 人签。正文先于证据，后面每一段都要重写。",
            {
              type: "gate",
              gate: "S8–S12",
              title: "写作槽位保持 locked",
              reason: "缺少已签 claim / EA / closure 引用",
              status: "blocked"
            }
          )
        : agent(
            "**G1 待人工收敛**\n\n现在只有候选方向，还不是 claim。建议的验证顺序：\n\n1. 先证明门禁会卡住（可复现的 blocked）\n2. 再证明判定可重算（同一 EA 两次判定一致）\n3. 最后才谈自动化程度\n\n> 候选不写入 claim；G1 必须由人来定。",
            {
              type: "gate",
              gate: "G1",
              title: "候选假设待人工收敛",
              reason: "只有候选方向；尚未形成可检验 claim",
              status: "needs_human"
            }
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
      // G1/G2 must read pass: the run below only exists because the protocol was
      // frozen and approved. Leaving them needs_human while S5 passed produced an
      // impossible sequence (a run cannot execute before its design gate).
      { id: "G1", status: "pass", reason: "四条 RQ 已收敛为一条可检验断言（合并样本 + 分层）" },
      { id: "G2", status: "pass", reason: "分层与置换计划已冻结；run-capsule 绑定 protocol sha256" },
      { id: "S5", status: "pass", reason: "run-capsule completed · EA immutable" },
      { id: "G5", status: "blocked", reason: "claim / closure / signature 尚未人签" }
    ],
    coverage: { sources: 3, spans: 0, gaps: 1, abstractOnly: 0 },
    evidence: [
      {
        id: "CLM-ESE-01",
        kind: "claim",
        status: "unsigned",
        text: "在 click / requests / httpx 合并样本上，缺陷修复提交触碰测试的比例比其它提交高 0.0464（0.4136 vs 0.3672，置换 p=0.015；分层调整后 +0.0681，Mantel-Haenszel）；但 click 内方向反转（−0.0067），因此不能外推到单个项目。",
        scope: "三仓库便利样本 · 启发式标签 · 不可外推",
        refs: ["EA-65d32e114229", "ESE-MS-20261118-03"],
        note: "待人工签署：statement 与 human_reason 需在本地 CLI 定稿，网页不代签。"
      }
    ],
    protocol: null,
    protocolFrozen: true,
    // The run really happened (runtime_data/ese-ms-20261118-03/run/). Leaving the
    // structured record null made EVIDENCE print "not run / not sealed" while the
    // S5 gate and the transcript both cited this capsule and EA — the same screen
    // contradicting itself.
    run: {
      id: "ESE-MS-20261118-03",
      dataset: "msr-corpus:click,httpx,requests",
      seeds: 1,
      metric: "test_cochange_rate",
      mean: 0.3749,
      baseline: null,
      status: "completed · EA immutable",
      ea: "EA-65d32e114229",
      note: "读数来自 runtime_data/ese-ms-20261118-03/run/metrics.json（seed 42）。合并样本 0.3749；缺陷修复 0.4136 vs 其它 0.3672（差 +0.0464，置换 p=0.015），但 click 内方向反转，不能外推到单项目。"
    },
    replay: { basis: "real", source: "runtime_data/ese-ms-20261118-03" },
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: freshStages().map((stage, index) => (index <= 4 ? { ...stage, status: "done" } : stage)),
    messages: [
      system(
        "STATIC REPLAY · 回放一次真实 ESE 研究的完整闭环（ESE-MS-20261118-03，S1→META）。执行与读数全部真实（3 仓库 / 5132 提交）；claim / closure / signature 未人签——门禁停在哪里，叙事就讲到哪里。",
        "22:41:02"
      ),
      user(
        "研究一个问题：Python 项目里，缺陷修复提交是不是比功能提交更常触碰测试？这个差异经项目分层后还成立吗？",
        "22:41:10"
      ),
      withStage(
        agent(
          "**S1 · 问题拆解与语料固定**。ESE 的 S1 不是文献检索，是语料组装：拆成四个可检验子问题，3 个仓库 HEAD 固定，path+message 启发式标签；跑数之前先冻结协议。",
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
        "S1"
      ),
      user("标签用 path+message 启发式，会不会把标签打错？", "22:41:38"),
      withStage(
        agent(
          "会，所以它被写进了边界而不是藏起来：capsule 的 warning 里明记「labels are path/message heuristics」——test/bug 标签是启发式，不是人工标注。这限制所有结论的口径：比的是「启发式标签下的提交群体」，不是人工核验过的缺陷修复。",
          undefined,
          "22:41:44"
        ),
        "S1"
      ),
      withStage(
        agent(
          "**S2–S3 · G1 收敛**：四条 RQ 收敛为一条可检验断言——合并样本差值 + 分层检验（按项目 / 提交规模 / 生产代码共变）。\n\n> 候选不是 claim；收敛由人确认后写入 G1，断言本身仍需 S5b 人签。",
          {
            type: "gate",
            gate: "G1",
            title: "四条 RQ 已收敛为一条可检验断言",
            reason: "合并样本差值 + 分层检验；置换检验双侧 p",
            status: "pass"
          },
          "22:41:50"
        ),
        "S2–S3"
      ),
      withStage(
        agent(
          "**S4 · 分析计划**：假设、基线、主指标、分层与置换计划在此定死——\n\n- 假设：缺陷修复提交触碰测试的比例高于其它提交，且经分层调整后方向一致\n- 基线：其它提交（non-bugfix）｜主指标：test_cochange_rate｜seeds：[42]\n- 分层维度：project · commit_size_bucket · production_cochange\n- 置换检验：1000 次双侧（固定种子）",
          {
            type: "protocol",
            hypothesis: "缺陷修复提交触碰测试的比例高于其它提交，且经分层调整后方向一致。",
            baseline: "其它提交（non-bugfix）",
            metric: "test_cochange_rate",
            seeds: 1,
            controls: ["project", "commit_size_bucket", "production_cochange"],
            status: "G2 待冻结"
          },
          "22:42:05"
        ),
        "S4"
      ),
      user("分层和置换的细节也一起冻进去吗？", "22:42:12"),
      withStage(
        agent(
          "是。分层维度、置换次数与种子全部写进 protocol；run-capsule 会绑定它的 sha256（254d1d10…），跑数之后执行器只能按冻结的计划提取与统计，改分析 = 重新走 G2。",
          undefined,
          "22:42:18"
        ),
        "S4"
      ),
      withStage(
        agent(
          "**S4 · G2 冻结**：协议已冻结，run-capsule 绑定 protocol sha256；执行器只做提取与统计。",
          {
            type: "gate",
            gate: "G2",
            title: "分层与置换计划已冻结",
            reason: "协议先于数据；run-capsule 绑定 protocol sha256",
            status: "pass"
          },
          "22:42:30"
        ),
        "S4"
      ),
      withStage(
        agent(
          "**S5a 执行完成**：3 个仓库、5132 个提交。",
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
        "S5a"
      ),
      withStage(
        agent(
          "**合并读数**\n\n- 触碰测试：1924 / 5132 = **0.3749**，95% CI [0.3618, 0.3882]\n- 缺陷修复：352 / 851 = 0.4136；其它：1572 / 4281 = 0.3672\n- 差 **+0.0464**，置换检验双侧 p = **0.015**\n- 分层调整后（Mantel-Haenszel）：**+0.0681**\n- 时间切分：早期 0.3091 → 晚期 0.4410，差 +0.1319（p = 0.001）\n\n> 合并样本上差异为正。是否每个项目都成立，要分层才知道。",
          undefined,
          "22:43:20"
        ),
        "S5a"
      ),
      withStage(
        agent(
          "**RunCapsule 与 run contract**\n\n- capsule：dataset `msr-corpus:click,httpx,requests`（sha256 435713f0…）· code sha256 29d53e3e… · protocol sha256 254d1d10… · seeds [42] · environment python 3.8.7\n- run contract 核对 10 项：capsule.completed / identity.protocol / identity.dataset / identity.seeds / identity.metric / metrics.finite / evidence.present / evidence.hash / artifacts.required 全部 **pass**\n- **min_delta → fail（not_verifiable）**：没有配对基线指标\n\n整体 status = **attention**。",
          undefined,
          "22:43:32"
        ),
        "S5a"
      ),
      user("min_delta fail 会不会把这条 run 判废？", "22:43:40"),
      withStage(
        agent(
          "不会——它把能宣称的范围写死：没有与基线配对的读数，就只能报合并差值 +0.0464 与置换 p=0.015，不能说「超过基线」。run contract 的作用不是判死刑，是画边界：attention 状态如实跟着这条 run 走，面板与 BRIEF 都能看到它。",
          undefined,
          "22:43:46"
        ),
        "S5a"
      ),
      user("分层之后呢？我担心是某个项目把总体拉高了。", "22:44:01"),
      withStage(
        agent(
          "**S5b · 分层结果：差异不是每个项目都成立**\n\n- click：0.4375 vs 0.4442 → **-0.0067（方向反转）**\n- httpx：0.6264 vs 0.5838 → +0.0426\n- requests：0.3581 vs 0.2513 → +0.1068\n- 提交规模 1-2：+0.0708｜3-5：+0.1530｜>5：**-0.0791**\n- 生产代码共变：无 +0.0000｜有 +0.0591\n\n所以能写的只有：“在三仓库合并样本上高 0.046，但 click 内方向反转，因此不适用于单项目。” 不能写“缺陷修复提交更常改测试”。",
          undefined,
          "22:44:18"
        ),
        "S5b"
      ),
      user("这条现在能签吗？", "22:45:02"),
      withStage(
        agent(
          "**EA 已封存**：EA-65d32e114229 · kind=metric · source=ese-exec · scope=S5/ESE-MS-20261118-03 · **immutable**；evidence hash 41149c82… 钉住 metrics.json，任何改动都会被发现。\n\nclaim 已起草（CLM-ESE-01），但还不能由我签：statement 只能写三仓库合并样本口径，分层反转必须同引，human_reason 由人定稿——签名只在本地 CLI，网页不代签。",
          {
            type: "gate",
            gate: "S5b",
            title: "判定已产出，claim 待人签",
            reason: "EA sealed（EA-65d32e114229）；statement 只能写分层口径；human_reason 由人填",
            status: "needs_human"
          },
          "22:45:10"
        ),
        "S5b"
      ),
      withStage(
        agent(
          "**S6 结果图**：本轮未产出绑定 EA 的结果图（runtime_data/ese-ms-20261118-03 下没有 result-figure）。图不脱离 EA 单独引用；产出后若上游数据变更，会被标 stale 并暂停导出。",
          undefined,
          "22:45:40"
        ),
        "S6"
      ),
      withStage(
        agent(
          "**S8–S12 写作槽位**：claim 人签前不上数——allowed_result_numbers 为空，Results / Abstract 保持 locked；槽位只接受已签 claim / EA 引用，Limitations 由作者亲写。",
          undefined,
          "22:45:50"
        ),
        "S8–S12"
      ),
      withStage(
        agent(
          "**S13–S16 闭包口**：证据链五段走到这里——\n\n- RunCapsule ✓ completed（metric=test_cochange_rate，seeds=[42]）\n- EA ✓ immutable（EA-65d32e114229，source=ese-exec）\n- Claim · 待人工\n- Closure · 待执行\n- Signature · 待人工\n\n后三步都是人签步骤，agent 不代签。",
          {
            type: "gate",
            gate: "G5",
            title: "结论待人工签署",
            reason: "capsule 与 EA 已完成；claim / closure / signature 需要人执行 CLI",
            status: "blocked"
          },
          "22:46:00"
        ),
        "S13–S16"
      ),
      system(
        "等待人工：run claim --evidence-source ese-exec → closure ese-check → closure ese-sign。签完后页面的证据链会自动变为 SIGNED。",
        "22:46:05"
      ),
      withStage(
        agent(
          "**META 经验登记**：本轮过程经验写入记忆——「ESE 分层数据显示 click 方向反转；引用该结论必须带分层口径」。\n\n本轮没有可准入的参数改进提案，所以不生成自进化候选：经验 ≠ 能力增益。",
          undefined,
          "22:46:10"
        ),
        "META"
      ),
      system(
        "闭环叙事结束：执行与读数真实；S5b / G5 停在人工门不是缺陷，是门禁在正常工作。",
        "22:46:20"
      )
    ]
  };
}

/**
 * Replay of a really-executed end-to-end closed loop
 * (runtime_data/e2e-closed-loop, PIPE-20261110T163849Z-e2bd4a).
 *
 * Every reading below comes from that run's report.md / artifacts. Two honest
 * caveats are carried in the UI rather than hidden:
 *   - the pipeline really ran, but the corpus is fixture data (`fixture_mode:
 *     true`, "no API, no real experiment"), so it demonstrates the mechanism,
 *     not a scientific result;
 *   - the on-disk signature under G5 is `[delegated:autopilot]` with
 *     submission=false, which is NOT a human signature — the gate stays
 *     needs_human.
 */
/**
 * S1 literature facet annotations for the seeded sessions, keyed by task id.
 * Single source for both createSeedWorkspace and the run-once migration that
 * backfills already-persisted workspaces. Each entry is transcribed from what
 * that session's own artifacts/messages state — see the per-task comments below.
 */
export const SEED_LITERATURE_ANNOTATIONS: Record<string, LiteratureAnnotation> = {
  // Real run: transcribed from its S1 message ("只覆盖了 2/6 个检索面向
  // （核心问题、综述），缺方法、评测、局限、近期进展") — not inferred.
  "e2e-closed-loop": {
    facets: [
      { id: "core", label: "核心问题", covered: true },
      { id: "survey", label: "综述", covered: true },
      { id: "method", label: "方法", covered: false },
      { id: "evaluation", label: "评测", covered: false },
      { id: "limitation", label: "局限", covered: false },
      { id: "recent", label: "近期进展", covered: false }
    ],
    source: "S1 覆盖声明（literature-ledger / 会话消息）"
  },
  // Teaching annotation consistent with the session's own plan card: its three
  // subqueries probe 核心/方法/评测（配对对照）; 综述/局限/近期 were never queried.
  // Demo data — the panel renders it under the task's demo label.
  "full-chain-demo": {
    facets: [
      { id: "core", label: "核心问题", covered: true },
      { id: "survey", label: "综述", covered: false },
      { id: "method", label: "方法", covered: true },
      { id: "evaluation", label: "评测", covered: true },
      { id: "limitation", label: "局限", covered: false },
      { id: "recent", label: "近期进展", covered: false }
    ],
    source: "S1 检索计划（plan 卡三个子查询的面向归属）"
  }
};

export function seedE2EClosedLoop(): ResearchTask {
  return {
    id: "e2e-closed-loop",
    name: "E2E 闭环：Iris 协议验证",
    goal: "完整走一遍 S1→G5 的受治理闭环：文献 → 候选 → G1 → 协议冻结 → 运行 → 证据 → 写作 → 闭合 → 签署，检验每一步的门禁是否真的卡住。",
    domain: "方法学 · 协议验证",
    mode: "experiment",
    access: "ask",
    status: "blocked",
    workspaceId: "thesis",
    createdAt: "2026-11-10",
    updatedAt: "2026-11-10T16:39:00",
    stage: 8,
    completedStages: [0, 1, 2, 3, 4, 5, 6, 7],
    harness: { version: "v1", budget: 6, label: "autopilot · policy AUTO-79d748b88e" },
    model: defaultModelSettings(),
    ...seedUsage([]),
    guidance: [],
    plugins: [],
    toolCalls: [],
    budget: { used: 3, total: 40 },
    gates: [
      { id: "Q0", status: "pass", reason: "1 篇全文 + 2 个 span；全文缺失的摘要只作线索" },
      { id: "G1", status: "pass", reason: "human-selected IDEA-02（独立预审 advance=0 / revise=2 / reject=0）" },
      { id: "G2", status: "pass", reason: "冻结的 ProtocolCard 与当前设计一致" },
      { id: "G3", status: "pass", reason: "论文契约与槽位已绑定；closure ready" },
      { id: "S5", status: "pass", reason: "capsule/EA 齐备；已绑定一条受支持的 claim" },
      { id: "G5", status: "needs_human", reason: "closure ready（16 项检查）；导出仍需人签——盘上是 autopilot 委托签，不是人签" }
    ],
    coverage: { sources: 2, spans: 2, gaps: 4, abstractOnly: 1 },
    evidence: [
      {
        id: "CLM-8a1d500c25",
        kind: "claim",
        text: "在本地 iris 协议上，三个种子的平均 accuracy 为 0.956。",
        status: "signed",
        scope: "local protocol validation · 不可外推到科学结论",
        refs: ["RUN-20261110T163848Z-f84f16", "EA-bf9f4eeca1d7"],
        note: "签署来源为 [delegated:autopilot]，submission=false；不是人签。",
        origin: "delegated"
      }
    ],
    protocol: {
      hypothesis: "StandardScaler + logistic regression 在冻结协议上超过多数类基线。",
      baseline: "majority class",
      metric: "accuracy",
      seeds: 3,
      controls: ["majority baseline"]
    },
    protocolFrozen: true,
    run: {
      id: "RUN-20261110T163848Z-f84f16",
      dataset: "sklearn:iris:150x4",
      seeds: 3,
      metric: "accuracy",
      mean: 0.956,
      // The run contract is blocked on min_delta precisely because there is no
      // paired baseline reading; a numeric 0 here would fake a delta.
      baseline: null,
      status: "completed · run contract blocked（min_delta 不可验证）",
      ea: "EA-bf9f4eeca1d7",
      note: "真实执行、fixture 语料（sklearn iris）。run contract 判 blocked：没有与基线配对的读数，只能报均值，不能宣称超过基线。"
    },
    replay: { basis: "fixture", source: "runtime_data/e2e-closed-loop" },
    literature: SEED_LITERATURE_ANNOTATIONS["e2e-closed-loop"],
    evaluation: emptyEvaluation(),
    evolution: { status: "idle", candidate: null, lease: "", history: [] },
    auto: { running: false, paused: false, index: 8, cycle: 0, gate: "claim", gateApproved: false },
    autoStages: freshStages().map((stage, index) =>
      index <= 7 ? { ...stage, status: "done" } : index === 8 ? { ...stage, status: "waiting" } : stage
    ),
    messages: [
      system(
        "STATIC REPLAY · 回放一次真实执行的端到端闭环（PIPE-20261110T163849Z-e2bd4a）。机制全部真实跑过，但语料是 fixture：数据不得当作科学结论；G5 盘上那份签名是 autopilot 委托签（submission=false），不是人签。",
        "16:30:00"
      ),
      user("用 fixture 语料把完整闭环跑一遍，我要看每一步的门是不是真的会卡住。", "16:30:12"),
      withStage(agent(
        "S1 完成。**覆盖只有 partial**：2 篇来源、1 篇有全文、2 个可定位 span、4 个 gap。\n\n只覆盖了 2/6 个检索面向（核心问题、综述），缺方法、评测、局限、近期进展。建议目标 ≥6 篇来源 / ≥3 篇全文 / ≥12 个 span。",
        {
          type: "sources",
          items: [
            { title: "FX-002 · Fixture Paper B", meta: "全文 · 2024 · Fixture Workshop（合成）", status: "ok" },
            { title: "FX-003 · Fixture Paper C", meta: "摘要线索 · 2023 · 不生成 span", status: "warn" }
          ],
          note: "摘要-only 只作线索；它不会变成 span，也不进入 claim。这两篇都是合成语料。"
        },
        "16:31:05"
      ), "S1"),
      withStage(agent(
        "S2–S3：从 span 生成两个候选帧，并做了独立预审。\n\n- **IDEA-01**（机制）：围绕「协议要求记录温度、湿度、样本量与停止条件」\n- **IDEA-02**（测量）：围绕「三次重复只有两次满足记录完整性检查」\n\n独立预审结果：**advance=0 / revise=2 / reject=0**。两个候选都需要改，G1 仍是人工收敛。",
        {
          type: "idea",
          gap: "只有 1 篇全文、2 个 span；候选是工作流演示，不是文献综述结论",
          candidates: [
            { id: "IDEA-01", text: "机制类：协议记录完整性 → 结果可判定性" },
            { id: "IDEA-02", text: "测量类：重复次数不足 → 不宣称稳定性提升" }
          ],
          note: "词法新颖性不等于文献新颖性；这是结构信号，不是新颖性证明。"
        },
        "16:32:10"
      ), "S2–S3"),
      user("G1：收敛到 IDEA-02，机制和指标由我补。", "16:33:00"),
      withStage(agent(
        "G1 记录为 pass，human-selected IDEA-02。\n\n注意：这一步在盘上是 autopilot 按 policy 执行的委托决策，文件在 `g1-decision.json`。",
        {
          type: "gate",
          gate: "G1",
          title: "候选已由人工语义收敛",
          reason: "选中 IDEA-02；两个候选预审均为 revise；候选不写入 claim",
          status: "pass"
        },
        "16:33:20"
      ), "S2–S3"),
      withStage(agent(
        "S4 设计冻结。\n\n- 假设：StandardScaler + logistic regression 超过多数类基线\n- 基线：majority class｜主指标：accuracy｜对照：majority baseline｜seeds：3\n- 设计审计：`attention`（blockers=0，warnings=1）\n- 协议卡 design_sha256 已绑定，G2 判 pass。",
        {
          type: "protocol",
          hypothesis: "StandardScaler + logistic regression 在冻结协议上超过多数类基线。",
          baseline: "majority class",
          metric: "accuracy",
          seeds: 3,
          controls: ["majority baseline"],
          status: "G2 pass · 已冻结"
        },
        "16:34:05"
      ), "S4"),
      withStage(agent(
        "S5a 执行完成：`RUN-20261110T163848Z-f84f16`，dataset `sklearn:iris:150x4`，seeds [17, 18, 19]，平均 **accuracy 0.956**；EA `EA-bf9f4eeca1d7` 已封装且不可变。\n\n但 run contract 判 **blocked**：`min_delta` 不可验证——没有与基线配对的指标读数，所以只能报均值，不能宣称“超过基线”。",
        {
          type: "run",
          id: "RUN-20261110T163848Z-f84f16",
          dataset: "sklearn:iris:150x4",
          seeds: 3,
          metric: "accuracy",
          mean: 0.956,
          // No paired baseline reading exists, so the card must not print a
          // delta: the run contract itself is blocked on min_delta.
          baseline: null,
          status: "completed · run contract blocked",
          ea: "EA-bf9f4eeca1d7",
          note: "run contract 判 blocked：min_delta 不可验证（没有与基线配对的指标读数）。只能报均值，不能宣称超过基线；数值来自真实执行，语料是 fixture。"
        },
        "16:35:00"
      ), "S5a"),
      withStage(agent(
        "S5b：claim 已绑定到 EA 与运行胶囊，但签署来源是 `[delegated:autopilot]`——**委托签不等于人签**，submission=false。\n\n所以这条 claim 只能在“本地协议验证”范围内引用，不能外推成科学结论。",
        undefined,
        "16:35:40"
      ), "S5b"),
      withStage(agent(
        "S8–S12 写作槽位：8 个章节全部有绑定状态，没有先于证据填数。\n\n- Abstract / Introduction / Related Work / Discussion → `draft_evidence`\n- Method / Experimental Setup → `bound_protocol`\n- Results / Conclusion → `bound_claim`\n\nResults 只引已签 claim `CLM-8a1d500c25`，不重算它的数值。",
        undefined,
        "16:36:20"
      ), "S8–S12"),
      withStage(agent(
        "中文投稿稿审计：**blocked**，submission_ready=False。四个阻断项：\n\n- `references.verified`：1 条引用缺可核验的文献元数据\n- `claims.evidence_ledger`：2 句需要证据\n- `claims.registry_coverage`：3 个候选只登记 1 个\n- `evidence.fixture`：fixture 证据不可引用\n\n这四条都是真阻断，不是提示。",
        undefined,
        "16:37:10"
      ), "S13–S16"),
      withStage(agent(
        "G5：closure **ready（16 项检查通过）**，但导出仍需要人签。\n\n盘上确实有一份 `signature.json`，但它是：\n- `human_reason`: `[delegated:autopilot] G5 closure signature under policy AUTO-79d748b88e`\n- `submission`: **false**\n- `signed_at`: 空\n\n所以 G5 在治理语义上仍是 `needs_human`——**机制闭环了，人签没有发生**。这不是缺陷，是门禁在正常工作。",
        {
          type: "gate",
          gate: "G5",
          title: "闭合完成，但仍待人签",
          reason: "closure 16 项检查 ready；盘上签名是 autopilot 委托签（submission=false），不是人签",
          status: "needs_human"
        },
        "16:38:00"
      ), "S13–S16"),
      system(
        "闭环结束。可对外的说法：机制全程真实执行、门禁逐一生效；语料是 fixture，不能作为科学结论；签署是委托签，不是人签。三件事必须一起讲，少一件就是夸大。",
        "16:39:00"
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
    replay: { basis: "demo", source: "前端教学演示 · 代理指标" },
    literature: SEED_LITERATURE_ANNOTATIONS["full-chain-demo"],
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
      seedE2EClosedLoop(),
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
