/**
 * design/176: 研究判断 → 过程分支建议（advisory，不改执行器、不改门禁）。
 *
 * 老师的框架要求三态决策不能压成二态：SUPPORTED / REFUTED / INCONCLUSIVE
 * 分别触发「继续分析 / 修正假设 / 补充证据」。我们已经有四态 StudyComparison.state，
 * 但只在 ContextPanel 里出文字，没有一等决策。本模块把它变成可测试的纯函数。
 *
 * 边界：这是 advisory 投影——只建议下一步，不自动跳阶段、不改 GateStatus、
 * 不产生 Claim。执行器仍由人签门禁控制。
 */

import type { StudyComparison } from "./types";

export type VerdictAction =
  | "continue_analysis"
  | "revise_hypothesis"
  | "add_evidence"
  | "needs_human";

export interface VerdictDecision {
  action: VerdictAction;
  label: string;
  reason: string;
  /** 老师三态到我们状态的映射，便于对照而非发明新词。 */
  triad: "SUPPORTED" | "REFUTED" | "INCONCLUSIVE" | "OUT_OF_SCOPE";
}

const ACTION_LABEL: Record<VerdictAction, string> = {
  continue_analysis: "继续分析",
  revise_hypothesis: "修正假设或理论",
  add_evidence: "补充证据后重判",
  needs_human: "交由人签判断"
};

/**
 * 单个比较的分支建议。四态来自 types.ts 的 StudyComparison.state：
 * positive → 支持（但只是支持这个比较，不等于整条 claim 成立）；
 * negative → 反驳；undecidable → 未判定（含"点估计为正但区间跨零"）；
 * unavailable → 无法判定（治理例外，交人）。
 */
export function researchVerdict(comparison: StudyComparison): VerdictDecision {
  switch (comparison.state) {
    case "positive":
      return {
        action: "continue_analysis",
        label: ACTION_LABEL.continue_analysis,
        reason: "该比较的方向成立；可继续做消融/机制分析，但结论范围仍受 EA scope 约束",
        triad: "SUPPORTED"
      };
    case "negative":
      return {
        action: "revise_hypothesis",
        label: ACTION_LABEL.revise_hypothesis,
        reason: "该比较的方向不成立；修正假设或理论，不要把反驳写成'没有差异'",
        triad: "REFUTED"
      };
    case "undecidable": {
      const seedsHint =
        typeof comparison.seeds_for_80pct === "number"
          ? `按当前效应量约需 ${comparison.seeds_for_80pct} 种子才可能判定；`
          : "";
      return {
        action: "add_evidence",
        label: ACTION_LABEL.add_evidence,
        reason: `${seedsHint}区间跨零或证据不足，不算提升也不算失败——补证据后重判`,
        triad: "INCONCLUSIVE"
      };
    }
    case "unavailable":
    default:
      return {
        action: "needs_human",
        label: ACTION_LABEL.needs_human,
        reason: "本次没有可判定的比较；不得据此推断结论，由人工决定是否补数据或改设计",
        triad: "OUT_OF_SCOPE"
      };
  }
}

/** 一组比较的整体建议：有任一 undecidable 就不宣布整体 SUPPORTED。 */
export function overallVerdict(comparisons: StudyComparison[]): VerdictDecision {
  if (!comparisons.length) {
    return {
      action: "needs_human",
      label: ACTION_LABEL.needs_human,
      reason: "没有比较可用；研究判断保持开放",
      triad: "OUT_OF_SCOPE"
    };
  }
  const decisions = comparisons.map(researchVerdict);
  if (decisions.some((item) => item.triad === "INCONCLUSIVE")) {
    return {
      action: "add_evidence",
      label: ACTION_LABEL.add_evidence,
      reason: "至少一个比较未判定；整体结论不能宣布为已支持",
      triad: "INCONCLUSIVE"
    };
  }
  if (decisions.some((item) => item.triad === "REFUTED")) {
    return {
      action: "revise_hypothesis",
      label: ACTION_LABEL.revise_hypothesis,
      reason: "至少一个比较被反驳；不得以其他比较的正向结果掩盖",
      triad: "REFUTED"
    };
  }
  if (decisions.every((item) => item.triad === "SUPPORTED")) {
    return {
      action: "continue_analysis",
      label: ACTION_LABEL.continue_analysis,
      reason: "全部比较方向成立；仍受 claim 三元组与 EA scope 约束",
      triad: "SUPPORTED"
    };
  }
  return {
    action: "needs_human",
    label: ACTION_LABEL.needs_human,
    reason: "比较结果无法归为三态；交人工判断",
    triad: "OUT_OF_SCOPE"
  };
}
