import type { ResearchTask } from "./types";

export interface ResearchCheck {
  id: string;
  label: string;
  status: "ok" | "warn" | "missing";
  value: string;
  note: string;
}

export interface LiteratureCoverage {
  sources: number;
  fullText: number;
  abstractOnly: number;
  spans: number;
  gaps: number;
  score: number;
  saturation: "saturated" | "partial" | "insufficient";
  checks: ResearchCheck[];
  missing: string[];
  summary: string;
}

export interface HypothesisConvergence {
  candidates: number;
  multiRef: number;
  totalRefs: number;
  checks: ResearchCheck[];
  summary: string;
}

const TARGET_SOURCES = 6;
const TARGET_FULL_TEXT = 3;
const TARGET_SPANS = 12;

export function literatureCoverage(task: ResearchTask): LiteratureCoverage {
  const sources = task.coverage.sources;
  const abstractOnly = Math.min(task.coverage.abstractOnly, sources);
  const fullText = Math.max(0, sources - abstractOnly);
  const spans = task.coverage.spans;
  const gaps = task.coverage.gaps;

  const checks: ResearchCheck[] = [
    {
      id: "sources",
      label: "来源广度",
      status: sources >= TARGET_SOURCES ? "ok" : sources >= 3 ? "warn" : "missing",
      value: `${sources}/${TARGET_SOURCES}`,
      note: sources >= TARGET_SOURCES ? "达到建议来源数" : "建议补综述/方法/评测/局限面向"
    },
    {
      id: "full_text",
      label: "全文可读",
      status: fullText >= TARGET_FULL_TEXT ? "ok" : fullText >= 1 ? "warn" : "missing",
      value: `${fullText}/${TARGET_FULL_TEXT}`,
      note: "只有全文能生成 span"
    },
    {
      id: "spans",
      label: "可定位 span",
      status: spans >= TARGET_SPANS ? "ok" : spans >= 4 ? "warn" : "missing",
      value: `${spans}/${TARGET_SPANS}`,
      note: "span 是后续候选的唯一证据单位"
    },
    {
      id: "abstract",
      label: "摘要隔离",
      status: spans > 0 || abstractOnly === 0 ? "ok" : "warn",
      value: `${abstractOnly} 摘要-only`,
      note: "摘要只作线索，不进 claim"
    },
    {
      id: "gaps",
      label: "缺口登记",
      status: gaps > 0 ? "ok" : sources > 0 ? "warn" : "missing",
      value: `${gaps} gaps`,
      note: gaps > 0 ? "缺口已显式登记" : "未见 gap，需复核覆盖"
    }
  ];

  const sourceScore = Math.min(sources / TARGET_SOURCES, 1);
  const fullScore = Math.min(fullText / TARGET_FULL_TEXT, 1);
  const spanScore = Math.min(spans / TARGET_SPANS, 1);
  const gapScore = gaps > 0 ? 1 : sources > 0 ? 0.5 : 0;
  const score = Math.round((sourceScore * 0.35 + fullScore * 0.3 + spanScore * 0.2 + gapScore * 0.15) * 100) / 100;
  const saturation: LiteratureCoverage["saturation"] =
    sources >= TARGET_SOURCES && fullText >= TARGET_FULL_TEXT && spans >= TARGET_SPANS
      ? "saturated"
      : sources >= 3 || spans > 0
        ? "partial"
        : "insufficient";
  const missing = checks.filter((check) => check.status === "missing").map((check) => check.label);

  const summary =
    sources === 0 && spans === 0
      ? "尚未记录来源或 span；先完成 S1 检索，再用本 Skill 复核来源广度、全文与 gap。"
      : `共 ${sources} 篇来源（全文 ${fullText} / 摘要-only ${abstractOnly}），${spans} 个可定位 span、${gaps} 个 gap；` +
        `目标 ≥${TARGET_SOURCES} 篇来源 / ≥${TARGET_FULL_TEXT} 篇全文 / ≥${TARGET_SPANS} 个 span。当前 ${saturation}` +
        `${missing.length ? `，缺：${missing.join("、")}` : ""}。` +
        (saturation === "saturated"
          ? " 覆盖门槛已满足，可以进入 G1 人工收敛。"
          : " 建议先补齐来源广度与全文，再进入 G1；摘要-only 不进入证据。");

  return { sources, fullText, abstractOnly, spans, gaps, score, saturation, checks, missing, summary };
}

export function hypothesisConvergence(task: ResearchTask): HypothesisConvergence {
  const hypotheses = task.evidence.filter((item) => item.kind === "hypothesis");
  const refCounts = hypotheses.map((item) => item.refs.length);
  const multiRef = refCounts.filter((count) => count >= 2).length;
  const totalRefs = refCounts.reduce((sum, count) => sum + count, 0);
  const g1 = task.gates.find((gate) => gate.id === "G1");
  const noRefs = hypotheses.length > 0 && refCounts.every((count) => count === 0);

  const checks: ResearchCheck[] = [
    {
      id: "candidates",
      label: "候选数量",
      status: hypotheses.length >= 2 ? "ok" : hypotheses.length === 1 ? "warn" : "missing",
      value: `${hypotheses.length} 个`,
      note: hypotheses.length >= 2 ? "保留多个可比较方向" : "至少保留两个方向再 G1"
    },
    {
      id: "support",
      label: "多证据支持",
      status: noRefs ? "missing" : multiRef === hypotheses.length ? "ok" : "warn",
      value: `${multiRef}/${hypotheses.length}`,
      note: totalRefs ? `${totalRefs} 条证据引用` : "候选尚未绑定 span"
    },
    {
      id: "falsification",
      label: "否证条件",
      status: "warn",
      value: "G1 前补全",
      note: "每个候选必须写清何种结果会否证它"
    },
    {
      id: "novelty",
      label: "新颖性",
      status: "warn",
      value: "unverified",
      note: "先查相关工作，不能在候选阶段宣称新颖"
    },
    {
      id: "g1",
      label: "G1 人工收敛",
      status: g1?.status === "pass" ? "ok" : "warn",
      value: g1?.status ?? "needs_human",
      note: "自动策略不能替代人工收敛"
    }
  ];

  const summary =
    `${hypotheses.length} 个候选，${multiRef} 个引用 ≥2 条证据（共 ${totalRefs} 条引用）；` +
    `否证条件、机制/指标与新颖性仍需人工补全；G1 状态 ${g1?.status ?? "needs_human"}。` +
    (hypotheses.length >= 2
      ? " 可以把候选按机制 / 边界 / 测量三轴交给人工收敛。"
      : " 建议先扩展候选，再进入 G1。");

  return { candidates: hypotheses.length, multiRef, totalRefs, checks, summary };
}
