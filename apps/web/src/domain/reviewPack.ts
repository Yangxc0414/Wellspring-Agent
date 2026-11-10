import { hypothesisConvergence, literatureCoverage } from "./researchBrief";
import type { ResearchTask, ReviewFinding, ReviewPackResult } from "./types";

export interface ReviewAgent {
  name: string;
  checks: string[];
}

const DEFAULT_REVIEWERS: ReviewAgent[] = [
  { name: "覆盖审阅", checks: ["coverage"] },
  { name: "引用审阅", checks: ["citation"] },
  { name: "假设审阅", checks: ["hypothesis"] }
];

const CHECK_LABELS: Record<string, string> = {
  coverage: "覆盖审计",
  citation: "引用对齐",
  hypothesis: "假设审阅",
  protocol: "协议审阅",
  evidence: "证据边界",
  figure: "图形审阅",
  closure: "闭包审阅"
};

function short(text: string, limit = 96): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > limit ? `${clean.slice(0, limit)}…` : clean;
}

function finding(
  reviewer: string,
  check: string,
  status: ReviewFinding["status"],
  summary: string
): ReviewFinding {
  return {
    id: `RF-${reviewer}-${check}`.replace(/\s+/g, "-"),
    reviewer,
    check,
    label: CHECK_LABELS[check] ?? check,
    status,
    summary: short(summary)
  };
}

function reviewCheck(task: ResearchTask, reviewer: string, check: string): ReviewFinding {
  if (check === "coverage") {
    const brief = literatureCoverage(task);
    const status =
      brief.saturation === "saturated"
        ? "pass"
        : brief.sources > 0 || brief.spans > 0
          ? "warn"
          : "blocked";
    return finding(
      reviewer,
      check,
      status,
      `${brief.sources} sources · ${brief.spans} spans · ${brief.gaps} gaps · ${brief.saturation}`
    );
  }

  if (check === "citation") {
    const refs = task.evidence.flatMap((item) => item.refs);
    const empty = task.evidence.filter((item) => item.refs.length === 0).length;
    if (task.coverage.spans === 0) {
      return finding(reviewer, check, "blocked", "没有 span，无法做引用对齐");
    }
    if (!refs.length) {
      return finding(reviewer, check, "warn", "当前没有 claim/候选引用");
    }
    return finding(
      reviewer,
      check,
      empty ? "warn" : "pass",
      `${refs.length} refs · ${empty} 个无引用对象 · 仅做结构对齐`
    );
  }

  if (check === "hypothesis") {
    const brief = hypothesisConvergence(task);
    const status = brief.candidates === 0 ? "blocked" : brief.multiRef > 0 ? "pass" : "warn";
    return finding(
      reviewer,
      check,
      status,
      `${brief.candidates} candidates · ${brief.multiRef} 个多证据支持`
    );
  }

  if (check === "protocol") {
    const status = task.protocolFrozen ? "pass" : task.protocol ? "warn" : "blocked";
    return finding(
      reviewer,
      check,
      status,
      task.protocolFrozen
        ? "协议已冻结；主指标/对照/seeds 锁定"
        : task.protocol
          ? "协议草案存在，等待 G2 冻结"
          : "还没有协议草案"
    );
  }

  if (check === "evidence") {
    const claim = task.evidence.find((item) => item.kind === "claim");
    const status = claim?.status === "signed" ? "pass" : task.run ? "warn" : "blocked";
    return finding(
      reviewer,
      check,
      status,
      task.run
        ? claim?.status === "signed"
          ? `claim ${claim.status} · EA 已封存`
          : "EA 已封存，claim 未签"
        : "尚未运行，无法检查 EA/claim"
    );
  }

  if (check === "figure") {
    return finding(
      reviewer,
      check,
      task.run ? "deferred" : "blocked",
      task.run ? "S6 图 provenance 当前静态审阅不执行" : "尚未运行，没有图可审"
    );
  }

  if (check === "closure") {
    const gate = task.gates.find((item) => item.id === "G5");
    const status = gate?.status === "pass" ? "pass" : task.run ? "deferred" : "blocked";
    return finding(
      reviewer,
      check,
      status,
      gate?.reason ?? "closure 尚未运行"
    );
  }

  return finding(reviewer, check, "deferred", "该 check 不在当前 stop point 内");
}

export function buildReviewPack(task: ResearchTask, agents: ReviewAgent[] = []): ReviewPackResult {
  const reviewers = agents.length
    ? agents.map((agent) => ({
        name: agent.name.trim() || "未命名审阅",
        checks: agent.checks.filter(Boolean)
      }))
    : DEFAULT_REVIEWERS;
  const findings = reviewers.flatMap((reviewer) =>
    reviewer.checks.map((check) => reviewCheck(task, reviewer.name, check))
  );
  const uniqueReviewers = new Set(findings.map((item) => item.reviewer)).size;
  const counts = findings.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] ?? 0) + 1;
    return acc;
  }, {});
  const summary = [
    `${uniqueReviewers} reviewers`,
    `${findings.length} checks`,
    `${counts.pass ?? 0} pass`,
    `${counts.warn ?? 0} warn`,
    `${counts.deferred ?? 0} deferred`,
    counts.blocked ? `${counts.blocked} blocked` : ""
  ]
    .filter(Boolean)
    .join(" · ");

  return {
    id: `RP-${Date.now().toString(36)}`,
    generatedAt: new Date().toISOString(),
    reviewers: uniqueReviewers,
    findings,
    summary,
    note:
      "只读 deterministic checks：不调用 LLM、不写 Claim/EA/gate，也不替代人工签署；deferred 表示当前静态 stop point 之外。"
  };
}
