import type { Mode, Skill, SkillActivation } from "./types";

export interface SkillRouteProfile {
  stage: string;
  triggers: string[];
  modes: Mode[];
  summary: string;
  priority?: number;
}

export interface SkillRoute {
  skill: Skill;
  score: number;
  reason: string;
  trigger: string;
  mode: "auto" | "explicit";
}

export interface SkillRouteDecision {
  primary: SkillRoute | null;
  candidates: SkillRoute[];
  suppressedReason?: string;
}

export const SKILL_ROUTE_PROFILES: Record<string, SkillRouteProfile> = {
  "literature-brief": {
    stage: "S1",
    triggers: ["文献", "检索", "来源", "综述", "覆盖", "span", "gap", "survey", "literature", "检索式", "扩展检索", "全文"],
    modes: ["research", "auto"],
    summary: "审计来源广度、全文覆盖与 span/gap",
    priority: 5
  },
  "hypothesis-triage": {
    stage: "S2–S3",
    triggers: ["假设", "候选", "novelty", "否证", "收敛", "idea", "创新点", "研究问题"],
    modes: ["research", "auto"],
    summary: "检查候选的证据支持、否证条件与跨来源",
    priority: 5
  },
  "protocol-review": {
    stage: "S4",
    triggers: ["协议", "baseline", "对照", "冻结", "seeds", "主指标", "实验设计", "消融", "ablation"],
    modes: ["experiment", "auto"],
    summary: "检查协议能否在 run 前冻结",
    priority: 6
  },
  "evidence-audit": {
    stage: "S5b/S13",
    triggers: ["claim", "ea", "证据", "门禁", "签署", "绑定", "越界", "closure", "闭合", "导出", "audit"],
    modes: ["research", "experiment", "writing", "auto"],
    summary: "检查 span→claim→EA→gate 的边界",
    priority: 7
  },
  "paper-slots": {
    stage: "S8–S12",
    triggers: ["写作", "槽位", "正文", "摘要", "段落", "引用", "manuscript", "paper", "section", "论文"],
    modes: ["writing", "auto"],
    summary: "按已签 claim 绑定写作槽位",
    priority: 6
  },
  "rsi-preflight": {
    stage: "META",
    triggers: ["自进化", "rsi", "租约", "dry-run", "回滚", "候选改进", "lease"],
    modes: ["auto"],
    summary: "检查候选是否只改策略层并具备回滚",
    priority: 6
  },
  "research-scout": {
    stage: "S2–S3",
    triggers: ["构思", "方向", "方案", "tier-1", "tier-2", "scout", "新颖性"],
    modes: ["research", "auto"],
    summary: "先查领域与方法两条线，再区分激进/稳妥方案",
    priority: 4
  },
  "experiment-manager": {
    stage: "S5",
    triggers: ["运行", "实验", "smoke", "预算", "gpu", "失败", "环境", "复现"],
    modes: ["experiment", "auto"],
    summary: "检查预算、短程验证与失败分诊",
    priority: 4
  },
  "exploration-check": {
    stage: "S5",
    triggers: ["探索", "收窄", "验证选择", "巡检", "小时"],
    modes: ["experiment", "auto"],
    summary: "检查是否退回调参、验证选择过多或探索收窄",
    priority: 3
  },
  "eval-integrity": {
    stage: "EVAL",
    triggers: ["held-out", "测试集", "评估隔离", "审计", "规则哈希", "复现基线", "泄漏", "leakage", "评估"],
    modes: ["research", "experiment", "writing", "auto"],
    summary: "检查 held-out 访问、规则冻结与复现基线",
    priority: 6
  }
};

const INSPECTION_HINTS = [
  "检查",
  "审计",
  "复核",
  "看看",
  "覆盖",
  "gap",
  "边界",
  "是否",
  "风险",
  "诊断",
  "体检",
  "评估",
  "收敛",
  "对比",
  "核对",
  "确认"
];

const STAGE_SKILL: Record<string, string> = {
  S1: "literature-brief",
  "S2–S3": "hypothesis-triage",
  S4: "protocol-review",
  S5a: "experiment-manager",
  S5b: "evidence-audit",
  S6: "evidence-audit",
  "S8–S12": "paper-slots",
  "S13–S16": "evidence-audit",
  META: "rsi-preflight"
};

export function skillActivationLabel(activation: SkillActivation): string {
  if (activation === "auto") return "按需";
  if (activation === "manual") return "手动";
  return "停用";
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasTrigger(text: string, trigger: string): boolean {
  const needle = trigger.toLowerCase();
  if (/[\u4e00-\u9fa5]/.test(needle)) return text.includes(needle);
  return new RegExp(`(^|[^a-z0-9])${escapeRegExp(needle)}([^a-z0-9]|$)`, "i").test(text);
}

export function routeSkill(input: {
  text: string;
  mode: Mode;
  skills: Skill[];
  autoRunning?: boolean;
}): SkillRouteDecision {
  const raw = input.text.trim();
  if (!raw) return { primary: null, candidates: [] };
  if (input.autoRunning) {
    return {
      primary: null,
      candidates: [],
      suppressedReason: "运行中的消息作为指导处理，不自动加载 Skill。"
    };
  }

  const explicit = raw.match(/^\/([^\s]+)(?:\s+([\s\S]*))?$/);
  if (explicit) {
    const token = explicit[1].toLowerCase();
    const skill = input.skills.find(
      (item) => item.id.toLowerCase() === token || item.name === explicit[1]
    );
    if (!skill) {
      return { primary: null, candidates: [], suppressedReason: "没有找到这个 Skill。" };
    }
    if (skill.activation === "off") {
      return { primary: null, candidates: [], suppressedReason: "该 Skill 已停用。" };
    }
    return {
      primary: {
        skill,
        score: 100,
        reason: `你显式指定了 /${skill.id}`,
        trigger: explicit[1],
        mode: "explicit"
      },
      candidates: []
    };
  }

  const normalized = raw.toLowerCase();
  if (!INSPECTION_HINTS.some((hint) => normalized.includes(hint))) {
    return {
      primary: null,
      candidates: [],
      suppressedReason: "执行动作完成后按阶段加载 Skill；当前消息先按普通流程处理。"
    };
  }

  const candidates: SkillRoute[] = [];
  for (const skill of input.skills) {
    if (skill.activation !== "auto" || skill.source !== "builtin") continue;
    const profile = SKILL_ROUTE_PROFILES[skill.id];
    if (!profile) continue;
    const hits = profile.triggers.filter((trigger) => hasTrigger(normalized, trigger));
    if (!hits.length) continue;
    let score = Math.min(hits.length, 3) * 12 + (profile.priority ?? 0);
    if (profile.modes.includes(input.mode)) score += 10;
    if (hits.length > 1) score += 4;
    candidates.push({
      skill,
      score,
      reason: `识别到「${hits.slice(0, 2).join(" / ")}」；${profile.summary}`,
      trigger: hits[0],
      mode: "auto"
    });
  }
  candidates.sort((a, b) => b.score - a.score || a.skill.name.localeCompare(b.skill.name, "zh"));

  return {
    primary: candidates[0] && candidates[0].score >= 22 ? candidates[0] : null,
    candidates: candidates.slice(0, 3)
  };
}

export function skillForStage(stageId: string | undefined, skills: Skill[]): Skill | null {
  if (!stageId) return null;
  const id = STAGE_SKILL[stageId];
  if (!id) return null;
  const skill = skills.find((item) => item.id === id);
  return skill && skill.activation === "auto" ? skill : null;
}
