/**
 * Governance element graph (要素组合视图, design/151).
 *
 * The advisor's challenge this answers: "为何当前流程顺序如此？" — the stage
 * order is NOT an experience-preferred sequence; it is DERIVED from the
 * input/output dependencies between research elements. Each governance slot is
 * an element with declared consumes/produces, transcribed from the backend's
 * real invariants (modules/run, writing, figure, closure SPECs and AGENTS.md
 * §5) with per-edge provenance. Swapping two elements changes what flows
 * between them — exactly the composition-over-fixed-stages point.
 *
 * Rule kept from design/149: this file is a read-only projection; the element
 * list mirrors the method-registry stage slots (ese-method-registry-0.1).
 */

export interface ElementNode {
  id: string;
  /** 研究要素名（不是流程阶段名）：它回答"这一步产出/消费什么"。 */
  element: string;
  /** 要素目标（design/160）：该要素为什么存在、做到什么程度算成——
   * 锚定研究本质四段（提出问题/证据生产/主张与审查/积累），逐条可溯源。 */
  goal: string;
  /** 该要素产出的产物（供下游消费）。 */
  produces: string[];
  /** 上游要素 id -> 消费的东西（逐条对应后端不变式）。 */
  consumes: Array<{ from: string; what: string; source: string }>;
  /** 要素是否只能由人完成。 */
  human: boolean;
}

export const ELEMENTS: ElementNode[] = [
  {
    id: "S0",
    goal: "把模糊的研究兴趣转成可检索、可判定的问题——本阶段的目标是「提出问题」而非收集",
    element: "研究问题与路由",
    produces: ["研究问题", "任务路由计划"],
    consumes: [],
    human: false
  },
  {
    id: "S1",
    goal: "按方法收集能判别候选答案的证据原料——目标不是读得多，是证据可定位",
    element: "证据收集（检索/语料组装）",
    produces: ["SourceHit / Span", "文献台账"],
    consumes: [{ from: "S0", what: "研究问题拆解为子查询", source: "literature 模块（ESE 会话中 S1 = 语料组装）" }],
    human: false
  },
  {
    id: "S1b",
    goal: "把散点证据组织成可比较的结构——目标是不漏、可复核",
    element: "跨来源综合",
    produces: ["主题×来源矩阵"],
    consumes: [{ from: "S1", what: "Span 与文献台账（摘要-only 不进入）", source: "literature_synthesis：每个主题 ≥2 全文来源" }],
    human: false
  },
  {
    id: "S2–S3",
    goal: "提出问题的风险承担时刻：产出可否证的候选假设",
    element: "问题与假设",
    produces: ["候选假设（不是 claim）"],
    consumes: [
      { from: "S1b", what: "coverage gap 与综合矩阵", source: "idea 模块：从 gap 生成候选" },
      { from: "人", what: "G1 人工收敛", source: "pipeline strict 模式在 needs_g1 停下" }
    ],
    human: true
  },
  {
    id: "S4",
    goal: "把假设转成能判别其真假的验证手段——设计必须服务于判别",
    element: "研究方案（协议冻结）",
    produces: ["冻结协议（protocol sha256）"],
    consumes: [{ from: "S2–S3", what: "已收敛的假设——方案以假设为输入", source: "run SPEC：无冻结协议不得执行" }],
    human: true
  },
  {
    id: "S5",
    goal: "按冻结方案生产可复算的证据——不 work 也如实记录",
    element: "证据生产（执行）",
    produces: ["RunCapsule", "EA（immutable）"],
    consumes: [{ from: "S4", what: "冻结协议（protocol_sha256 必须一致）", source: "run SPEC v0.8.0：无冻结协议不执行" }],
    human: false
  },
  {
    id: "S5b",
    goal: "把证据转成经人签、带范围的主张——签的是范围，不是结论",
    element: "断言与签核",
    produces: ["ClaimRecord（signed）"],
    consumes: [
      { from: "S5", what: "EA（只绑定已存在 EA，scope 严格匹配）", source: "run SPEC：断言先重算后签署" },
      { from: "人", what: "human_reason（空理由被 CLI 拒绝）", source: "run SPEC" }
    ],
    human: true
  },
  {
    id: "S6",
    goal: "主张的可视化：让证据可读并与主张绑定——图不脱离证据",
    element: "结果图表",
    produces: ["图 + manifest（绑定 EA）"],
    consumes: [{ from: "S5b", what: "EA 绑定；上游变更标 stale", source: "figure SPEC：图不脱离 EA 引用" }],
    human: false
  },
  {
    id: "S8–S12",
    goal: "把主张转成可评审的文本——写作不先于证据",
    element: "写作与评审",
    produces: ["稿件槽位绑定"],
    consumes: [
      { from: "S5b", what: "已签 claim（未签 → allowed_result_numbers 为空）", source: "writing SPEC v0.9.0" },
      { from: "S6", what: "图 manifest", source: "writing SPEC：槽位只接受已签 claim/EA/图 manifest" }
    ],
    human: true
  },
  {
    id: "S13–S16",
    goal: "核对一致性并把结论送进公共记录——积累才算完成",
    element: "闭包与导出签核",
    produces: ["closure 报告", "export manifest"],
    consumes: [
      { from: "S5b", what: "已签 claim", source: "closure SPEC：四件产物一致性" },
      { from: "S5", what: "EA 与 capsule", source: "closure SPEC" },
      { from: "人", what: "G5 导出签名", source: "closure SPEC：签名只在本地 CLI" }
    ],
    human: true
  },
  {
    id: "META",
    goal: "积累与循环：把过程经验变成下一次研究的输入，完成积累",
    element: "经验与自改进",
    produces: ["过程经验", "自改进候选（lease 未授予不生效）"],
    consumes: [{ from: "S13–S16", what: "本轮任务反馈", source: "RSI 模块：候选不改 claim/gate/导出层" }],
    human: true
  }
];

/** Slot ids in element order — mirrors the method-registry stage slots. */
export const ELEMENT_ORDER: string[] = ELEMENTS.map((node) => node.id);

/**
 * The order is a topological order of this dependency graph. Testable
 * property: every consumed upstream element appears EARLIER in the list, so
 * "为何这个顺序" is answered by "因为这些输入在那之前才存在".
 */
export function elementById(id: string): ElementNode | undefined {
  return ELEMENTS.find((node) => node.id === id);
}

export function upstreamIds(node: ElementNode): string[] {
  return [...new Set(node.consumes.map((edge) => edge.from))];
}

/** Human elements = gates; the rest are executable/agent elements. */
export function isHumanElement(node: ElementNode): boolean {
  return node.human;
}

/** The dependency edges as renderable pairs (from -> to, what flows). */
export interface ElementEdge {
  from: string;
  to: string;
  what: string;
  source: string;
}

export function elementEdges(): ElementEdge[] {
  const edges: ElementEdge[] = [];
  for (const node of ELEMENTS) {
    for (const edge of node.consumes) {
      edges.push({ from: edge.from, to: node.id, what: edge.what, source: edge.source });
    }
  }
  return edges;
}
