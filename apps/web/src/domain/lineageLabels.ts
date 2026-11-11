/**
 * Human-readable vocabulary for the evidence-lineage page.
 *
 * The snapshot itself is machine output (ids, sha256 prefixes, English stage keys).
 * Every label a reader sees is derived from this single table, so the graph, the
 * stage list and the inspector cannot drift into three different explanations.
 * Descriptions state what the artifacts are; they do not claim any capability
 * that the runtime does not have (signing and export still belong to the CLI).
 */

export interface LineageKindLabel {
  /** Short English tag kept for people who read the CLI output. */
  en: string;
  /** Plain-language Chinese name. */
  zh: string;
  /** One sentence explaining what this node is and why it matters. */
  desc: string;
}

export const LINEAGE_KINDS: Record<string, LineageKindLabel> = {
  dataset: {
    en: "DATASET",
    zh: "数据集",
    desc: "本次研究所用的数据快照；它的内容哈希是整条链的起点。"
  },
  code: {
    en: "CODE",
    zh: "运行代码",
    desc: "产生 run 的代码版本，与数据集一起决定结果是否可复现。"
  },
  bibliography: {
    en: "BIBLIOGRAPHY",
    zh: "参考文献",
    desc: "稿件引用的文献清单，closure 会检查引用是否都已绑定。"
  },
  bib: {
    en: "BIBLIOGRAPHY",
    zh: "参考文献",
    desc: "稿件引用的文献清单，closure 会检查引用是否都已绑定。"
  },
  run: {
    en: "RUN",
    zh: "运行记录",
    desc: "RunCapsule：一次本地执行的过程与指标记录，下游证据都指向它。"
  },
  protocol: {
    en: "PROTOCOL",
    zh: "冻结协议",
    desc: "G2 人工门冻结后的实验设计；冻结后不能静默改动。"
  },
  evidence: {
    en: "EA",
    zh: "证据断言",
    desc: "EvidenceArtifact：把 run 的数值封存成可核查的断言，是 claim 的依据。"
  },
  figure: {
    en: "FIGURE",
    zh: "结果图",
    desc: "由 run 产物绘制的图；重跑后必须重新绑定，不能沿用旧图。"
  },
  claim: {
    en: "CLAIM",
    zh: "研究主张",
    desc: "作者 / PI 在终端核对 EA 后人工签署的结论，浏览器不会代签。"
  },
  paper_slot: {
    en: "SLOT",
    zh: "稿件槽位",
    desc: "论文里引用证据的位置（方法、主结果、图、局限、相关引文等）。"
  },
  paper: {
    en: "PAPER",
    zh: "稿件",
    desc: "写作产物，其槽位逐条指向上游证据。"
  },
  closure: {
    en: "CLOSURE",
    zh: "闭合检查",
    desc: "导出前的一致性检查集合；未通过时不能生成导出清单。"
  },
  signature: {
    en: "SIGNATURE",
    zh: "签署",
    desc: "由 CLI 的 closure sign 产生的人签结果。"
  },
  export_manifest: {
    en: "EXPORT",
    zh: "导出清单",
    desc: "允许导出的产物清单；上游失效时会被锁定。"
  }
};

export interface LineageStageLabel {
  zh: string;
  hint: string;
}

export const LINEAGE_STAGES: Record<string, LineageStageLabel> = {
  sources: { zh: "数据与来源", hint: "数据、代码、文献——整条链的起点" },
  run: { zh: "本地运行", hint: "RunCapsule 记录这一次执行" },
  freeze: { zh: "协议冻结", hint: "G2 人工门之后设计不再变动" },
  evidence: { zh: "证据与结果图", hint: "EA 封存数值，结果图绑定 run" },
  claim: { zh: "研究主张", hint: "必须由作者在 CLI 人工签署" },
  slots: { zh: "稿件槽位", hint: "论文各段落分别引用了哪些证据" },
  paper: { zh: "稿件", hint: "写作产物，正文里的每个槽位都指向上游证据" },
  closure: { zh: "闭合检查", hint: "导出前的一致性检查" },
  signature: { zh: "签署与导出", hint: "人签之后导出清单才生效" }
};

/** Metadata keys that appear in the snapshot; anything unknown stays verbatim. */
export const LINEAGE_META_LABELS: Record<string, string> = {
  status: "状态",
  checks: "检查项数",
  ready: "就绪",
  scope: "适用范围",
  claim_id: "主张 ID",
  claimId: "主张 ID",
  run_id: "运行 ID",
  runId: "运行 ID",
  node_count: "节点数",
  seed: "随机种子",
  seeds: "随机种子",
  dataset: "数据集",
  statement: "主张内容",
  generated_at: "生成时间"
};

export const LINEAGE_ACTION_LABELS: Record<string, string> = {
  rerun: "需重跑",
  rewrite: "需重写",
  recheck: "需复核"
};

export function lineageKind(kind: string): LineageKindLabel {
  return (
    LINEAGE_KINDS[kind] ?? {
      en: kind.toUpperCase(),
      zh: kind,
      desc: "快照中的产物节点；点击可查看它的上游依赖与下游影响。"
    }
  );
}

export function lineageStage(stage: string): LineageStageLabel {
  return LINEAGE_STAGES[stage] ?? { zh: stage.toUpperCase(), hint: "快照中的一个阶段" };
}

export function lineageMetaLabel(key: string): string {
  return LINEAGE_META_LABELS[key] ?? key;
}

export function lineageActionLabel(action: string): string {
  return LINEAGE_ACTION_LABELS[action] ?? action;
}
