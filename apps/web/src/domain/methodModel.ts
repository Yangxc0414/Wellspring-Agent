/**
 * Method-model projection (方法原模型, design/149).
 *
 * The method registry (modules/method-registry/registry.json, schema
 * ese-method-registry-0.1) is DATA, not code: ten shared governance slots ×
 * nine research methods, each declaring where it fits, its protocol fields,
 * artifacts, checks and what it cannot support. The CLI queries it via
 * research_agent/method_registry.py; `workspace export` ships the SAME file to
 * apps/web/public/method-registry.json, so this view consumes the identical
 * source. Nothing here edits the registry — a read-only projection.
 */

export interface MethodStageSlot {
  id: string;
  name: string;
}

export interface MethodGuideline {
  key: string;
  citation: string;
  mandates: string;
}

export interface MethodDimension {
  dimension: string;
  basis: string;
}

export interface TagVocabularyEntry {
  tag: string;
  definition: string;
  basis: string;
}

export interface MethodRegistryMethod {
  id: string;
  name_zh: string;
  name_en: string;
  fit_stages: string[];
  guidelines?: MethodGuideline[];
  protocol_fields: string[];
  threat_focus?: string[];
  artifacts: string[];
  cannot_support: string[];
  checks: Array<{ id: string; severity: string; requires?: string[] }>;
  /** design/162: which composition wiring this method instantiates. */
  composition_id?: string;
  /** design/153: the three reference-model dimensions. */
  inputs?: string[];
  evidence_sources?: string[];
  evaluation_dimensions?: MethodDimension[];
  /** Per-slot task cards from the registry (stage id -> task text). */
  stage_tasks?: Record<string, string>;
  /** design/155: vocabulary tags from the 标签化梳理 todo. */
  tags?: string[];
}

export interface MethodRegistryData {
  schema: string;
  boundary: string;
  stages: MethodStageSlot[];
  methods: MethodRegistryMethod[];
  /** design/155: shared tag vocabulary (tag -> definition + basis). */
  tag_vocabulary?: TagVocabularyEntry[];
  /** design/156: the element port model + reference wirings (framework as data). */
  elements?: Array<{
    id: string;
    label: string;
    input_kinds: string[];
    outputs: Array<{ consumes: string | null; produces: string }>;
    human: boolean;
  }>;
  compositions?: Array<{
    id: string;
    label: string;
    sub: string;
    wiring: Array<{ element: string; consumes: string | null }>;
    /** design/162: element id -> governance slots it walks. */
    slot_map?: Record<string, string[]>;
  }>;
}

let cache: MethodRegistryData | null | undefined;

/** Fetch the exported registry snapshot (same file the CLI writes). Returns
 * null when it is missing — callers render an honest empty state. */
export async function loadMethodRegistry(): Promise<MethodRegistryData | null> {
  if (cache !== undefined) return cache;
  try {
    const response = await fetch("./method-registry.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(String(response.status));
    const data = (await response.json()) as MethodRegistryData;
    cache = data.schema === "ese-method-registry-0.5" ? data : null;
  } catch {
    cache = null;
  }
  return cache;
}

/**
 * Which method profile each seeded session demonstrates. Declared here (not on
 * the task) because the demo sessions are frontend constants; a runtime task
 * should carry its method id in task metadata and bypass this map.
 */
export const SESSION_METHOD: Record<string, string> = {
  "ese-ms-20261118-03": "repository-mining",
  "e2e-closed-loop": "controlled-experiment",
  "full-chain-demo": "controlled-experiment"
};

export function methodForSession(
  taskId: string | undefined,
  registry: MethodRegistryData | null
): MethodRegistryMethod | null {
  if (!taskId || !registry) return null;
  const id = SESSION_METHOD[taskId];
  return id ? (registry.methods.find((m) => m.id === id) ?? null) : null;
}

/** fit map for the matrix: stage id -> the method declares activity there. */
export function fitMap(method: MethodRegistryMethod): Record<string, boolean> {
  const map: Record<string, boolean> = {};
  for (const stage of method.fit_stages) map[stage] = true;
  return map;
}

export function blockerCount(method: MethodRegistryMethod): number {
  return method.checks.filter((check) => check.severity === "blocker").length;
}

/**
 * 证据类型与效力边界 per method (design/152).
 *
 * The classification is the standard empirical-methodology one (Easterbrook et
 * al. 2008, "Selecting Empirical Methods for Software Engineering Research";
 * Creswell, Research Design): each method produces a DIFFERENT KIND of
 * evidence, which is exactly why their inputs/outputs/validity differ. Every
 * validity limit below is verbatim from the registry's own cannot_support /
 * threat_focus fields — the kind label is the display-level classification.
 */
export interface EvidenceProfile {
  kind: string;
  /** 依据（文献） */
  basis: string;
  /** design/157：该方法下智能体的基线对比策略——由证据类型推导，
   * 与 run contract 语义一致（如无配对基线则只报差值，不宣称超过基线）。 */
  baselinePolicy: string;
  /** design/162：S5 执行槽位产出的具体证据形态——随方法变；
   * 但治理对证据的抽象要求（可固定 / 可复算 / 可核查）不变。 */
  artifactForm: string;
}

export const EVIDENCE_PROFILES: Record<string, EvidenceProfile> = {
  "controlled-experiment": {
    kind: "一手受控测量（受控 + 随机）",
    basis: "Wohlin 2014；实验的内部效度来自控制与随机化",
    baselinePolicy: "配对基线比较：效应量 + 功效分析 + 预注册主比较；宣称「超过基线」必须有预注册的主对照",    artifactForm: "RunCapsule + EA（受控测量记录）",
  },
  "quasi-experiment": {
    kind: "一手分组观察（有对照，无随机）",
    basis: "因果主张受识别策略限制",
    baselinePolicy: "对照组比较：效应估计限定于识别策略；须附敏感性分析",    artifactForm: "分组测量数据集（可哈希固定）",
  },
  "benchmark-evaluation": {
    kind: "标准化任务测量",
    basis: "可复现，但受污染与饱和威胁",
    baselinePolicy: "基准分数对比：污染检查 + 预算匹配 + 多重比较校正；跨基准排名不可宣称",    artifactForm: "基准评分 + 污染检查记录（可哈希固定）",
  },
  "repository-mining": {
    kind: "回顾性观察挖掘",
    basis: "生态效度好；标签为启发式，因果机制不可支持",
    baselinePolicy: "无配对基线读数——只报差值/相关与检验，不宣称超过基线（E2E/ESE 实测口径）",    artifactForm: "语料快照 + metrics.json（sha 固定）",
  },
  "systematic-literature-review": {
    kind: "二手综合（证据 = 已发表研究）",
    basis: "Kitchenham 2007 / PRISMA 2020；效力取决于检索与筛选的可复现性",
    baselinePolicy: "无一手基线——综合产出证据地图与共识/分歧；不与单一系统做排名对比",    artifactForm: "检索协议 + 筛选清单 + 综合矩阵（可复现重放）",
  },
  "case-study": {
    kind: "个案深描与三角验证",
    basis: "Runeson & Höst 2009；深度与机制，不可统计泛化",
    baselinePolicy: "无对照——结论是机制性理解与可转移性判断，不报效应量",    artifactForm: "访谈/文档/制品证据包（链式可溯）",
  },
  survey: {
    kind: "自报测量（问卷/访谈）",
    basis: "主观体验可测，行为因果不可支持",
    baselinePolicy: "自报分布与相关——不宣称行为因果；组间差异须答抽样框与无应答偏倚",    artifactForm: "应答数据集 + 提纲（可哈希固定）",
  },
  "design-science": {
    kind: "设计制品评估",
    basis: "效用主张限于评估策略所及",
    baselinePolicy: "制品效用对比按评估策略执行；贡献类型决定对比形式",    artifactForm: "制品 + 评估记录（可核查）",
  },
  "action-research": {
    kind: "介入循环反思",
    basis: "情境性知识；无介入则不可归因",
    baselinePolicy: "介入前后对照受情境限制——结论是情境性知识，不做统计归因",    artifactForm: "循环日志 + 反思记录（可追溯）",
  },
  "ml-iterative-experiment": {
    kind: "一手迭代测量（多种子 + 消融）",
    basis: "pengsida learning_research；Agarwal et al. 2021（statistical precipice）",
    baselinePolicy: "与已发表 SOTA 的可复现对比 + 消融；多种子区间报告；toy→real 迁移差距如实声明",    artifactForm: "实验日志 + 多种子结果 + 消融表（可复算）",
  }
};

export function evidenceProfileFor(methodId: string): EvidenceProfile | null {
  return EVIDENCE_PROFILES[methodId] ?? null;
}

/**
 * 标签化梳理的提取结果（design/155）：tags held by >=3 methods are
 * commonalities, ==2 partial, ==1 essential differences — the advisor's
 * "提炼共性、识别本质差异" as reproducible data.
 */
export type TagGroup = "common" | "partial" | "difference";

export interface TagAnalysisRow {
  tag: string;
  definition: string;
  basis: string;
  methods: string[];
  group: TagGroup;
}

export function tagAnalysis(registry: MethodRegistryData): TagAnalysisRow[] {
  const defs = new Map((registry.tag_vocabulary ?? []).map((entry) => [entry.tag, entry]));
  const counter = new Map<string, string[]>();
  for (const method of registry.methods) {
    for (const tag of method.tags ?? []) {
      const list = counter.get(tag) ?? [];
      list.push(method.id);
      counter.set(tag, list);
    }
  }
  const rows: TagAnalysisRow[] = [];
  for (const [tag, methods] of counter) {
    const group: TagGroup = methods.length >= 3 ? "common" : methods.length === 2 ? "partial" : "difference";
    const def = defs.get(tag);
    rows.push({
      tag,
      definition: def?.definition ?? "",
      basis: def?.basis ?? "",
      methods: [...methods].sort(),
      group
    });
  }
  return rows.sort((a, b) => b.methods.length - a.methods.length || a.tag.localeCompare(b.tag));
}

/**
 * 解析后的阶段计划（design/162）：mirror of method_registry.stage_plan —
 * the method's composition wiring walked in order, filtered to the method's
 * fit slots, per-slot task card attached; fit slots not covered by the
 * composition are appended with an uncovered marker.
 */
export interface MethodStagePlanStep {
  slot: string;
  task: string;
  uncovered?: boolean;
}

export function stagePlanFor(
  method: MethodRegistryMethod,
  registry: MethodRegistryData
): { compositionId: string; label: string; stages: MethodStagePlanStep[] } | null {
  const composition = (registry.compositions ?? []).find((item) => item.id === method.composition_id);
  if (!composition) return null;
  const slotMap = composition.slot_map ?? {};
  const fit = new Set(method.fit_stages);
  const stages: MethodStagePlanStep[] = [];
  const seen = new Set<string>();
  for (const step of composition.wiring) {
    for (const slot of slotMap[step.element] ?? []) {
      if (fit.has(slot) && !seen.has(slot)) {
        seen.add(slot);
        stages.push({ slot, task: method.stage_tasks?.[slot] ?? "" });
      }
    }
  }
  const uncovered = method.fit_stages.filter((slot) => !seen.has(slot));
  for (const slot of uncovered) {
    stages.push({ slot, task: method.stage_tasks?.[slot] ?? "", uncovered: true });
  }
  return { compositionId: composition.id, label: composition.label, stages };
}
