import { create } from "zustand";
import { folderStorage } from "../adapters/folderStorage";
import { isSnapshot, normalizeSkill, staticAdapter } from "../adapters/staticAdapter";
import {
  createRun,
  getRun,
  loadCustomAgents,
  loadExecStats,
  loadRunArtifactJson,
  loadRunArtifacts,
  loadRunEvents,
  runtimeUrl,
  type RunEvent
} from "../adapters/runtimeApi";
import { applyRuntimeSnapshot, defaultRuntimeSource, type RuntimeDemo } from "../domain/runtimeSnapshot";
import { compactRuntimeLoop } from "../domain/runtimeLoop";
import { CLI_ONLY_NOTE, protocolFreezeCommand } from "../domain/gateCommands";
import { claimSignatureLabel, type SignedClaimRecord } from "../domain/claimSignature";
import { ACCESS_META, AUTO_STAGE_CATALOG, DEFAULT_PREFERENCES, builtinSkills, clampModel } from "../domain/catalog";
import { DEFAULT_SHORTCUTS } from "../domain/shortcuts";
import { hypothesisConvergence, literatureCoverage } from "../domain/researchBrief";
import { skillDraftFromChat } from "../domain/skillAuthoring";
import { routeSkill, skillForStage, type SkillRoute } from "../domain/skillRouting";
import { buildReviewPack, type ReviewAgent } from "../domain/reviewPack";
import {
  createConversationTask,
  createSeedWorkspace,
  createTask as buildTask,
  planCard,
  writingCard
} from "../domain/seed";
import type {
  AccessMode,
  AutomationPlan,
  AutoStage,
  Card,
  ContextAttachment,
  EvidenceItem,
  Gate,
  GateStatus,
  Guidance,
  MemoryEntry,
  MemoryKind,
  Message,
  Mode,
  ModelSettings,
  PermissionRequest,
  PersistedWorkspace,
  Plugin,
  Preferences,
  ResearchTask,
  RuntimeFlowMode,
  RuntimeSource,
  RuntimeTaskType,
  SettingsOrigin,
  SettingsSection,
  ShortcutAction,
  Skill,
  SkillActivation,
  ToolCall,
  UIState,
  Workspace,
  WorkspaceFolder
} from "../domain/types";
import { clockTime, formatBytes, isoDateOffset, isoNow, uid } from "../domain/utils";

const initialSnapshot = staticAdapter.load() ?? createSeedWorkspace();

const defaultUI: UIState = {
  contextTab: "run",
  search: "",
  expandedWorkspaces: {},
  sidebarOpen: false,
  contextOpen: false,
  contextCollapsed: false,
  // Wellspring-Agent is an agent product: the workbench opens straight into the tool
  // surface (task thread + context panel), not a marketing welcome screen. New
  // sessions start from TopBar "新会话" / Sidebar / command palette, which route back
  // to WelcomeHome on demand.
  welcomeOpen: false,
  skillsOpen: false,
  draftAccess: "ask",
  draftProfileId: "glm-5.3-flash",
  skillDraft: null,
  permissionRequest: null,
  newTaskOpen: false,
  newTaskMode: "research",
  modelOpen: false,
  pluginsOpen: false,
  paletteOpen: false,
  settingsOpen: false,
  settingsSection: "general",
  settingsOrigin: { kind: "welcome", taskId: "", label: "欢迎页" },
  filesOpen: false,
  filesWorkspaceId: "",
  focusComposerTick: 0,
  claimGateOpen: false
};

export interface ToastState {
  id: string;
  text: string;
}

type OverlayKey = "newTaskOpen" | "modelOpen" | "pluginsOpen" | "skillsOpen" | "paletteOpen";
type NewTaskInput = { name: string; goal: string; domain: string; mode: Mode; workspaceId: string; access?: AccessMode; profileId?: string };
type AddWorkspaceInput = { name: string; note: string; folder: WorkspaceFolder };
type CreateSkillInput = { name: string; description: string; instructions: string; tools: string[] };

interface WorkspaceActions {
  selectTask: (id: string) => void;
  activateWorkspace: (id: string) => void;
  toggleWorkspace: (id: string) => void;
  addWorkspace: (input: AddWorkspaceInput) => void;
  updateWorkspaceFolder: (id: string, folder: WorkspaceFolder) => void;
  deleteWorkspace: (id: string) => void;
  setMode: (mode: Mode) => void;
  setAccess: (mode: AccessMode) => void;
  openWelcome: (workspaceId?: string) => void;
  startSession: (input: {
    text: string;
    workspaceId: string;
    access: AccessMode;
    thinkingStop?: string | number | null;
    attachments?: ContextAttachment[];
  }) => void;
  setUI: (patch: Partial<UIState>) => void;
  setContextTab: (tab: UIState["contextTab"]) => void;
  openOverlay: (key: OverlayKey) => void;
  openFiles: (workspaceId?: string) => void;
  openNewTask: (mode?: Mode) => void;
  closeOverlays: () => void;
  openSettings: (section?: SettingsSection) => void;
  setSettingsSection: (section: SettingsSection) => void;
  closeSettings: () => void;
  focusComposer: () => void;
  setPreference: <K extends keyof Preferences>(key: K, value: Preferences[K]) => void;
  setShortcut: (action: ShortcutAction, shortcut: string) => void;
  addMemory: (input: { text: string; kind: MemoryKind; scope?: string; source?: string }) => void;
  deleteMemory: (id: string) => void;
  markMemorySynced: (ids: string[]) => void;
  archiveTask: (id: string) => void;
  restoreTask: (id: string) => void;
  hydrateSnapshot: (snapshot: PersistedWorkspace, silent?: boolean, message?: string) => boolean;
  setAutoPlan: (id: string, plan: AutomationPlan) => void;
  createNewTask: (input: NewTaskInput) => void;
  deleteTask: (id: string) => void;
  sendMessage: (text: string) => void;
  runResearch: () => void;
  designExperiment: () => void;
  freezeProtocol: () => void;
  runExperiment: () => void;
  signClaim: () => void;
  closeClaimGate: () => void;
  previewDemoClaim: () => void;
  resetDemoClaim: () => void;
  importSignedClaim: (record: SignedClaimRecord, scopeWarning?: string) => void;
  prepareWriting: () => void;
  submitEvaluation: () => void;
  runEvaluationAudit: () => void;
  createSkill: (input: CreateSkillInput) => Skill | null;
  importSkills: (skills: Skill[]) => void;
  setSkillActivation: (id: string, activation: SkillActivation) => void;
  deleteSkill: (id: string) => void;
  invokeSkill: (id: string, note?: string) => void;
  runReviewPack: () => Promise<void>;
  startLiveRun: (
    source?: RuntimeSource,
    taskType?: RuntimeTaskType,
    flowMode?: RuntimeFlowMode,
    options?: {
      runDataset?: "" | "iris" | "breast_cancer" | "chemlab";
      runSeeds?: number;
      g1DecisionFile?: string;
      protocolFile?: string;
      claimFile?: string;
      bibliographyFile?: string;
      runDir?: string;
    }
  ) => Promise<void>;
  confirmPermission: () => void;
  cancelPermission: () => void;
  startAuto: () => void;
  pauseAuto: () => void;
  resumeAuto: () => void;
  autoStep: () => void;
  stepAuto: () => void;
  stopAuto: () => void;
  previewCandidate: () => void;
  approveCandidate: () => void;
  rejectCandidate: () => void;
  rollbackHarness: () => void;
  saveModel: (settings: ModelSettings, options?: { silent?: boolean }) => void;
  registerPlugin: (plugin: Omit<Plugin, "id" | "status">) => void;
  togglePlugin: (id: string) => void;
  proposeToolCall: () => void;
  approveToolCall: (id: string) => void;
  denyToolCall: (id: string) => void;
  exportWorkspace: () => void;
  resetWorkspace: () => void;
  notify: (text: string) => void;
  dismissToast: () => void;
}

export interface WorkspaceStore extends PersistedWorkspace {
  ui: UIState;
  toast: ToastState | null;
  actions: WorkspaceActions;
}

const RUNTIME_STAGE_ALIASES: Record<string, string> = {
  literature: "S1",
  idea: "S2–S3",
  experiment: "S4",
  run: "S5a",
  judge: "S5b",
  support: "S5b",
  figure: "S6",
  paper: "S8–S12",
  writing: "S8–S12",
  closure: "S13–S16",
  meta: "META",
  rsi: "META"
};

function runtimeStageIndex(stage?: string | null): number {
  if (!stage) return -1;
  const normalize = (value: string) => value.replace(/[-–—]/g, "–").trim().toUpperCase();
  const target = normalize(RUNTIME_STAGE_ALIASES[stage.trim().toLowerCase()] ?? stage);
  return AUTO_STAGE_CATALOG.findIndex((entry) => normalize(entry.id) === target);
}

function message(role: Message["role"], text: string, card?: Card): Message {
  return { id: uid("msg"), role, at: clockTime(), text, ...(card ? { card } : {}) };
}

function gate(gates: Gate[], id: string, status: GateStatus, reason: string): Gate[] {
  return gates.map((item) => (item.id === id ? { ...item, status, reason } : item));
}

function withEvidence(evidence: EvidenceItem[], item: EvidenceItem): EvidenceItem[] {
  const exists = evidence.some((entry) => entry.id === item.id);
  return exists ? evidence.map((entry) => (entry.id === item.id ? item : entry)) : [...evidence, item];
}

const DEFAULT_PROTOCOL = {
  hypothesis: "双分子钝化层在 85°C / 85% RH 下延长 T80，且不降低初始 PCE。",
  baseline: "未钝化对照",
  metric: "T80（小时）· 初始 PCE",
  seeds: 3,
  controls: ["未钝化", "单分子钝化"]
};

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
  return { type: "protocol", ...DEFAULT_PROTOCOL, status: "G2 needs_human" };
}

function runCard(): Card {
  return {
    type: "run",
    id: "RUN-014",
    dataset: "perovskite / 本地 fixture",
    seeds: 3,
    metric: "T80 (h)",
    mean: 412,
    baseline: 286,
    status: "EA sealed · claim unsigned",
    ea: "EA-7c41"
  };
}

function claimGateCard(status: GateStatus = "needs_human", claim?: EvidenceItem): Card {
  const label = claimSignatureLabel(claim);
  return {
    type: "gate",
    gate: "S5 · CLAIM",
    title: status === "pass"
      ? label.demo
        ? "演示态预览 · claim 未真实签署"
        : "claim 已签署（来源见证据面板）"
      : "人工门：claim 待人工签署",
    reason: label.detail,
    status
  };
}

type SkillStep = { label: string; status: "done" | "pending" | "blocked"; note: string };

function skillStep(label: string, done: boolean, note: string, blocked = false): SkillStep {
  return { label, status: blocked ? "blocked" : done ? "done" : "pending", note };
}

function skillCardFor(task: ResearchTask, skill: Skill): Card {
  const claim = task.evidence.find((item) => item.kind === "claim");
  const signed = claim?.status === "signed";
  const closure = task.gates.find((gate) => gate.id === "G5");

  if (skill.id === "literature-brief") {
    const coverageBrief = literatureCoverage(task);
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status: coverageBrief.saturation === "saturated" ? "ok" : coverageBrief.sources > 0 ? "needs_input" : "blocked",
      summary: coverageBrief.summary,
      steps: coverageBrief.checks.map((check) =>
        skillStep(
          check.label,
          check.status === "ok",
          `${check.value} · ${check.note}`,
          check.status === "missing"
        )
      ),
      note: "覆盖审计只读：来源/全文/span/gap 可审计；综述/方法/评测/局限/近期六面向由 runtime LiteratureBrief 计算，静态前端不伪造。"
    };
  }

  if (skill.id === "hypothesis-triage") {
    const brief = hypothesisConvergence(task);
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status: brief.candidates === 0 ? "blocked" : brief.multiRef > 0 ? "ok" : "needs_input",
      summary: brief.summary,
      steps: brief.checks.map((check) =>
        skillStep(
          check.label,
          check.status === "ok",
          `${check.value} · ${check.note}`,
          check.status === "missing"
        )
      ),
      note: "假设收敛只读：不自动评 novelty、不自动通过 G1；低证据支持与无跨来源候选会被显式标出。"
    };
  }

  if (skill.id === "protocol-review") {
    const protocol = task.protocol;
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status: !protocol ? "blocked" : task.protocolFrozen ? "ok" : "needs_input",
      summary: !protocol
        ? "当前没有协议草案；先从 gap 进入 S4 设计。"
        : task.protocolFrozen
          ? "协议已冻结；主指标、对照与 seeds 均已锁定。"
          : "协议草案存在，但 G2 尚未冻结。",
      steps: [
        skillStep("假设", Boolean(protocol?.hypothesis), protocol?.hypothesis ?? "缺少假设"),
        skillStep("baseline", Boolean(protocol?.baseline), protocol?.baseline ?? "缺少 baseline"),
        skillStep("主指标", Boolean(protocol?.metric), protocol?.metric ?? "缺少主指标"),
        skillStep("seeds / 对照", Boolean(protocol?.seeds), protocol ? `${protocol.seeds} seeds · ${protocol.controls.join(" / ")}` : "未登记"),
        skillStep("G2 冻结", task.protocolFrozen, task.protocolFrozen ? "已冻结" : "等待人工冻结")
      ],
      note: "协议体检只读；不会代替人工冻结，也不会运行实验。"
    };
  }

  if (skill.id === "evidence-audit") {
    const status: "ok" | "needs_input" | "blocked" =
      task.coverage.spans === 0 ? "blocked" : signed ? (closure?.status === "pass" ? "ok" : "needs_input") : "needs_input";
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status,
      summary:
        task.coverage.spans === 0
          ? "没有 span，无法进入 claim。"
          : signed
            ? closure?.status === "pass"
              ? "claim 已签且 closure 通过；仍需导出签名。"
              : "claim 已签，但 closure 未通过，导出保持锁定。"
            : "已有 span，但 claim 未签；写作与导出保持 pending。",
      steps: [
        skillStep("span 可定位", task.coverage.spans > 0, `${task.coverage.spans} 个 span`),
        skillStep("EA 封存", Boolean(task.run), task.run?.ea ?? "尚未运行"),
        skillStep("claim 人签", signed, signed ? "signed" : "unsigned"),
        skillStep("closure 通过", closure?.status === "pass", closure?.reason ?? "未运行 closure")
      ],
      note: "审计只读；不会自动签 claim，也不会解锁导出。"
    };
  }

  if (skill.id === "paper-slots") {
    const writing = writingCard({ claimSigned: signed, protocolFrozen: task.protocolFrozen });
    const bound = writing.type === "writing" ? writing.slots.filter((slot) => slot.status === "bound").length : 0;
    const locked = writing.type === "writing" ? writing.slots.filter((slot) => slot.status === "locked").length : 0;
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status: signed ? (bound >= 4 ? "ok" : "needs_input") : "needs_input",
      summary: `${bound}/6 已绑定 · ${locked} 个槽位 locked；正文不会先于证据填数。`,
      steps: writing.type === "writing" ? writing.slots.map((slot) => ({
        label: slot.label,
        status: slot.status === "bound" ? "done" : slot.status === "locked" ? "blocked" : "pending",
        note: slot.note
      })) : [],
      note: "写作槽位只接受已签 claim / EA / closure 引用；不会生成正文。"
    };
  }

  if (skill.id === "rsi-preflight") {
    const candidate = task.evolution.candidate;
    const active = candidate?.status === "active";
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status: !candidate ? "blocked" : active ? "ok" : "needs_input",
      summary: !candidate
        ? "还没有自进化候选；先在 META 或自进化面板生成一个。"
        : active
          ? `${candidate.id} 已准入；租约：${candidate.lease}`
          : `${candidate.id} 当前状态：${candidate.status}`,
      steps: [
        skillStep("候选目标", Boolean(candidate), candidate?.target ?? "无候选"),
        skillStep("dry-run / public / hidden", Boolean(candidate), candidate?.evidence ?? "未登记证据"),
        skillStep("人工准入", active, active ? "已准入（演示数据）" : "等待人工"),
        skillStep("租约与回滚", active, candidate?.lease ?? "未授予")
      ],
      note: "preflight 只检查治理字段；claim / evidence / gate / rubric / export / signature 保持不可写。"
    };
  }

  if (skill.id === "research-scout" || skill.id === "experiment-manager" || skill.id === "exploration-check" || skill.id === "eval-integrity") {
    const evaluation = task.evaluation;
    const engineering = evaluation.interventions.filter((item) => item.kind === "engineering").length;
    const domain = evaluation.interventions.filter((item) => item.kind === "domain").length;
    const total = engineering + domain;
    const domainPercent = total ? Math.round((domain / total) * 100) : 0;
    const selectionRisk = evaluation.validationSelections > 10;

    if (skill.id === "research-scout") {
      return {
        type: "skill",
        skillId: skill.id,
        name: skill.name,
        version: skill.version,
        status: task.coverage.gaps > 0 ? (domain > 0 ? "ok" : "needs_input") : "needs_input",
        summary:
          task.coverage.gaps > 0
            ? `${task.coverage.gaps} 个 gap · ${domain}/${total || 0} 个干预回应领域结构`
            : "还没有可用的 gap；先完成 S1 与 G1。",
        steps: [
          skillStep("领域文献线", task.coverage.spans > 0, `${task.coverage.sources} 条来源 · ${task.coverage.spans} 个 span`),
          skillStep("方法文献线", task.coverage.spans > 0, "对比架构/目标函数/数据处理"),
          skillStep("大胆方案 Tier-1", domain > 0, `${domain} 个领域结构干预`),
          skillStep("稳妥方案 Tier-2", engineering > 0, `${engineering} 个工程/复现干预`),
          skillStep("新颖性对照", domain > 0 && task.coverage.gaps > 0, "避免把成熟技巧写成突破")
        ],
        note: "构思技能只读：先查文献再判断新颖性；不会把工程组合自动写成科学发现。"
      };
    }

    if (skill.id === "experiment-manager") {
      return {
        type: "skill",
        skillId: skill.id,
        name: skill.name,
        version: skill.version,
        status: !task.protocolFrozen ? "blocked" : task.run ? "ok" : "needs_input",
        summary: !task.protocolFrozen
          ? "协议尚未冻结；先完成 G2。"
          : task.run
            ? `${task.run.seeds} seeds · ${evaluation.trainCost ?? "—"} GPU·h · 验证选择 ${evaluation.validationSelections} 次`
            : "协议已冻结；下一步做短程 smoke 并核对预算。",
        steps: [
          skillStep("协议冻结", task.protocolFrozen, task.protocolFrozen ? "主指标/对照/seeds 锁定" : "等待 G2"),
          skillStep("短程 smoke", Boolean(task.run), "先 1–2 轮核对数据加载与设备使用"),
          skillStep("预算与并行", task.budget.used < task.budget.total, `${task.budget.used}/${task.budget.total} budget`),
          skillStep("失败分诊", total > 0, "实现错误 / 环境 / 方案不适配"),
          skillStep("独立目录与 seeds", Boolean(task.run), `${task.run?.seeds ?? "—"} seeds`)
        ],
        note: "实验管理只读：不替代真实调度器；GPU/CPU 隔离与短程检查仍需 runtime。"
      };
    }

    if (skill.id === "exploration-check") {
      const narrowed = total > 0 && domainPercent < 25;
      return {
        type: "skill",
        skillId: skill.id,
        name: skill.name,
        version: skill.version,
        status: selectionRisk ? "blocked" : total ? (narrowed ? "needs_input" : "ok") : "needs_input",
        summary: total
          ? `${evaluation.validationSelections} 次验证选择 · 领域干预 ${domainPercent}%${selectionRisk ? " · 过拟合风险" : ""}`
          : "还没有干预台账；无法判断探索是否收窄。",
        steps: [
          skillStep("仍在探索", task.coverage.gaps > 0, `${task.coverage.gaps} 个 open gap`),
          skillStep("未退回纯调参", !narrowed, `${domainPercent}% domain interventions`),
          skillStep("验证选择压力", !selectionRisk, `${evaluation.validationSelections} 次选择`),
          skillStep("GPU / 预算使用", task.budget.used < task.budget.total, `${task.budget.used}/${task.budget.total}`),
          skillStep("重新规划", total > 0, "收窄时先停预算，再重排 Tier-1/Tier-2")
        ],
        note: "巡检技能只读：它提醒方向收窄和验证集过拟合，不会自动重排实验。"
      };
    }

    const integrityStatus: "ok" | "needs_input" | "blocked" =
      evaluation.audit === "pass" ? "ok" : evaluation.hiddenAccessCount > 1 ? "blocked" : "needs_input";
    return {
      type: "skill",
      skillId: skill.id,
      name: skill.name,
      version: skill.version,
      status: integrityStatus,
      summary:
        evaluation.audit === "pass"
          ? "held-out 已评估一次，过程审计通过。"
          : evaluation.hiddenAccessCount > 0
            ? "held-out 已提交，等待过程审计。"
            : "held-out 尚未访问；改进阶段仍与测试隔离。",
      steps: [
        skillStep("held-out 一次访问", evaluation.hiddenAccessCount === 1, `${evaluation.hiddenAccessCount}/1`),
        skillStep("评价规则冻结", evaluation.evalRuleHash !== "—", evaluation.evalRuleHash),
        skillStep("复现基线登记", evaluation.baselineReproduced !== null, `${evaluation.baselineReproduced ?? "—"}`),
        skillStep("过程审计", evaluation.audit === "pass", evaluation.audit),
        skillStep("成本记录", evaluation.trainCost !== null, `${evaluation.trainCost ?? "—"} GPU·h · ${evaluation.inferenceCost ?? "—"}× inference`)
      ],
      note: "评估隔离技能只读：真实系统的 held-out 隔离、规则冻结和审计必须在服务端执行。"
    };
  }

  return {
    type: "skill",
    skillId: skill.id,
    name: skill.name,
    version: skill.version,
    status: "needs_input",
    summary: skill.description,
    steps: [skillStep("读取会话上下文", true, "只读当前任务状态")],
    note:
      skill.source === "imported"
        ? "导入 Skill 只展示说明与检查占位；不执行 scripts，不调用外部工具，也不写 Claim/EA。"
        : "自定义 Skill 当前只生成静态检查结果，不执行真实工具。"
  };
}

function skillCallFor(task: ResearchTask, skill: Skill, note?: string) {
  const card = skillCardFor(task, skill);
  const statusLabel = card.type === "skill" ? card.status : "ok";
  const summary = card.type === "skill" ? card.summary : skill.description;
  const command = `/${skill.id}${note ? ` ${note}` : ""}`;
  const text = `已调用 **${skill.name}** \`v${skill.version}\`。\n\n- 状态：\`${statusLabel}\`\n- 结论：${summary}\n- 工具：${skill.tools.join(" · ")}\n\n> 技能只生成检查结果与下一步建议；不会调用外部工具，也不会越过 claim / EA / gate。`;
  return { card, command, text };
}

const SKILL_USE_NOTE = "只加载检查步骤；不执行 scripts、不调用外部工具，也不写 Claim/EA。";

function skillUseCard(route: SkillRoute, task: ResearchTask): Card {
  const result = skillCardFor(task, route.skill);
  const resultCard = result.type === "skill" ? result : null;
  return {
    type: "skill-use",
    skillId: route.skill.id,
    name: route.skill.name,
    version: route.skill.version,
    reason: route.reason,
    mode: route.mode,
    status: resultCard?.status ?? "needs_input",
    summary: resultCard?.summary ?? route.skill.description,
    steps: (resultCard?.steps ?? []).slice(0, 3),
    note: SKILL_USE_NOTE
  };
}

function skillUseMessage(route: SkillRoute, task: ResearchTask): Message {
  const lead = route.mode === "auto" ? "按需加载" : "手动加载";
  return message(
    "agent",
    `**${lead} Skill「${route.skill.name}」** · 已加入本轮检查`,
    skillUseCard(route, task)
  );
}

function insertSkillUse(task: ResearchTask, route: SkillRoute): ResearchTask {
  const index = task.messages.findIndex((item) => item.role === "agent");
  const messages = [...task.messages];
  messages.splice(index < 0 ? messages.length : index, 0, skillUseMessage(route, task));
  return { ...task, messages };
}

function resetAutoStages(): AutoStage[] {
  return AUTO_STAGE_CATALOG.map((stage) => ({ ...stage, status: "pending" }));
}

function stagesDone(stages: AutoStage[], indexes: number[]): AutoStage[] {
  return stages.map((stage, index) =>
    indexes.includes(index) ? { ...stage, status: "done" as const } : stage
  );
}

function autoStartGates(): Gate[] {
  return [
    { id: "Q0", status: "pending", reason: "cycle queued" },
    { id: "G1", status: "needs_human", reason: "等待自动收敛；生产环境需人签" },
    { id: "G2", status: "not_started", reason: "协议尚未冻结" },
    { id: "S5", status: "not_started", reason: "本轮尚未执行" },
    { id: "G5", status: "blocked", reason: "本轮没有 EA / Claim / Closure" }
  ];
}

function makeCandidate() {
  return {
    id: "CAND-RSI-014",
    target: "literature.query_planner",
    patch: "broad retrieval 前追加 review 子查询；预算从 6 调为 3。",
    rationale: "transfer 任务 coverage 偏薄，gap 数连续两轮为 0。",
    predicted: "多 1 篇全文、多 1 个可定位 span；不改变 claim 边界。",
    evidence: "public 3/3 · hidden 2/2 · regression 0 · near-OOD 待复核",
    lease: "未授予",
    status: "pending" as const
  };
}

function advanceAuto(task: ResearchTask, pauseAfter: boolean, skills: Skill[] = []): ResearchTask {
  if (!task.auto.running) return task;
  if (task.auto.gate === "claim" && !task.auto.gateApproved) return task;
  if (task.auto.index >= task.autoStages.length) return task;

  const index = task.auto.index;
  const stage = task.autoStages[index];
  if (!stage) return task;

  const pendingGuidance = task.guidance.filter((item) => item.status === "pending");
  const guidance: Guidance[] = task.guidance.map((item) =>
    item.status === "pending" ? { ...item, status: "applied", appliedAt: clockTime() } : item
  );
  const messages: Message[] = [...task.messages];

  if (pendingGuidance.length) {
    messages.push(
      message(
        "agent",
        `已按运行中指导调整（演示）：${pendingGuidance.map((item) => item.text).join("；")}。调整记录进入本次 run，不会改写已封存证据。`
      )
    );
  }

  const stageSkill = skillForStage(stage.id, skills);
  messages.push(
    message(
      "system",
      `${stage.id} ${stage.label} · ${stage.cmd} — ${stage.output}${stageSkill ? ` · SKILL ${stageSkill.name}` : ""}`
    )
  );

  const autoStages = task.autoStages.map((item, itemIndex) =>
    itemIndex === index ? { ...item, status: "done" as const } : item
  );
  const completedStages = Array.from(new Set([...task.completedStages, index]));
  let coverage = { ...task.coverage };
  let gates = task.gates.map((item) => ({ ...item }));
  let evidence = task.evidence;
  let protocol = task.protocol;
  let protocolFrozen = task.protocolFrozen;
  let run = task.run;
  let evaluation = task.evaluation;
  let evolution = task.evolution;
  let status = task.status;
  let auto = { ...task.auto, index: index + 1 };

  if (stage.gate) {
    coverage = { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 };
    gates = gate(gates, "S5", "pass", "EA 已封存（演示数据）");
    gates = gate(gates, "G5", "blocked", "claim 未签；closure 未运行");
    evidence = withEvidence(evidence, {
      id: "CLAIM-014",
      kind: "claim",
      status: "unsigned",
      text: "双分子钝化层在湿热条件下延长 T80，但效应量仍需独立复现。",
      scope: "S5/perovskite",
      refs: ["EA-7c41", "SPAN-014", "SPAN-021"],
      note: "claim 只能由作者/PI 签署；当前为待签状态。"
    });
    auto = { ...auto, paused: true, gate: "claim", gateApproved: false };
    status = "blocked";
    messages.push(
      message(
        "agent",
        "EA 已封存。claim 尚未签署，全自动停在人工门；你可以先看证据链，再查看终端里的人签命令。",
        claimGateCard("needs_human")
      )
    );
  } else if (index === 0) {
    coverage = { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 };
    gates = gate(gates, "Q0", "pass", "12 spans / 2 gaps 已记录（演示数据）");
    gates = gate(gates, "G1", "needs_human", "2 个候选假设等待收敛");
    evidence = withEvidence(evidence, {
      id: "GAP-001",
      kind: "gap",
      status: "open",
      text: "湿热循环后的配对定量对照缺失。",
      scope: "S1/perovskite",
      refs: ["SPAN-021"],
      note: "4 篇来源中只有 2 篇报告 T80。"
    });
    messages.push(
      message("agent", "**S1 · 检索完成**\n\n- 3 条全文 / 1 条摘要-only\n- 12 个可定位 span\n- 2 个 coverage gap\n\n> 摘要-only 只作线索，不生成 span。", sourcesCard())
    );
  } else if (index === 1) {
    gates = gate(gates, "G1", "pass", "演示策略自动收敛；生产环境需人签");
    evidence = withEvidence(evidence, {
      id: "CAND-H1",
      kind: "hypothesis",
      status: "candidate",
      text: "双分子钝化层降低界面缺陷密度 → 延长 T80。",
      scope: "S2/perovskite",
      refs: ["SPAN-014", "SPAN-021"]
    });
    messages.push(
      message("agent", "### G1 · 假设收敛\n\n- 保留 H1：双分子钝化层 → 延长 T80\n- 搁置 H2：疏水性主因\n\n> 候选仍不是 claim；生产环境必须人签。", ideaCard())
    );
  } else if (index === 2) {
    protocol = { ...DEFAULT_PROTOCOL, controls: [...DEFAULT_PROTOCOL.controls] };
    protocolFrozen = true;
    gates = gate(gates, "G2", "pass", "演示推进；真实 G2 冻结由 CLI 完成");
    messages.push(message("system", "G2 · 协议已冻结；后续运行不得改写主指标、对照与 seeds。"));
  } else if (index === 3) {
    run = {
      id: "RUN-014",
      dataset: "perovskite / 本地 fixture",
      seeds: 3,
      metric: "T80 (h)",
      mean: 412,
      baseline: 286,
      ea: "EA-7c41",
      status: "EA sealed · claim unsigned"
    };
    evaluation = {
      ...evaluation,
      baselineReproduced: evaluation.baselineReproduced ?? 286,
      validationSelections: evaluation.validationSelections + 1,
      trainCost: evaluation.trainCost ?? 2.4,
      evalRuleHash: evaluation.evalRuleHash === "—" ? "sha256:7c41e2" : evaluation.evalRuleHash
    };
    gates = gate(gates, "S5", "pass", "RUN-014 完成；EA 已封存（演示数据）");
    messages.push(
      message("agent", "**RUN-014 完成**\n\n- 3 seeds · EA 已封存\n- 数值只来自本地 fixture\n\n> 它与真实材料实验不是同一证据臂。", runCard())
    );
  } else if (index === 5) {
    messages.push(message("system", "S6 · SVG 与 manifest 已绑定到 EA-7c41；图不能脱离 EA 单独引用。"));
  } else if (index === 6) {
    messages.push(message("system", "S8–S12 · result.primary 仍为 pending_evidence；写作槽位不会抢先填数。"));
  } else if (index === 7) {
    gates = gate(gates, "G5", "blocked", "演示快照：closure 未运行；导出保持锁定");
    messages.push(message("system", "S13–S16 · 演示快照：closure 未运行，导出保持锁定；真实闭合状态请读 CLI closure 报告。"));
  } else if (index === 8) {
    const candidate = makeCandidate();
    evolution = {
      status: "proposed",
      candidate,
      lease: "",
      history: [{ at: clockTime(), text: "候选由 META 阶段生成；等待人工准入。" }]
    };
    messages.push(
      message(
        "agent",
        "自进化候选已生成：只改 query_planner 的检索预算，不触碰 claim、gate、rubric 或导出层。需要人工准入后才授予租约。",
        { type: "evolution", candidate }
      )
    );
  }

  const finished = index + 1 >= autoStages.length;
  if (finished) {
    auto = { ...auto, running: false, paused: false, gate: "", gateApproved: false };
    messages.push(
      message("system", "全自动演示已跑完阶段；claim 仍待人工签署，closure 未通过，导出与署名保持锁定。")
    );
  } else if (!auto.paused) {
    const next = autoStages[index + 1];
    if (next) autoStages[index + 1] = { ...next, status: "running" };
  }

  if (pauseAfter && !auto.paused && !finished) {
    auto = { ...auto, paused: true };
    const next = autoStages[index + 1];
    if (next) autoStages[index + 1] = { ...next, status: "pending" };
    messages.push(message("system", "单步完成，已暂停。"));
  }

  return {
    ...task,
    auto,
    autoStages,
    completedStages,
    coverage,
    gates,
    evidence,
    protocol,
    protocolFrozen,
    run,
    evaluation,
    evolution,
    status,
    stage: auto.index,
    budget: { ...task.budget, used: Math.min(task.budget.total, task.budget.used + 3) },
    guidance,
    messages,
    updatedAt: isoNow()
  };
}

function textTokens(text: string): number {
  if (!text) return 0;
  const cjk = (text.match(/[㐀-鿿]/g) ?? []).length;
  const other = text.length - cjk;
  return Math.ceil(cjk * 0.8 + other / 3.6);
}

function messageTokens(entry: Message): number {
  return textTokens(entry.text) + (entry.card ? textTokens(JSON.stringify(entry.card)) : 0);
}

type UsageDelta = Pick<ResearchTask, "usage" | "usageDays">;

function withMessageUsage(previous: ResearchTask, next: ResearchTask): UsageDelta {
  const known = new Set(previous.messages.map((entry) => entry.id));
  const added = next.messages.filter((entry) => !known.has(entry.id));
  if (!added.length) return { usage: next.usage, usageDays: next.usageDays ?? {} };
  const prompt = added.reduce((sum, entry) => sum + messageTokens(entry), 0);
  const completion = added
    .filter((entry) => entry.role === "agent")
    .reduce((sum, entry) => sum + messageTokens(entry), 0);
  const profileId = next.model.profileId;
  const current = next.usage[profileId] ?? { prompt: 0, completion: 0, requests: 0 };
  const nextUsage = {
    ...next.usage,
    [profileId]: {
      prompt: current.prompt + prompt,
      completion: current.completion + completion,
      requests: current.requests + 1
    }
  };
  const dayKey = isoDateOffset(0);
  const usageDays = next.usageDays ?? {};
  const dayBucket = usageDays[dayKey] ?? {};
  const dayCurrent = dayBucket[profileId] ?? { prompt: 0, completion: 0, requests: 0 };
  return {
    usage: nextUsage,
    usageDays: {
      ...usageDays,
      [dayKey]: {
        ...dayBucket,
        [profileId]: {
          prompt: dayCurrent.prompt + prompt,
          completion: dayCurrent.completion + completion,
          requests: dayCurrent.requests + 1
        }
      }
    }
  };
}

function persistedSnapshot(state: WorkspaceStore): PersistedWorkspace {
  return {
    version: state.version,
    selectedTaskId: state.selectedTaskId,
    activeWorkspaceId: state.activeWorkspaceId,
    preferences: state.preferences,
    workspaces: state.workspaces,
    tasks: state.tasks,
    plugins: state.plugins,
    skills: state.skills,
    memory: state.memory,
    archivedTaskIds: state.archivedTaskIds
  };
}

export const useWorkspaceStore = create<WorkspaceStore>((set, get) => {
  const currentTask = (): ResearchTask | undefined =>
    get().tasks.find((task) => task.id === get().selectedTaskId) ?? get().tasks[0];

  const mutateTask = (id: string, update: (task: ResearchTask) => ResearchTask): void => {
    set((state) => ({
      tasks: state.tasks.map((task) => {
        if (task.id !== id) return task;
        const next = update(task);
        const usageDelta = withMessageUsage(task, next);
        return { ...next, ...usageDelta, updatedAt: isoNow() };
      })
    }));
  };

  const openFiles = (workspaceId?: string): void => {
    set((state) => ({
      ui: {
        ...state.ui,
        filesOpen: true,
        filesWorkspaceId: workspaceId || state.activeWorkspaceId,
        newTaskOpen: false,
        modelOpen: false,
        pluginsOpen: false,
        skillsOpen: false,
        paletteOpen: false,
        sidebarOpen: false
      }
    }));
  };

  const notify = (text: string): void => {
    set({ toast: { id: uid("toast"), text } });
  };

  const openOverlay = (key: OverlayKey): void => {
    set((state) => ({
      ui: {
        ...state.ui,
        newTaskOpen: false,
        modelOpen: false,
        pluginsOpen: false,
        skillsOpen: false,
        paletteOpen: false,
        filesOpen: false,
        sidebarOpen: false,
        contextOpen: false,
        newTaskMode: key === "newTaskOpen" ? "research" : state.ui.newTaskMode,
        [key]: true
      }
    }));
  };

  const appendToCurrent = (fn: (task: ResearchTask) => ResearchTask): void => {
    const task = currentTask();
    if (task) mutateTask(task.id, fn);
  };

  const startAutoTask = (task: ResearchTask): ResearchTask => ({
    ...task,
    mode: "auto",
    status: "active",
    auto: { running: true, paused: false, index: 0, cycle: task.auto.cycle + 1, gate: "", gateApproved: false },
    autoStages: resetAutoStages().map((stage, index) => ({
      ...stage,
      status: index === 0 ? "running" : "pending"
    })),
    stage: 0,
    completedStages: [],
    gates: autoStartGates(),
    protocol: null,
    protocolFrozen: false,
    run: null,
    evidence: task.evidence.filter((item) => item.kind !== "claim"),
    messages: [
      ...task.messages,
      message("system", `受治理全自动 · cycle ${task.auto.cycle + 1} · 将在 S5b claim 人工门暂停。`),
      message("agent", "我会连续执行 S1→META。你可以随时输入指导，指导会在下一个阶段边界生效；claim 与导出不会自动签署。")
    ]
  });

  const startAutoInternal = (): void => {
    const task = currentTask();
    if (!task) return;
    if (task.auto.running) {
      notify(task.auto.paused ? "全自动已暂停；请使用继续或停止" : "全自动正在运行");
      return;
    }
    appendToCurrent(startAutoTask);
    notify("全自动已启动：会在 claim 人工门暂停");
  };

  let permissionBypass = false;

  const denyReadOnly = (task: ResearchTask, action: string): boolean => {
    if (task.access !== "read_only") return false;
    notify(`只读模式：不能${action}。请切换为「每次询问」或「完全访问」。`);
    return true;
  };

  const requestPermission = (
    task: ResearchTask,
    request: Omit<PermissionRequest, "id" | "taskId">
  ): boolean => {
    if (permissionBypass) return true;
    if (task.access === "ask") {
      set((state) => ({
        ui: {
          ...state.ui,
          permissionRequest: { ...request, id: uid("perm"), taskId: task.id }
        }
      }));
      return false;
    }
    return true;
  };

  const appendAutoSkill = (task: ResearchTask, skillId: string, reason: string): ResearchTask => {
    const skill = get().skills.find((item) => item.id === skillId);
    if (!skill || skill.activation !== "auto") return task;
    const route: SkillRoute = { skill, score: 0, reason, trigger: skillId, mode: "auto" };
    return { ...task, messages: [...task.messages, skillUseMessage(route, task)] };
  };

  return {
    ...initialSnapshot,
    memory: initialSnapshot.memory ?? [],
    archivedTaskIds: initialSnapshot.archivedTaskIds ?? [],
    preferences: {
      ...DEFAULT_PREFERENCES,
      ...(initialSnapshot.preferences ?? {}),
      shortcuts: {
        ...DEFAULT_SHORTCUTS,
        ...(initialSnapshot.preferences?.shortcuts ?? {})
      }
    },
    ui: defaultUI,
    toast: null,
    actions: {
      selectTask: (id) => {
        const task = get().tasks.find((item) => item.id === id);
        if (!task) return;
        const active = currentTask();
        if (active && active.id !== id && active.auto.running && !active.auto.paused) {
          mutateTask(active.id, (item) => ({
            ...item,
            auto: { ...item.auto, paused: true },
            messages: [...item.messages, message("system", "已暂停全自动：切换到其他任务。当前 run 保留，可稍后继续。")]
          }));
          notify("已暂停全自动：切换任务");
        }
        set((state) => ({
          selectedTaskId: id,
          activeWorkspaceId: task.workspaceId,
          ui: {
            ...state.ui,
            welcomeOpen: false,
            sidebarOpen: false,
            contextOpen: false,
            permissionRequest: null,
            expandedWorkspaces: {
              ...state.ui.expandedWorkspaces,
              [task.workspaceId]: true
            }
          }
        }));
      },
      openWelcome: (workspaceId) => {
        const active = currentTask();
        if (active && active.auto.running && !active.auto.paused) {
          mutateTask(active.id, (item) => ({
            ...item,
            auto: { ...item.auto, paused: true },
            messages: [...item.messages, message("system", "已暂停全自动：返回新会话。当前 run 保留，可稍后继续。")]
          }));
        }
        set((state) => ({
          activeWorkspaceId: workspaceId ?? state.activeWorkspaceId,
          ui: {
            ...state.ui,
            welcomeOpen: true,
            newTaskOpen: false,
            settingsOpen: false,
            sidebarOpen: false,
            contextOpen: false,
            filesOpen: false,
            permissionRequest: null,
            expandedWorkspaces: workspaceId
              ? { ...state.ui.expandedWorkspaces, [workspaceId]: true }
              : state.ui.expandedWorkspaces
          }
        }));
      },
      startSession: (input) => {
        const text = input.text.trim();
        if (!text) return;
        const state = get();
        const workspace = state.workspaces.find((item) => item.id === input.workspaceId) ?? state.workspaces[0];
        if (!workspace) {
          notify("没有可用工作区；请先导入文件夹或重置示例");
          return;
        }
        const skillDraft = skillDraftFromChat(text);
        if (skillDraft) {
          const base = buildTask({
            name: `技能草稿 · ${skillDraft.name}`,
            goal: skillDraft.description,
            domain: "其他",
            mode: "research",
            workspaceId: workspace.id,
            access: input.access,
            profileId: state.ui.draftProfileId,
            thinkingStop: input.thinkingStop
          });
          const task: ResearchTask = {
            ...base,
            messages: [
              message("system", "SKILL CREATOR · 静态草稿；保存前不会启用，不执行代码，不创建 Claim。"),
              message("user", text),
              message(
                "agent",
                `我把这条需求整理成技能草稿「${skillDraft.name}」。\n\n- 描述：${skillDraft.description}\n- 工具声明：${skillDraft.tools.join(" · ")}\n\n已放入 Skills 面板；检查指令后点击“保存 Skill”。保存前不会启用，也不会调用任何外部工具。`
              )
            ]
          };
          set((current) => ({
            tasks: [task, ...current.tasks],
            selectedTaskId: task.id,
            activeWorkspaceId: workspace.id,
            ui: {
              ...current.ui,
              welcomeOpen: false,
              newTaskOpen: false,
              settingsOpen: false,
              sidebarOpen: false,
              contextOpen: false,
              skillsOpen: true,
              skillDraft,
              permissionRequest: null,
              draftAccess: input.access,
              expandedWorkspaces: { ...current.ui.expandedWorkspaces, [workspace.id]: true }
            }
          }));
          notify(`技能草稿已生成：${skillDraft.name}；在 Skills 面板确认保存`);
          return;
        }
        const liveMatch = /^\/live(?:\s+(.*))?$/i.exec(text);
        const liveTopic = liveMatch ? (liveMatch[1] || "").trim() : "";
        if (liveMatch && !liveTopic) {
          notify("在欢迎页使用 /live 需要跟上研究问题，例如：/live 钙钛矿界面钝化");
          return;
        }
        const sessionText = liveMatch ? liveTopic : text;
        const baseTask = createConversationTask({
          text: sessionText,
          workspaceId: workspace.id,
          access: input.access,
          profileId: state.ui.draftProfileId,
          thinkingStop: input.thinkingStop,
          attachments: input.attachments
        });
        const decision = sessionText.startsWith("/")
          ? routeSkill({ text: sessionText, mode: baseTask.mode, skills: state.skills })
          : null;
        const task = decision?.primary ? insertSkillUse(baseTask, decision.primary) : baseTask;
        set((current) => ({
          tasks: [task, ...current.tasks],
          selectedTaskId: task.id,
          activeWorkspaceId: workspace.id,
          ui: {
            ...current.ui,
            welcomeOpen: false,
            newTaskOpen: false,
            settingsOpen: false,
            sidebarOpen: false,
            contextOpen: false,
            permissionRequest: null,
            draftAccess: input.access,
            expandedWorkspaces: { ...current.ui.expandedWorkspaces, [workspace.id]: true }
          }
        }));
        if (liveMatch) {
          notify("新会话已开始 · 正在连接本地 runtime");
          void get().actions.startLiveRun();
          return;
        }
        notify("新会话已开始 · 本地静态状态");
      },
      activateWorkspace: (id) => {
        set({ activeWorkspaceId: id });
      },
      toggleWorkspace: (id) => {
        set((state) => ({
          ui: {
            ...state.ui,
            expandedWorkspaces: {
              ...state.ui.expandedWorkspaces,
              [id]: !(state.ui.expandedWorkspaces[id] ?? true)
            }
          }
        }));
      },
      addWorkspace: (input) => {
        const active = currentTask();
        if (active && active.auto.running && !active.auto.paused) {
          mutateTask(active.id, (item) => ({
            ...item,
            auto: { ...item.auto, paused: true },
            messages: [
              ...item.messages,
              message("system", "已暂停全自动：添加本地文件夹并切换工作区。当前 run 保留，可稍后继续。")
            ]
          }));
        }
        const workspaceId = uid("ws");
        const folder = input.folder;
        const workspace: Workspace = {
          id: workspaceId,
          name: input.name,
          note: input.note,
          folder
        };
        const base = buildTask({
          name: `${workspace.name} · 资料盘点`,
          goal: `以本地文件夹「${folder.name}」为只读资料目录，先盘点可引用材料与缺口。`,
          domain: "其他",
          mode: "research",
          workspaceId,
          profileId: get().ui.draftProfileId
        });
        const task: ResearchTask = {
          ...base,
          messages: [
            message(
              "system",
              `LOCAL FOLDER · ${folder.name} · ${folder.files} 个文件 · ${formatBytes(folder.bytes)}；只登记元数据，不读取内容、不上传。`
            ),
            message(
              "agent",
              `文件夹「${folder.name}」已登记为工作区。浏览器只暴露文件名与大小；正文、引用与 span 仍需逐项导入并在 S1 核验。`,
              planCard(
                [`${folder.name} 研究问题`, "本地资料 关键词映射", "公开文献 对照"],
                `${folder.files} 个本地文件 · 只读元数据`,
                "先盘点后检索 · span-only",
                "文件夹内容未被读取：plan 只登记元数据，不生成 span。"
              )
            )
          ]
        };
        set((state) => ({
          workspaces: [...state.workspaces, workspace],
          tasks: [task, ...state.tasks],
          selectedTaskId: task.id,
          activeWorkspaceId: workspaceId,
          ui: {
            ...state.ui,
            welcomeOpen: false,
            newTaskOpen: false,
            settingsOpen: false,
            sidebarOpen: false,
            contextOpen: false,
            permissionRequest: null,
            expandedWorkspaces: { ...state.ui.expandedWorkspaces, [workspaceId]: true }
          }
        }));
        notify(`已添加工作区「${workspace.name}」· ${folder.files} 个文件（只读元数据）`);
      },
      updateWorkspaceFolder: (id, folder) => {
        set((state) => ({
          workspaces: state.workspaces.map((workspace) =>
            workspace.id === id
              ? {
                  ...workspace,
                  folder,
                  note: `本地文件夹 · ${folder.files} 个文件 · ${formatBytes(folder.bytes)} · 可预览`
                }
              : workspace
          )
        }));
        notify(`已读取「${folder.name}」· ${folder.files} 个文件（只读）`);
      },
      deleteWorkspace: (id) => {
        const state = get();
        const workspace = state.workspaces.find((item) => item.id === id);
        if (!workspace) return;
        if (state.workspaces.length <= 1) {
          notify("至少保留一个工作区");
          return;
        }
        const workspaceTasks = state.tasks.filter((task) => task.workspaceId === id);
        if (workspaceTasks.some((task) => task.auto.running)) {
          notify("该工作区还有全自动运行中的任务；先停止再删除");
          return;
        }
        const remainingWorkspaces = state.workspaces.filter((item) => item.id !== id);
        const remainingTasks = state.tasks.filter((task) => task.workspaceId !== id);
        const selectedRemoved = workspaceTasks.some((task) => task.id === state.selectedTaskId);
        const removedTaskIds = new Set(workspaceTasks.map((task) => task.id));
        const nextWorkspace =
          state.activeWorkspaceId === id ? remainingWorkspaces[0] : state.workspaces.find((item) => item.id === state.activeWorkspaceId);
        const nextTask = remainingTasks[0];
        set({
          workspaces: remainingWorkspaces,
          tasks: remainingTasks,
          archivedTaskIds: state.archivedTaskIds.filter((taskId) => !removedTaskIds.has(taskId)),
          activeWorkspaceId: nextWorkspace?.id ?? remainingWorkspaces[0].id,
          selectedTaskId: selectedRemoved ? nextTask?.id ?? "" : state.selectedTaskId,
          ui: {
            ...state.ui,
            welcomeOpen: selectedRemoved ? true : state.ui.welcomeOpen,
            contextOpen: false,
            permissionRequest: null,
            expandedWorkspaces: Object.fromEntries(
              Object.entries(state.ui.expandedWorkspaces).filter(([workspaceId]) => workspaceId !== id)
            )
          }
        });
        notify(`已删除工作区「${workspace.name}」及其 ${workspaceTasks.length} 个任务`);
      },
      setMode: (mode) => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.running && mode !== "auto") {
          if (!task.auto.paused) {
            mutateTask(task.id, (item) => ({
              ...item,
              auto: { ...item.auto, paused: true },
              messages: [...item.messages, message("system", "已暂停全自动：请先停止再切换模式。")]
            }));
            notify("已暂停全自动：请先停止再切换模式");
          } else {
            notify("全自动已暂停：请先停止再切换模式");
          }
          return;
        }
        mutateTask(task.id, (item) => ({ ...item, mode }));
      },
      setAccess: (mode) => {
        const task = currentTask();
        if (!task) return;
        if (task.access === mode) return;
        if (task.auto.running) {
          notify("全自动运行中：先停止再调整访问级别");
          return;
        }
        mutateTask(task.id, (item) => ({
          ...item,
          access: mode,
          messages: [
            ...item.messages,
            message("system", `访问级别切换为 ${ACCESS_META[mode].label} · ${ACCESS_META[mode].hint}`)
          ]
        }));
        set((state) => ({ ui: { ...state.ui, draftAccess: mode } }));
        notify(`访问级别：${ACCESS_META[mode].label}`);
      },
      setUI: (patch) => {
        set((state) => ({ ui: { ...state.ui, ...patch } }));
      },
      setContextTab: (tab) => {
        set((state) => ({
          ui: {
            ...state.ui,
            contextTab: tab,
            contextOpen: true,
            contextCollapsed: false
          }
        }));
      },
      openOverlay,
      openFiles,
      openNewTask: (mode = "research") => {
        set((state) => ({
          ui: {
            ...state.ui,
            newTaskOpen: true,
            newTaskMode: mode,
            modelOpen: false,
            pluginsOpen: false,
            skillsOpen: false,
            paletteOpen: false,
            sidebarOpen: false,
            contextOpen: false
          }
        }));
      },
      closeOverlays: () => {
        set((state) => ({
          ui: {
            ...state.ui,
            newTaskOpen: false,
            modelOpen: false,
            pluginsOpen: false,
            skillsOpen: false,
            paletteOpen: false,
            claimGateOpen: false
          }
        }));
      },
      openSettings: (section = "general") => {
        const task = get().tasks.find((item) => item.id === get().selectedTaskId);
        const origin: SettingsOrigin =
          get().ui.welcomeOpen || !task
            ? { kind: "welcome", taskId: "", label: "欢迎页" }
            : { kind: "task", taskId: task.id, label: task.name };
        set((state) => ({
          ui: {
            ...state.ui,
            newTaskOpen: false,
            modelOpen: false,
            pluginsOpen: false,
            skillsOpen: false,
            paletteOpen: false,
            filesOpen: false,
            sidebarOpen: false,
            contextOpen: false,
            permissionRequest: null,
            settingsOpen: true,
            settingsSection: section,
            settingsOrigin: origin
          }
        }));
      },
      setSettingsSection: (section) => {
        set((state) => ({ ui: { ...state.ui, settingsSection: section } }));
      },
      closeSettings: () => {
        const origin = get().ui.settingsOrigin;
        set((state) => ({
          selectedTaskId:
            origin.kind === "task" && state.tasks.some((task) => task.id === origin.taskId)
              ? origin.taskId
              : state.selectedTaskId,
          ui: {
            ...state.ui,
            settingsOpen: false,
            welcomeOpen: origin.kind === "welcome"
          }
        }));
      },
      focusComposer: () => {
        set((state) => ({ ui: { ...state.ui, focusComposerTick: state.ui.focusComposerTick + 1 } }));
      },
      setPreference: (key, value) => {
        set((state) => ({ preferences: { ...state.preferences, [key]: value } }));
      },
      setShortcut: (action, shortcut) => {
        set((state) => ({
          preferences: {
            ...state.preferences,
            shortcuts: { ...state.preferences.shortcuts, [action]: shortcut }
          }
        }));
      },
      addMemory: ({ text, kind, scope = "workspace", source = "user" }) => {
        const trimmed = text.trim();
        if (!trimmed) return;
        const entry: MemoryEntry = {
          id: uid("MEM"),
          text: trimmed.slice(0, 2000),
          kind,
          scope: scope.trim().slice(0, 120) || "workspace",
          source: source.trim().slice(0, 120) || "user",
          createdAt: isoNow()
        };
        set((state) => ({ memory: [entry, ...state.memory].slice(0, 500) }));
      },
      deleteMemory: (id) => {
        set((state) => ({ memory: state.memory.filter((entry) => entry.id !== id) }));
      },
      markMemorySynced: (ids) => {
        const stamp = isoNow();
        set((state) => ({
          memory: state.memory.map((entry) =>
            ids.includes(entry.id) ? { ...entry, syncedAt: stamp } : entry
          )
        }));
      },
      archiveTask: (id) => {
        const task = get().tasks.find((item) => item.id === id);
        if (!task) return;
        const archivedTaskIds = Array.from(new Set([...get().archivedTaskIds, id]));
        const remaining = get().tasks.find(
          (item) => item.id !== id && !archivedTaskIds.includes(item.id)
        );
        set((state) => ({
          archivedTaskIds,
          selectedTaskId:
            state.selectedTaskId === id && remaining ? remaining.id : state.selectedTaskId,
          ui:
            state.selectedTaskId === id
              ? {
                  ...state.ui,
                  welcomeOpen: true,
                  settingsOpen: false,
                  sidebarOpen: false,
                  contextOpen: false
                }
              : state.ui
        }));
        notify(`已归档「${task.name}」；可在设置 → 归档管理中恢复`);
      },
      restoreTask: (id) => {
        set((state) => ({
          archivedTaskIds: state.archivedTaskIds.filter((item) => item !== id)
        }));
        notify("已从归档恢复到任务列表");
      },
      hydrateSnapshot: (snapshot, silent = false, message = "已从本地文件夹恢复工作区") => {
        if (!isSnapshot(snapshot)) {
          notify("工作区文件格式不兼容，未恢复");
          return false;
        }
        const selectedTaskId = snapshot.tasks.some((task) => task.id === snapshot.selectedTaskId)
          ? snapshot.selectedTaskId
          : snapshot.tasks[0].id;
        const skills = Array.isArray(snapshot.skills)
          ? snapshot.skills.map((skill) => normalizeSkill(skill as Skill & { enabled?: boolean }))
          : builtinSkills();
        const next: PersistedWorkspace = {
          ...snapshot,
          selectedTaskId,
          skills,
          memory: Array.isArray(snapshot.memory) ? snapshot.memory : [],
          archivedTaskIds: Array.isArray(snapshot.archivedTaskIds) ? snapshot.archivedTaskIds : []
        };
        staticAdapter.save(next);
        set({
          ...next,
          preferences: {
            ...DEFAULT_PREFERENCES,
            ...(next.preferences ?? {}),
            shortcuts: { ...DEFAULT_SHORTCUTS, ...(next.preferences?.shortcuts ?? {}) }
          },
          ui: { ...defaultUI, welcomeOpen: false },
          toast: silent ? get().toast : { id: uid("toast"), text: message }
        });
        return true;
      },
      setAutoPlan: (id, plan) => {
        mutateTask(id, (task) => ({ ...task, autoPlan: plan }));
      },
      createNewTask: (input) => {
        const active = currentTask();
        if (active && active.auto.running && !active.auto.paused) {
          mutateTask(active.id, (item) => ({
            ...item,
            auto: { ...item.auto, paused: true },
            messages: [...item.messages, message("system", "已暂停全自动：创建新任务并切换。当前 run 保留，可稍后继续。")]
          }));
        }
        const task = buildTask({
          ...input,
          profileId: input.profileId ?? get().ui.draftProfileId
        });
        set((state) => ({
          tasks: [task, ...state.tasks],
          selectedTaskId: task.id,
          activeWorkspaceId: task.workspaceId,
          ui: {
            ...state.ui,
            welcomeOpen: false,
            newTaskOpen: false,
            settingsOpen: false,
            sidebarOpen: false,
            contextOpen: false,
            permissionRequest: null,
            draftAccess: input.access ?? state.ui.draftAccess,
            expandedWorkspaces: { ...state.ui.expandedWorkspaces, [task.workspaceId]: true }
          }
        }));
        notify("任务已创建；状态只保存在本地");
      },
      deleteTask: (id) => {
        const state = get();
        const task = state.tasks.find((item) => item.id === id);
        if (!task) return;
        if (task.auto.running) {
          notify("全自动运行中的任务不能删除；先停止");
          return;
        }
        const remaining = state.tasks.filter((item) => item.id !== id);
        const selected = task.id === state.selectedTaskId;
        const next = remaining[0];
        set({
          tasks: remaining,
          archivedTaskIds: state.archivedTaskIds.filter((item) => item !== id),
          selectedTaskId: selected ? next?.id ?? "" : state.selectedTaskId,
          activeWorkspaceId: selected && next ? next.workspaceId : state.activeWorkspaceId,
          ui: {
            ...state.ui,
            welcomeOpen: selected ? true : state.ui.welcomeOpen,
            contextOpen: false,
            permissionRequest: null
          }
        });
        notify("任务已删除");
      },
      sendMessage: (raw) => {
        const text = raw.trim();
        const task = currentTask();
        if (!text || !task) return;

        const draft = skillDraftFromChat(text);
        if (draft) {
          mutateTask(task.id, (item) => ({
            ...item,
            messages: [
              ...item.messages,
              message("user", text),
              message(
                "agent",
                `已整理成技能草稿「${draft.name}」。\n\n- 描述：${draft.description}\n- 工具声明：${draft.tools.join(" · ")}\n\n草稿已放入 Skills 面板；确认指令后保存。保存前不会启用，也不会执行代码或调用外部工具。`
              )
            ]
          }));
          get().actions.setUI({ skillsOpen: true, skillDraft: draft });
          notify("技能草稿已生成；在 Skills 面板确认保存");
          return;
        }

        if (text.startsWith("/")) {
          const [command, ...rest] = text.slice(1).split(/\s+/);
          const arg = rest.join(" ").trim();
          const skill = get().skills.find(
            (item) => item.id.toLowerCase() === command.toLowerCase() || item.name === command
          );
          if (skill) {
            get().actions.invokeSkill(skill.id, arg || undefined);
            return;
          }
        }

        mutateTask(task.id, (item) => ({
          ...item,
          messages: [...item.messages, message("user", text)]
        }));

        if (text.startsWith("/")) {
          const [command, ...rest] = text.slice(1).split(/\s+/);
          const arg = rest.join(" ").trim();
          switch (command.toLowerCase()) {
            case "start":
            case "auto":
              get().actions.startAuto();
              return;
            case "pause":
              get().actions.pauseAuto();
              return;
            case "resume":
              get().actions.resumeAuto();
              return;
            case "step":
              get().actions.stepAuto();
              return;
            case "stop":
              get().actions.stopAuto();
              return;
            case "research":
              get().actions.runResearch();
              return;
            case "review":
              void get().actions.runReviewPack();
              return;
            case "experiment":
              get().actions.designExperiment();
              return;
            case "freeze":
              get().actions.freezeProtocol();
              return;
            case "run":
              get().actions.runExperiment();
              return;
            case "live": {
              const latestTask = currentTask();
              const source: RuntimeSource | undefined =
                arg === "fixture" || arg === "real" || arg === "openalex"
                  ? (arg === "real" ? "real_corpus" : arg)
                  : latestTask ? defaultRuntimeSource(latestTask) : undefined;
              void get().actions.startLiveRun(source);
              return;
            }
            case "writing":
              get().actions.prepareWriting();
              return;
            case "sign":
            case "claim":
              get().actions.signClaim();
              return;
            case "evidence":
              get().actions.setContextTab("evidence");
              notify("已切到证据链");
              return;
            case "eval":
              get().actions.setContextTab("eval");
              notify("已切到评估隔离");
              return;
            case "evolution":
              get().actions.setContextTab("evolution");
              notify("已切到自进化");
              return;
            case "lineage":
              get().actions.openSettings("lineage");
              return;
            case "model":
              openOverlay("modelOpen");
              return;
            case "plugins":
              openOverlay("pluginsOpen");
              return;
            case "skills":
              openOverlay("skillsOpen");
              return;
            case "agents":
              get().actions.openSettings("agents");
              return;
            case "files":
              get().actions.openFiles();
              return;
            case "memory":
              get().actions.openSettings("memory");
              return;
            case "settings":
              get().actions.openSettings("general");
              return;
            case "new":
              get().actions.openWelcome();
              return;
            case "export":
              get().actions.exportWorkspace();
              return;
            case "help":
              appendToCurrent((item) => ({
                ...item,
                messages: [
                  ...item.messages,
                  message(
                    "agent",
                    "可用指令：/research 检索、/review 运行审阅包、/experiment 设计、/freeze 冻结、/run 运行、/live 本地 API 运行、/writing 写作槽位、/sign 签署、/start 全自动、/pause /resume /step /stop 控制、/evidence、/eval、/evolution、/lineage、/skills、/agents、/files、/memory、/new、/model、/plugins、/export、/settings、/help；输入 /技能 id 可直接调用 Skill。也可以说“帮我创建一个技能……”或 /skill-creator 生成草稿，确认后再保存。运行中输入普通文本会变成指导，在下一个阶段边界生效。"
                  )
                ]
              }));
              return;
            default:
              appendToCurrent((item) => ({
                ...item,
                messages: [
                  ...item.messages,
                  message("agent", `未知指令 /${command}${arg ? ` ${arg}` : ""}。输入 /help 查看可用动作；静态预览不会调用模型。`)
                ]
              }));
              return;
          }
        }

        const latest = currentTask();
        if (!latest) return;

        if (latest.auto.running) {
          mutateTask(latest.id, (item) => ({
            ...item,
            guidance: [
              ...item.guidance,
              { id: uid("guide"), text, at: clockTime(), status: "pending" }
            ],
            messages: [
              ...item.messages,
              message(
                "agent",
                latest.auto.paused
                  ? "指导已记下。当前运行已暂停；恢复后会在下一个阶段边界应用，不会改写已封存证据。"
                  : "收到运行中指导。会在下一个阶段边界应用，并写入本次 run 的 trace。"
              )
            ]
          }));
          return;
        }

        const routed = routeSkill({
          text,
          mode: latest.mode,
          skills: get().skills
        });
        const primarySkill = routed.primary;
        if (primarySkill) {
          appendToCurrent((item) => ({
            ...item,
            messages: [...item.messages, skillUseMessage(primarySkill, item)]
          }));
        }

        if (/自动/.test(text)) {
          get().actions.startAuto();
        } else if (/写作|槽位|摘要|正文/.test(text)) {
          get().actions.prepareWriting();
        } else if (/实验|设计|冻结|协议/.test(text)) {
          get().actions.designExperiment();
        } else if (/检索|调研|文献|来源|扩展/.test(text)) {
          get().actions.runResearch();
        } else if (/证据|claim|EA|门禁/i.test(text)) {
          get().actions.setContextTab("evidence");
          appendToCurrent((item) => ({
            ...item,
            messages: [
              ...item.messages,
              message("agent", "右侧已切到证据链。当前可宣称的边界以 span 与 gate 为准；静态预览不会自动写 claim。")
            ]
          }));
        } else {
          appendToCurrent((item) => ({
            ...item,
            messages: [
              ...item.messages,
              message(
                "agent",
                "已收到。当前是静态适配器，不会调用模型或外部 API。你可以点上方建议推进流程，或用 /start 运行受治理全自动、/plugins 查看工具审批。"
              )
            ]
          }));
        }
      },
      runResearch: () => {
        const active = currentTask();
        if (!active) return;
        if (active.auto.running) {
          notify("全自动已占用当前 run；先暂停并停止，再手动推进");
          return;
        }
        appendToCurrent((task) => appendAutoSkill({
          ...task,
          mode: task.mode === "auto" ? "auto" : "research",
          stage: Math.max(task.stage, 1),
          completedStages: Array.from(new Set([...task.completedStages, 0])),
          autoStages: stagesDone(task.autoStages, [0]),
          coverage: { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 },
          budget: { ...task.budget, used: Math.min(task.budget.total, task.budget.used + 4) },
          gates: gate(gate(task.gates, "Q0", "pass", "12 spans / 2 gaps 已记录（演示数据）"), "G1", "needs_human", "2 个候选假设等待收敛"),
          evidence: withEvidence(
            withEvidence(
              withEvidence(task.evidence, {
                id: "GAP-001",
                kind: "gap",
                status: "open",
                text: "湿热循环后的配对定量对照缺失。",
                scope: "S1/perovskite",
                refs: ["SPAN-021"],
                note: "4 篇来源中只有 2 篇报告 T80。"
              }),
              {
                id: "CAND-H1",
                kind: "hypothesis",
                status: "candidate",
                text: "双分子钝化层降低界面缺陷密度 → 延长 T80。",
                scope: "S2/perovskite",
                refs: ["SPAN-014", "SPAN-021"]
              }
            ),
            {
              id: "CAND-H2",
              kind: "hypothesis",
              status: "candidate",
              text: "疏水性而非缺陷密度是湿热稳定性的主因。",
              scope: "S2/perovskite",
              refs: ["SPAN-009"]
            }
          ),
          messages: [
            ...task.messages,
            message("agent", "**扩展检索完成（演示数据）**\n\n- 3 条全文 / 1 条摘要-only\n- 12 个可定位 span\n- 新增 2 条 gap", sourcesCard()),
            message("agent", "### 证据边界\n\n- 证据足够支撑假设\n- 还不足以支撑 claim\n\n> 可以选一个候选进入 S4，但不能跳过人工门。", ideaCard())
          ]
        }, "literature-brief", "检索完成，按需复核来源、全文与 span。"));
        notify("检索完成（演示数据）：12 spans / 2 gaps");
      },
      designExperiment: () => {
        const active = currentTask();
        if (!active) return;
        if (active.auto.running) {
          notify("全自动已占用当前 run；先暂停并停止，再手动推进");
          return;
        }
        if (denyReadOnly(active, "设计实验")) return;
        if (active.protocol) {
          notify("当前任务已有协议草案；请直接冻结或检查");
          return;
        }
        if (active.coverage.spans === 0) {
          notify("先完成检索并形成 gap/hypothesis，再进入实验设计");
          return;
        }
        appendToCurrent((task) => appendAutoSkill({
          ...task,
          mode: "experiment",
          stage: Math.max(task.stage, 2),
          completedStages: Array.from(new Set([...task.completedStages, 0, 1])),
          autoStages: stagesDone(task.autoStages, [0, 1]),
          protocol: task.protocol ?? { ...DEFAULT_PROTOCOL, controls: [...DEFAULT_PROTOCOL.controls] },
          gates: gate(gate(task.gates, "G1", "pass", "演示推进；真实 G1 由 CLI flow g1 决定"), "G2", "needs_human", "协议等待人工冻结"),
          budget: { ...task.budget, used: Math.min(task.budget.total, task.budget.used + 2) },
          messages: [
            ...task.messages,
            message(
              "agent",
              "**H1 已送入 S4 设计**\n\n- 主指标：T80 / 初始 PCE\n- 对照：未钝化 / 单分子钝化\n- seeds：3\n\n> 下一步是人工冻结协议，而不是直接运行。",
              protocolCard()
            )
          ]
        }, "protocol-review", "协议草案已生成，按需检查 baseline、指标、对照与 seeds。"));
        notify("已生成协议草案；等待 G2 冻结");
      },
      freezeProtocol: () => {
        const task = currentTask();
        if (!task) return;
        if (!task.protocol) {
          notify("没有可冻结的协议草案；先送入实验设计");
          return;
        }
        mutateTask(task.id, (item) => ({
          ...item,
          gates: gate(item.gates, "G2", "needs_human", "G2 等待人工在终端冻结；网页不冻结协议"),
          messages: [
            ...item.messages,
            message(
              "agent",
              "G2 · 待人工冻结。协议保持待定，主指标、对照与 seeds 尚未锁定。请在终端核对后执行：\n\n```bash\n" +
                protocolFreezeCommand() +
                "\n```\n\n" +
                CLI_ONLY_NOTE
            )
          ]
        }));
        notify("G2 保持待人工冻结；已在会话中给出 CLI 命令");
      },
      runExperiment: () => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.running) {
          notify("全自动运行中；手动 run 前请先暂停并停止");
          return;
        }
        if (task.evaluation.hiddenAccessCount > 0) {
          notify("held-out 已消耗；同一任务不能重新评估。请新建任务或新协议");
          return;
        }
        if (task.evidence.some((item) => item.kind === "claim" && item.status === "signed")) {
          notify("已有已签 claim；重跑会覆盖签名。请新建任务或新协议");
          return;
        }
        if (!task.protocolFrozen) {
          notify("先冻结协议（G2），再运行；系统不会跳过门禁");
          return;
        }
        if (denyReadOnly(task, "运行实验")) return;
        if (
          !requestPermission(task, {
            kind: "run_experiment",
            title: "运行实验并封存 EA",
            detail: "将以当前冻结协议运行 3 seeds，并生成一个待签 claim；不会自动签名。"
          })
        ) {
          return;
        }
        mutateTask(task.id, (item) => appendAutoSkill({
          ...item,
          stage: Math.max(item.stage, 4),
          status: "blocked",
          completedStages: Array.from(new Set([...item.completedStages, 2, 3])),
          autoStages: stagesDone(item.autoStages, [2, 3]),
          run: {
            id: "RUN-014",
            dataset: "perovskite / 本地 fixture",
            seeds: 3,
            metric: "T80 (h)",
            mean: 412,
            baseline: 286,
            ea: "EA-7c41",
            status: "EA sealed · claim unsigned"
          },
          evaluation: {
            ...item.evaluation,
            baselineReproduced: item.evaluation.baselineReproduced ?? 286,
            validationSelections: item.evaluation.validationSelections + 1,
            trainCost: item.evaluation.trainCost ?? 2.4,
            evalRuleHash: item.evaluation.evalRuleHash === "—" ? "sha256:7c41e2" : item.evaluation.evalRuleHash
          },
          gates: gate(gate(item.gates, "S5", "pass", "EA 已封存（演示数据）"), "G5", "blocked", "claim 未签；closure 未运行"),
          evidence: withEvidence(item.evidence, {
            id: "CLAIM-014",
            kind: "claim",
            status: "unsigned",
            text: "双分子钝化层在湿热条件下延长 T80，但效应量仍需独立复现。",
            scope: "S5/perovskite",
            refs: ["EA-7c41", "SPAN-014", "SPAN-021"],
            note: "claim 只能由作者/PI 签署；当前为待签状态。"
          }),
          budget: { ...item.budget, used: Math.min(item.budget.total, item.budget.used + 6) },
          messages: [
            ...item.messages,
            message("agent", "**RUN-014 完成**\n\n- 3 seeds · EA 已封存\n- 数值来自本地 fixture\n\n> 不冒充真实材料实验。", runCard()),
            message("agent", "现在停在 claim 人工门。\n\n- 未签 claim 之前，写作与导出保持 pending\n- 系统不会自动生成结论", claimGateCard("needs_human"))
          ]
        }, "evidence-audit", "EA 已封存，按需检查 span→claim→EA 边界。"));
        notify("EA 已封存（演示数据）；claim 等待人工签署");
      },
      signClaim: () => {
        const task = currentTask();
        if (!task) return;
        const claim = task.evidence.find(
          (item) => item.kind === "claim" && (item.status !== "signed" || item.origin === "demo")
        );
        // Opening a real panel is the feedback a click owes the user. The old behavior only
        // appended a chat message plus a 2.8s toast, which read as "nothing happened".
        mutateTask(task.id, (item) => ({
          ...item,
          auto: { ...item.auto, paused: true, gate: "claim", gateApproved: false },
          gates: gate(item.gates, "G5", "blocked", "claim 待人工签署；closure 未运行"),
          messages: [
            ...item.messages,
            message(
              "agent",
              claim
                ? "已打开 Q0 / S5b 人工门面板。浏览器不产生签名：面板里可以复制 CLI 人签命令、导入已签署的 claim.json，静态 demo 还能预览签署后的界面状态。\n\n" +
                    claimSignatureLabel(claim).detail
                : "已打开 Q0 / S5b 人工门面板。当前没有待签 claim；先运行 pipeline 生成 RunCapsule / EA 与 claim draft。",
              claim ? claimGateCard("needs_human", claim) : undefined
            )
          ]
        }));
        set((state) => ({ ui: { ...state.ui, claimGateOpen: true, paletteOpen: false } }));
      },
      closeClaimGate: () => {
        set((state) => ({ ui: { ...state.ui, claimGateOpen: false } }));
      },
      previewDemoClaim: () => {
        if (!__STATIC_ONLY__) {
          notify("演示态预览只在静态 demo 构建可用；产品工作台请导入 CLI 签署产物");
          return;
        }
        const task = currentTask();
        if (!task) return;
        const claim = task.evidence.find((item) => item.kind === "claim" && item.status === "unsigned");
        if (!claim) {
          notify("没有待签署的 claim；先运行 pipeline 生成 EA 与 claim draft");
          return;
        }
        mutateTask(task.id, (item) => ({
          ...item,
          evidence: item.evidence.map((entry) =>
            entry.id === claim.id
              ? {
                  ...entry,
                  status: "signed" as const,
                  origin: "demo" as const,
                  note: "演示态预览：浏览器未产生签名；未写入证据层，closure 与导出签名仍需 CLI 人签。"
                }
              : entry
          ),
          gates: gate(item.gates, "G5", "blocked", "演示态预览：claim 无真实签名，closure 与导出签名仍需 CLI 人签"),
          messages: [
            ...item.messages,
            message(
              "agent",
              "**演示态预览 · 非真实签署**\n\n- claim 状态按演示流程推进，便于查看 S8–S16 的界面\n- 浏览器没有产生签名，也没有写入证据层\n- G5 / closure 仍为 blocked，导出签名仍需 `closure sign`\n\n> 数值与状态均为演示数据，不构成研究证据。",
              claimGateCard("needs_human", { ...claim, status: "signed", origin: "demo" })
            )
          ]
        }));
        set((state) => ({
          ui: { ...state.ui, claimGateOpen: false },
          toast: { id: uid("toast"), text: "已进入演示态预览（未产生真实签名）" }
        }));
      },
      resetDemoClaim: () => {
        const task = currentTask();
        if (!task) return;
        const demo = task.evidence.find((item) => item.kind === "claim" && item.origin === "demo");
        if (!demo) {
          notify("当前没有演示态预览可撤销");
          return;
        }
        mutateTask(task.id, (item) => ({
          ...item,
          evidence: item.evidence.map((entry) =>
            entry.id === demo.id
              ? {
                  ...entry,
                  status: "unsigned" as const,
                  origin: undefined,
                  note: "claim 只能由作者/PI 签署；当前为待签状态。"
                }
              : entry
          ),
          gates: gate(item.gates, "G5", "blocked", "claim 待人工签署；closure 未运行"),
          messages: [
            ...item.messages,
            message(
              "agent",
              "已撤销演示态预览：claim 回到待人工签署，G5 保持 blocked。",
              claimGateCard("needs_human", { ...demo, status: "unsigned", origin: undefined })
            )
          ]
        }));
        set((state) => ({
          ui: { ...state.ui, claimGateOpen: false },
          toast: { id: uid("toast"), text: "已撤销演示态预览；claim 回到待签" }
        }));
      },
      importSignedClaim: (record, scopeWarning) => {
        const task = currentTask();
        if (!task) return;
        const claim = task.evidence.find(
          (item) => item.kind === "claim" && (item.status !== "signed" || item.origin === "demo")
        );
        if (!claim) {
          notify("没有待回填的 claim；当前产物已处于已签状态");
          return;
        }
        const note = [
          `导入自 ${record.claimId} · status=${record.status}`,
          `人签理由：${record.humanReason}`,
          ...(scopeWarning ? [scopeWarning] : []),
          ...(record.warnings.length ? [`产物警告：${record.warnings[0]}`] : [])
        ].join("；");
        mutateTask(task.id, (item) => ({
          ...item,
          evidence: item.evidence.map((entry) =>
            entry.id === claim.id
              ? {
                  ...entry,
                  status: "signed" as const,
                  origin: "cli-import" as const,
                  text: record.statement,
                  scope: record.scope,
                  refs: record.evidenceRefs.length ? record.evidenceRefs : entry.refs,
                  note
                }
              : entry
          ),
          gates: gate(item.gates, "G5", "blocked", "已导入 CLI claim.json；closure 与导出签名仍需 CLI 人签"),
          messages: [
            ...item.messages,
            message(
              "agent",
              "**已导入 CLI 签署产物**\n\n- 读取 `claim/claim.json`，未代签、未回写证据层\n- claim_id / statement / scope / human_reason 均已校验\n" +
                (scopeWarning ? `- 注意：${scopeWarning}\n` : "") +
                "\n> 后续 closure 与导出签名仍由本地 CLI 完成。",
              claimGateCard("pass", { ...claim, status: "signed", origin: "cli-import" })
            )
          ]
        }));
        set((state) => ({
          ui: { ...state.ui, claimGateOpen: false },
          toast: { id: uid("toast"), text: "已导入 claim.json；工作台只读取，未代签" }
        }));
      },
      prepareWriting: () => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.running) {
          notify("全自动运行中；生成写作槽位前请先暂停并停止");
          return;
        }
        const signed = task.evidence.some((item) => item.kind === "claim" && item.status === "signed");
        mutateTask(task.id, (item) => {
          const claimSigned = item.evidence.some((entry) => entry.kind === "claim" && entry.status === "signed");
          const card = writingCard({ claimSigned, protocolFrozen: item.protocolFrozen });
          const bound = card.type === "writing" ? card.slots.filter((slot) => slot.status === "bound").length : 0;
          return appendAutoSkill({
            ...item,
            mode: "writing",
            stage: Math.max(item.stage, 6),
            messages: [
              ...item.messages,
              message(
                "agent",
                claimSigned
                  ? `已按当前证据刷新写作槽位：${bound}/6 已绑定；引用仍待 closure，导出保持锁定。`
                  : "已生成写作槽位：结果、主图与摘要保持 locked，因为还没有已签 claim。可以先回到调研或实验补齐证据。",
                card
              )
            ]
          }, "paper-slots", "写作槽位已生成，按需检查绑定与 locked 槽位。");
        });
        notify(signed ? "写作槽位已刷新（演示数据）" : "写作槽位已生成；结果槽仍 locked");
      },
      submitEvaluation: () => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.running) {
          notify("全自动运行中：先停止再提交独立评估");
          return;
        }
        if (denyReadOnly(task, "提交 held-out 评估")) return;
        if (!task.run) {
          notify("先完成 S5 run 并封存 EA，再提交独立评估");
          return;
        }
        if (task.evaluation.hiddenAccessCount > 0) {
          notify("held-out 已消耗一次；一次运行只允许一次最终评估");
          return;
        }
        mutateTask(task.id, (item) => ({
          ...item,
          evaluation: { ...item.evaluation, hiddenAccessCount: 1, audit: "pending" },
          messages: [
            ...item.messages,
            message("system", "已提交独立评估（演示数据）：held-out 只读一次；评估结果不回流到改进阶段。")
          ]
        }));
        notify("已提交独立评估（演示数据）");
      },
      runEvaluationAudit: () => {
        const task = currentTask();
        if (!task) return;
        const evaluation = task.evaluation;
        if (evaluation.hiddenAccessCount === 0) {
          notify("先提交独立评估，再运行过程审计");
          return;
        }
        if (evaluation.audit !== "pending") {
          notify("本轮过程审计已完成");
          return;
        }
        const risks: string[] = [];
        if (evaluation.validationSelections > 10) {
          risks.push(`验证选择 ${evaluation.validationSelections} 次，存在验证集过拟合风险`);
        }
        if (evaluation.evalRuleHash === "—") {
          risks.push("评价规则尚未冻结");
        }
        if (evaluation.baselineReproduced === null) {
          risks.push("复现基线未登记");
        }
        const flagged = risks.length > 0;
        mutateTask(task.id, (item) => ({
          ...item,
          evaluation: { ...item.evaluation, audit: flagged ? "flagged" : "pass" },
          messages: [
            ...item.messages,
            message(
              "system",
              flagged
                ? `过程审计（演示数据）标记风险：${risks.join("；")}。结果保留，但不应作为可信改进。`
                : "过程审计（演示数据）通过：未发现测试泄漏、规则改写或异常验证选择。"
            )
          ]
        }));
        notify(flagged ? "审计发现风险，已标记" : "过程审计通过（演示数据）");
      },
      createSkill: (input) => {
        const name = input.name.trim();
        if (!name) {
          notify("Skill 名称不能为空");
          return null;
        }
        const slug = name
          .toLowerCase()
          .replace(/\s+/g, "-")
          .replace(/[^\w\u4e00-\u9fa5-]/g, "")
          .replace(/-+/g, "-")
          .replace(/^-|-$/g, "") || uid("skill");
        const id = slug.startsWith("skill-") ? slug : `skill-${slug}`;
        if (get().skills.some((skill) => skill.id === id || skill.name === name)) {
          notify("已有同名 Skill；换一个名称");
          return null;
        }
        const tools = input.tools.map((tool) => tool.trim()).filter(Boolean);
        const skill: Skill = {
          id,
          name,
          description: input.description.trim() || "自定义只读检查技能",
          instructions: input.instructions.trim() || "只读取当前会话状态并给出检查结果。",
          tools: tools.length ? tools : ["session.inspect"],
          activation: "manual",
          source: "custom",
          version: "0.1.0",
          createdAt: isoNow()
        };
        set((state) => ({ skills: [...state.skills, skill] }));
        notify(`Skill 已创建：${name}`);
        return skill;
      },
      importSkills: (incoming) => {
        const existing = get().skills;
        const fresh = incoming.filter(
          (skill) =>
            !existing.some(
              (item) => item.id === skill.id || item.name.toLowerCase() === skill.name.toLowerCase()
            )
        );
        if (!fresh.length) {
          notify("没有可导入的新 Skill；同名项已跳过");
          return;
        }
        set((state) => ({ skills: [...state.skills, ...fresh] }));
        notify(`已导入 ${fresh.length} 个 Skill；默认停用，检查后启用`);
      },
      setSkillActivation: (id, activation) => {
        const skill = get().skills.find((item) => item.id === id);
        if (!skill) return;
        if (activation === "auto" && skill.source !== "builtin") {
          notify("导入或自定义 Skill 只能手动调用；不能自动加载");
          return;
        }
        set((state) => ({
          skills: state.skills.map((item) =>
            item.id === id ? { ...item, activation } : item
          )
        }));
        const label = activation === "auto" ? "按需" : activation === "manual" ? "手动" : "停用";
        notify(`${skill.name} 已设为${label}`);
      },
      deleteSkill: (id) => {
        const skill = get().skills.find((item) => item.id === id);
        if (!skill) return;
        if (skill.source === "builtin") {
          notify("内置 Skill 不能删除；可以停用");
          return;
        }
        set((state) => ({ skills: state.skills.filter((item) => item.id !== id) }));
        notify(`Skill 已删除：${skill.name}`);
      },
      invokeSkill: (id, note) => {
        const state = get();
        const skill = state.skills.find((item) => item.id === id);
        if (!skill) {
          notify("未找到 Skill");
          return;
        }
        if (skill.activation === "off") {
          notify("该 Skill 已停用；先在 Skills 面板设为按需或手动");
          return;
        }
        if (state.ui.welcomeOpen) {
          const workspace =
            state.workspaces.find((item) => item.id === state.activeWorkspaceId) ?? state.workspaces[0];
          if (!workspace) {
            notify("没有可用工作区");
            return;
          }
          const base = buildTask({
            name: skill.name,
            goal: skill.description,
            domain: "其他",
            mode: "research",
            workspaceId: workspace.id,
            access: state.ui.draftAccess,
            profileId: state.ui.draftProfileId
          });
          const call = skillCallFor(base, skill, note);
          const task: ResearchTask = {
            ...base,
            messages: [
              message("system", `SKILL / ${skill.id} · v${skill.version} · 只读检查；不调用外部工具。`),
              message("user", call.command),
              message("agent", call.text, call.card)
            ]
          };
          set((current) => ({
            tasks: [task, ...current.tasks],
            selectedTaskId: task.id,
            activeWorkspaceId: workspace.id,
            ui: {
              ...current.ui,
              welcomeOpen: false,
              skillsOpen: false,
              sidebarOpen: false,
              contextOpen: false,
              permissionRequest: null,
              expandedWorkspaces: { ...current.ui.expandedWorkspaces, [workspace.id]: true }
            }
          }));
          notify(`Skill 已调用：${skill.name}`);
          return;
        }
        const task = currentTask();
        if (!task) return;
        if (task.auto.running) {
          notify("全自动运行中：先暂停并停止再调用 Skill");
          return;
        }
        const call = skillCallFor(task, skill, note);
        mutateTask(task.id, (item) => ({
          ...item,
          budget: { ...item.budget, used: Math.min(item.budget.total, item.budget.used + 1) },
          messages: [
            ...item.messages,
            message("user", call.command),
            message("agent", call.text, call.card)
          ]
        }));
        set((current) => ({ ui: { ...current.ui, skillsOpen: false } }));
        notify(`Skill 已调用：${skill.name}`);
      },
      runReviewPack: async () => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.running) {
          notify("全自动运行中：先暂停并停止再运行审阅包");
          return;
        }
        let agents: ReviewAgent[] = [];
        try {
          const snapshot = await loadCustomAgents();
          agents = snapshot.data.agents
            .filter((agent) => agent.enabled)
            .map((agent) => ({ name: agent.name, checks: agent.checks }));
        } catch {
          agents = [];
        }
        const latest = get().tasks.find((item) => item.id === task.id);
        if (!latest) return;
        const pack = buildReviewPack(latest, agents);
        mutateTask(latest.id, (item) => ({
          ...item,
          reviewPack: pack,
          messages: [
            ...item.messages,
            message("agent", "**审阅包完成** · advisory only", {
              type: "review-pack",
              ...pack
            })
          ]
        }));
        notify(`审阅包完成：${pack.summary}`);
      },
      startLiveRun: async (source, taskType, flowMode, options) => {
        const task = currentTask();
        if (!task) return;
        if (task.access === "read_only") {
          notify("只读模式不启动本地 API 运行");
          return;
        }
        if (task.auto.running) {
          notify("全自动运行中：先暂停并停止再启动 API 运行");
          return;
        }
        if (task.evidence.some((item) => item.kind === "claim" && item.status === "signed")) {
          notify("claim 已签：API 重跑会使旧签名失效，请先走 maintenance");
          return;
        }
        if (task.messages.some((item) => item.card?.type === "runtime-run" && (item.card.status === "queued" || item.card.status === "running"))) {
          notify("已有本地 API 运行进行中");
          return;
        }
        const chosen = source ?? defaultRuntimeSource(task);
        const chosenType = taskType ?? "auto";
        const topic = (task.goal || task.name).trim().slice(0, 500);
        if (topic.length < 2) {
          notify("任务主题太短，无法启动 pipeline");
          return;
        }
        const isZh = /[\u4e00-\u9fff]/.test(topic);
        const note = chosen === "fixture"
          ? "fixture 演示语料：只验证流程与证据边界，不是科学结论，也不能引用。"
          : chosen === "openalex"
            ? "OpenAlex 只返回摘要线索；未取得全文的来源不会生成 span，也不会产生 claim。"
            : "冻结 CC-BY 真实正文；若主题不在语料范围内，会明确返回证据不足。";
        const initial: Card = {
          type: "runtime-run",
          jobId: "",
          status: "queued",
          events: 0,
          source: chosen,
          taskType: chosenType,
          dataset: options?.runDataset || undefined,
          warnings: [],
          artifacts: [],
          evidencePackages: [],
          note: chosenType === "auto" ? `${note} 任务类型由 runtime 自动路由。` : `${note} 任务类型：${chosenType}。`,
        };
        const pendingMessage = message("agent", `本地 API 任务已提交：${topic}\n\n${initial.note}`, initial);
        mutateTask(task.id, (item) => ({
          ...item,
          evidencePackages: [],
          runtime: { source: chosen, appliedAt: new Date().toISOString() },
          messages: [
            ...item.messages.filter(
              (entry) =>
                !(
                  entry.role === "system" &&
                  entry.text.startsWith("STATIC WORKSPACE")
                )
            ),
            message(
              "system",
              "RUNTIME WORKSPACE · 本地 API pipeline；claim/closure/export 仍需离线人工签署。"
            ),
            pendingMessage
          ]
        }));
        const messageId = pendingMessage.id;
        const updateCard = (patch: Partial<Extract<Card, { type: "runtime-run" }>>) => {
          mutateTask(task.id, (item) => {
            const completedStages = new Set(item.completedStages);
            const messages = item.messages.map((entry) => {
              if (entry.id !== messageId || entry.card?.type !== "runtime-run") return entry;
              const incoming = patch.eventLog ?? [];
              const merged = [...(entry.card.eventLog ?? []), ...incoming]
                .filter(
                  (event, index, list) =>
                    list.findIndex((item) => item.seq === event.seq) === index
                )
                .slice(-40);
              for (const event of merged) {
                if (event.type !== "step_end" && event.type !== "stage_end") continue;
                const index = runtimeStageIndex(event.stage);
                if (index >= 0) completedStages.add(index);
              }
              return {
                ...entry,
                card: {
                  ...entry.card,
                  ...patch,
                  eventLog: merged.length ? merged : undefined
                }
              };
            });
            return {
              ...item,
              completedStages: [...completedStages].sort((a, b) => a - b),
              runtime: {
                source: item.runtime?.source ?? chosen,
                runId: patch.runId ?? item.runtime?.runId,
                appliedAt: item.runtime?.appliedAt ?? new Date().toISOString()
              },
              messages
            };
          });
        };
        let lastSeq = 0;
        let pollErrors = 0;
        let lastExecStats: { counts?: Record<string, number>; faces?: number } | undefined;
        const poll = async (jobId: string) => {
          try {
            const [job, eventBody, execBody] = await Promise.all([
              getRun(jobId),
              loadRunEvents(jobId, lastSeq).catch(() => null),
              loadExecStats().catch(() => null)
            ]);
            if (execBody?.dispatch_stats) {
              lastExecStats = {
                counts: execBody.dispatch_stats.counts,
                faces: execBody.faces?.length
              };
            }
            const events = eventBody?.events ?? [];
            if (events.length) lastSeq = events[events.length - 1].seq;
            const last = events[events.length - 1];
            const lastStage = [...events]
              .reverse()
              .find((entry) => entry.stage && entry.type !== "stage_skip")?.stage;
            const finished = job.status === "completed" || job.status === "failed";
            const status = (job.status === "completed" && job.result?.status === "failed"
              ? "failed"
              : ["queued", "running", "completed", "failed"].includes(job.status)
                ? job.status
                : "running") as "queued" | "running" | "completed" | "failed";
            let artifacts: Awaited<ReturnType<typeof loadRunArtifacts>> = [];
            if (finished) {
              // An interrupted artifact fetch must not turn a completed run into a failed one.
              try {
                artifacts = await loadRunArtifacts(jobId);
              } catch {
                artifacts = [];
              }
            }
            pollErrors = 0;
            updateCard({
              jobId,
              status,
              events: job.events_count,
              runId: job.result?.run_id,
              jobDir: job.result?.job_dir,
              fixtureMode: job.result?.fixture_mode,
              verdictBus: job.verdict_bus,
              execStats: lastExecStats,
              route: job.result?.route,
              taskStatus: job.result?.status,
              flowMode: job.result?.flow_mode,
              stoppedAt: job.result?.stopped_at,
              gates: job.result?.gates,
              ...(lastStage ? { stage: lastStage } : {}),
              lastEvent: last?.message ?? undefined,
              eventLog: events.map((event) => ({
                seq: event.seq,
                type: event.type,
                stage: event.stage,
                message: event.message,
                ts: event.ts
              })),
              warnings: job.result?.warnings ?? [],
              artifacts,
              evidencePackages: job.result?.evidence_packages ?? [],
              supportAudit: job.result?.support_audit,
              failure:
                job.result?.failure &&
                Object.keys(job.result.failure).length > 0
                  ? job.result.failure
                  : undefined,
              error: job.error || job.result?.error || undefined,
            });
            if (finished && job.result?.evidence_packages?.length) {
              mutateTask(task.id, (item) => ({
                ...item,
                evidencePackages: job.result?.evidence_packages ?? item.evidencePackages ?? [],
              }));
            }
            if (finished && job.result?.status === "failed") {
              const failure = job.result?.failure;
              notify(
                `任务失败：${failure?.error_type || "unknown"}${
                  failure?.suggested_action ? ` · ${failure.suggested_action}` : ""
                }`
              );
            } else if (finished && status === "failed") {
              notify(`本地 API pipeline 失败：${job.error || "unknown"}`);
            } else if (finished) {
              const literatureArtifact = artifacts.find((artifact) => artifact.path.endsWith("literature.json"));
              if (literatureArtifact) {
                try {
                  const literature = await loadRunArtifactJson<{
                    spans?: unknown[];
                    coverage?: { sources_found?: number; spans_extracted?: number; gaps?: unknown[] };
                  }>(literatureArtifact.url);
                  const coverage = literature?.coverage ?? {};
                  mutateTask(task.id, (item) => ({
                    ...item,
                    coverage: {
                      sources: typeof coverage.sources_found === "number" ? coverage.sources_found : item.coverage.sources,
                      spans: typeof coverage.spans_extracted === "number"
                        ? coverage.spans_extracted
                        : Array.isArray(literature?.spans)
                          ? literature.spans.length
                          : item.coverage.spans,
                      gaps: Array.isArray(coverage.gaps) ? coverage.gaps.length : item.coverage.gaps,
                      abstractOnly: item.coverage.abstractOnly
                    }
                  }));
                } catch {
                  // Coverage stays at its previous value if the artifact cannot be read.
                }
              }
              const loadLoopArtifact = async (suffix: string): Promise<unknown> => {
                const artifact = artifacts.find((item) => item.path.endsWith(suffix));
                if (!artifact) return undefined;
                try {
                  return await loadRunArtifactJson<unknown>(artifact.url);
                } catch {
                  return undefined;
                }
              };
              const [
                ideaArtifact,
                experimentArtifact,
                paperArtifact,
                figureArtifact,
                registryArtifact,
                closureArtifact,
                loopCapsuleArtifact
              ] = await Promise.all([
                loadLoopArtifact("idea.json"),
                loadLoopArtifact("experiment.json"),
                loadLoopArtifact("paper.json"),
                loadLoopArtifact("figure.manifest.json"),
                loadLoopArtifact("claim-registry.json"),
                loadLoopArtifact("closure-report.json"),
                loadLoopArtifact("loop-capsule.json")
              ]);              mutateTask(task.id, (item) => ({
                ...item,
                runtimeLoop: compactRuntimeLoop({
                  idea: ideaArtifact,
                  experiment: experimentArtifact,
                  paper: paperArtifact,
                  figure: figureArtifact,
                  claimRegistry: registryArtifact,
                  closure: closureArtifact,
                  loopCapsule: loopCapsuleArtifact,
                  observationId: job.result?.observation_id,
                  activePolicyId: job.result?.active_policy?.policy_id,
                  appliedPolicy: job.result?.active_policy,
                  activeLease: job.result?.active_s5_lease
                })
              }));
              const demoArtifact = artifacts.find((artifact) => artifact.path.endsWith("demo.json"));              if (demoArtifact) {
                try {
                  const demo = await loadRunArtifactJson<RuntimeDemo>(demoArtifact.url);
                  const latest = get().tasks.find((entry) => entry.id === task.id) ?? task;
                  mutateTask(task.id, (item) => ({
                    ...item,
                    ...applyRuntimeSnapshot(latest, demo, chosen),
                    messages: [
                      ...item.messages,
                      message(
                        "system",
                        `RUNTIME SNAPSHOT · ${demo.run_id ?? "run"} · ${note} 证据链与门禁已从产物回填；claim 仍只能在离线签署。`
                      )
                    ]
                  }));
                  notify("runtime 产物已回填到证据链；claim 仍需离线人签");
                } catch {
                  notify("pipeline 完成，但 demo.json 回填失败；可直接打开产物核对");
                }
              } else {
                notify("pipeline 完成；产物已附在会话卡片");
              }
            } else {
              window.setTimeout(() => void poll(jobId), 900);
            }
            if (finished) return;
          } catch (error) {
            pollErrors += 1;
            if (pollErrors <= 3) {
              window.setTimeout(() => void poll(jobId), 1200);
              return;
            }
            const latestCard = [...(get().tasks.find((entry) => entry.id === task.id)?.messages ?? [])]
              .reverse()
              .find((entry) => entry.card?.type === "runtime-run")?.card;
            if (
              latestCard?.type === "runtime-run"
              && (latestCard.status === "completed" || latestCard.status === "failed")
            ) {
              notify("本地 API 轮询中断；可手动刷新产物列表");
              return;
            }
            updateCard({ status: "failed", error: error instanceof Error ? error.message : String(error) });
            notify("本地 API 轮询失败");
          }
        };
        try {
          const job = await createRun({
            topic,
            task_type: chosenType,
            language: isZh ? "zh" : "en",
            venue_type: isZh ? "zh_core_journal" : "en_conference",
            max_sources: 6,
            real_corpus: chosen === "real_corpus",
            local_corpus: chosen === "local",
            openalex: chosen === "openalex",
            planner: "gateway",
            run_dataset: options?.runDataset || "",
            run_seeds: options?.runSeeds ?? 3,
            flow_mode: flowMode ?? "review",
            g1_decision_file: options?.g1DecisionFile?.trim() || "",
            protocol_file: options?.protocolFile?.trim() || "",
            claim_file: options?.claimFile?.trim() || "",
            bibliography_file: options?.bibliographyFile?.trim() || "",
            run_dir: options?.runDir?.trim() || "",
          });
          updateCard({ jobId: job.job_id, status: "queued" });
          let stream: EventSource | null = null;
          try {
            stream = new EventSource(
              runtimeUrl(
                `/api/runs/${encodeURIComponent(job.job_id)}/events/stream?after=0`
              )
            );
            stream.onmessage = (message) => {
              try {
                const event = JSON.parse(message.data) as RunEvent;
                updateCard({
                  events: Math.max(0, Number(event.seq) || 0),
                  lastEvent: event.message,
                  ...(event.stage ? { stage: event.stage } : {}),
                  eventLog: [
                    {
                      seq: event.seq,
                      type: event.type,
                      stage: event.stage,
                      message: event.message,
                      ts: event.ts
                    }
                  ]
                });
              } catch {
                /* ignore malformed SSE frames */
              }
            };
            stream.onerror = () => {
              // EventSource is closed here, so the browser will not reconnect. The poll loop
              // still carries every event via loadRunEvents(lastSeq); say so instead of letting
              // the live indicator silently degrade.
              notify("实时事件通道断开；已由 900ms 轮询继续同步，产物不会丢失");
              stream?.close();
              stream = null;
            };
          } catch {
            stream = null;
          }
          try {
            await poll(job.job_id);
          } finally {
            stream?.close();
            stream = null;
          }
        } catch (error) {
          const detail = error instanceof Error ? error.message : String(error);
          // A static build disables the runtime at compile time; reporting it as
          // "start the runtime" misattributes a build-time limitation to the user.
          const staticDisabled = __STATIC_ONLY__ && detail.includes("runtime disabled in static build");
          updateCard({
            status: "failed",
            error: staticDisabled ? "静态演示构建不支持真实运行" : detail
          });
          notify(
            staticDisabled
              ? "当前是静态演示构建，runtime 在编译时已禁用；/live 需以非 static 模式重新构建前端"
              : "本地 API 启动失败：需要先运行 runtime"
          );
        }
      },
      confirmPermission: () => {
        const request = get().ui.permissionRequest;
        if (!request) return;
        const task = currentTask();
        if (!task || task.id !== request.taskId) {
          set((state) => ({ ui: { ...state.ui, permissionRequest: null } }));
          notify("任务已切换；权限请求已取消");
          return;
        }
        set((state) => ({ ui: { ...state.ui, permissionRequest: null } }));
        mutateTask(task.id, (item) => ({
          ...item,
          messages: [...item.messages, message("system", `已允许本次：${request.title}。`)]
        }));
        permissionBypass = true;
        try {
          switch (request.kind) {
            case "start_auto":
              get().actions.startAuto();
              break;
            case "step_auto":
              get().actions.stepAuto();
              break;
            case "run_experiment":
              get().actions.runExperiment();
              break;
            case "approve_candidate":
              get().actions.approveCandidate();
              break;
            case "approve_tool":
              get().actions.approveToolCall(request.targetId ?? "");
              break;
          }
        } finally {
          permissionBypass = false;
        }
      },
      cancelPermission: () => {
        const request = get().ui.permissionRequest;
        set((state) => ({ ui: { ...state.ui, permissionRequest: null } }));
        if (request) {
          const task = currentTask();
          if (task && task.id === request.taskId) {
            mutateTask(task.id, (item) => ({
              ...item,
              messages: [...item.messages, message("system", `已取消：${request.title}。没有执行任何高权限动作。`)]
            }));
          }
        }
        notify("已取消本次高权限动作");
      },
      startAuto: () => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.running) {
          notify(task.auto.paused ? "全自动已暂停；请使用继续或停止" : "全自动正在运行");
          return;
        }
        if (task.evaluation.hiddenAccessCount > 0) {
          notify("held-out 已消耗；同一任务不能再次启动改进运行");
          return;
        }
        if (task.evidence.some((item) => item.kind === "claim" && item.status === "signed")) {
          notify("已有已签 claim；启动全自动会重置证据。请新建任务或新协议");
          return;
        }
        if (denyReadOnly(task, "启动全自动")) return;
        if (
          !requestPermission(task, {
            kind: "start_auto",
            title: "启动受治理全自动",
            detail: "将连续执行 S1→META，并在 claim 人工门暂停；不会自动签署 claim，也不会解锁导出。"
          })
        ) {
          return;
        }
        startAutoInternal();
      },
      pauseAuto: () => {
        const task = currentTask();
        if (!task) return;
        if (!task.auto.running) {
          notify("全自动尚未启动");
          return;
        }
        if (task.auto.paused) {
          notify("已经暂停");
          return;
        }
        mutateTask(task.id, (item) => ({
          ...item,
          auto: { ...item.auto, paused: true },
          messages: [...item.messages, message("system", "已暂停。当前 run 与未完成阶段保留，可继续或单步。")]
        }));
        notify("已暂停");
      },
      resumeAuto: () => {
        const task = currentTask();
        if (!task) return;
        if (!task.auto.running) {
          notify("全自动尚未启动");
          return;
        }
        if (task.auto.gate === "claim" && !task.auto.gateApproved) {
          notify("claim 尚未签署，不能越过人工门");
          return;
        }
        mutateTask(task.id, (item) => {
          const autoStages = item.autoStages.map((stage, index) =>
            index === item.auto.index ? { ...stage, status: "running" as const } : stage
          );
          return {
            ...item,
            mode: "auto",
            status: "active",
            auto: { ...item.auto, paused: false, gate: "", gateApproved: false },
            autoStages,
            messages: [...item.messages, message("system", "继续运行；下一阶段开始。")]
          };
        });
        notify("继续运行");
      },
      autoStep: () => {
        appendToCurrent((task) => advanceAuto(task, false, get().skills));
      },
      stepAuto: () => {
        const task = currentTask();
        if (!task) return;
        if (task.auto.gate === "claim" && !task.auto.gateApproved) {
          notify("claim 尚未签署，无法单步越过人工门");
          return;
        }
        if (!task.auto.running) {
          if (task.evaluation.hiddenAccessCount > 0) {
            notify("held-out 已消耗；同一任务不能再次启动改进运行");
            return;
          }
          if (task.evidence.some((item) => item.kind === "claim" && item.status === "signed")) {
            notify("已有已签 claim；单步不会重置证据。请新建任务或新协议");
            return;
          }
          if (denyReadOnly(task, "单步执行全自动")) return;
          if (
            !requestPermission(task, {
              kind: "step_auto",
              title: "启动并执行一个自动阶段",
              detail: "将启动受治理全自动，只执行一个阶段后暂停；不会越过 claim 人工门。"
            })
          ) {
            return;
          }
          mutateTask(task.id, (item) => advanceAuto(startAutoTask(item), true, get().skills));
          notify("已启动并执行一个阶段，当前暂停");
          return;
        }
        mutateTask(task.id, (item) => advanceAuto({ ...item, mode: "auto", auto: { ...item.auto, paused: true } }, true, get().skills));
        notify("已单步执行；当前暂停");
      },
      stopAuto: () => {
        const task = currentTask();
        if (!task) return;
        mutateTask(task.id, (item) => ({
          ...item,
          status: "active",
          auto: { ...item.auto, running: false, paused: false, gate: "", gateApproved: false },
          autoStages: item.autoStages.map((stage) =>
            stage.status === "running" ? { ...stage, status: "pending" } : stage
          ),
          messages: [...item.messages, message("system", "全自动已停止。已封存证据保留；未签 claim 不会产生。")]
        }));
        notify("已停止全自动");
      },
      previewCandidate: () => {
        const task = currentTask();
        if (!task) return;
        if (task.evolution.candidate) {
          notify("已有自进化候选");
          return;
        }
        const candidate = makeCandidate();
        mutateTask(task.id, (item) => ({
          ...item,
          evolution: {
            status: "proposed",
            candidate,
            lease: "",
            history: [{ at: clockTime(), text: "静态预览生成候选；等待人工准入。" }]
          },
          messages: [
            ...item.messages,
            message("agent", "已生成一个静态自进化候选（演示数据）。它只改检索预算，不触碰 claim、gate 与导出。", {
              type: "evolution",
              candidate
            })
          ]
        }));
        notify("已生成自进化候选（演示数据）");
      },
      approveCandidate: () => {
        const task = currentTask();
        if (!task?.evolution.candidate || task.evolution.candidate.status !== "pending") return;
        if (denyReadOnly(task, "批准自进化候选")) return;
        if (
          !requestPermission(task, {
            kind: "approve_candidate",
            title: "演示：批准自进化候选",
            detail: "只在本地演示状态里标记；真实租约必须由 CLI 人工准入，claim / evidence / gate / export 仍不可写。"
          })
        ) {
          return;
        }
        mutateTask(task.id, (item) => {
          const candidate = item.evolution.candidate;
          if (!candidate) return item;
          const updated = { ...candidate, status: "active" as const, lease: "literature · 2 runs · scope S1/perovskite" };
          return {
            ...item,
            evolution: {
              status: "active",
              candidate: updated,
              lease: updated.lease,
              history: [...item.evolution.history, { at: clockTime(), text: "演示状态：本地标记为已准入；正式租约仍须 CLI 人工准入。" }]
            },
            messages: [
              ...item.messages,
              message("agent", "演示状态更新：候选在本地标记为 active，不代表真实租约；正式准入请执行 CLI 的 rsi admit。此动作不写 claim / EA / gate。", {
                type: "evolution",
                candidate: updated
              })
            ]
          };
        });
        notify("演示状态已更新；正式准入仍须 CLI 人签");
      },
      rejectCandidate: () => {
        const task = currentTask();
        if (!task?.evolution.candidate || task.evolution.candidate.status !== "pending") return;
        mutateTask(task.id, (item) => {
          const candidate = item.evolution.candidate;
          if (!candidate) return item;
          const updated = { ...candidate, status: "rejected" as const, lease: "未授予" };
          return {
            ...item,
            evolution: {
              status: "rejected",
              candidate: updated,
              lease: "",
              history: [...item.evolution.history, { at: clockTime(), text: "候选被拒绝；保留负结果，不进入 harness。" }]
            },
            messages: [...item.messages, message("system", "自进化候选被拒绝；负结果保留在 trace 中，不污染 incumbent。")]
          };
        });
        notify("候选已拒绝；负结果保留");
      },
      rollbackHarness: () => {
        const task = currentTask();
        if (!task?.evolution.candidate || task.evolution.candidate.status !== "active") return;
        mutateTask(task.id, (item) => {
          const candidate = item.evolution.candidate;
          if (!candidate) return item;
          const updated = { ...candidate, status: "rolled_back" as const, lease: "已回收" };
          return {
            ...item,
            evolution: {
              status: "rolled_back",
              candidate: updated,
              lease: "",
              history: [...item.evolution.history, { at: clockTime(), text: "租约撤销；harness 回滚到 incumbent v1。" }]
            },
            messages: [...item.messages, message("system", "harness 已回滚到 incumbent v1；候选与 trace 保留。")]
          };
        });
        notify("已撤销租约并回滚 harness");
      },
      saveModel: (settings, options) => {
        const task = currentTask();
        if (!task) return;
        mutateTask(task.id, (item) => ({ ...item, model: clampModel(settings) }));
        if (!options?.silent) notify("模型设置已应用（仅本地）");
      },
      registerPlugin: (plugin) => {
        const task = get().ui.welcomeOpen ? undefined : currentTask();
        const registered: Plugin = { ...plugin, id: uid("mcp"), status: "ready" };
        set((state) => ({
          plugins: [...state.plugins, registered],
          tasks: task
            ? state.tasks.map((item) =>
                item.id === task.id ? { ...item, plugins: [...item.plugins, registered.id] } : item
              )
            : state.tasks
        }));
        notify(task ? "MCP server 已登记并绑定当前会话；未发起真实连接" : "MCP server 已登记；创建会话后可启用");
      },
      togglePlugin: (id) => {
        const task = currentTask();
        if (!task) return;
        const enabled = task.plugins.includes(id);
        mutateTask(task.id, (item) => ({
          ...item,
          plugins: enabled ? item.plugins.filter((pluginId) => pluginId !== id) : [...item.plugins, id]
        }));
        notify(enabled ? "已在本任务停用连接器" : "已在本任务启用连接器（仍无真实连接）");
      },
      proposeToolCall: () => {
        const task = currentTask();
        if (!task) return;
        if (!task.plugins.includes("github")) {
          notify("GitHub MCP 未启用；请先在插件面板启用");
          return;
        }
        if (task.toolCalls.some((call) => call.status === "proposed")) {
          notify("已有待审批的工具调用");
          return;
        }
        const call: ToolCall = {
          id: uid("call"),
          pluginId: "github",
          server: "GitHub MCP",
          tool: "search_repositories",
          args: 'query="self-improving agent archive" · per_page=5 · read-only',
          status: "proposed",
          at: clockTime()
        };
        mutateTask(task.id, (item) => ({
          ...item,
          toolCalls: [call, ...item.toolCalls],
          messages: [
            ...item.messages,
            message("agent", "准备调用 GitHub MCP 的只读 search_repositories；工具结果进入会话前需要你逐次批准。", {
              type: "tool",
              server: call.server,
              tool: call.tool,
              status: call.status,
              args: call.args
            })
          ]
        }));
        notify("工具调用待批准 · 打开插件面板处理");
        openOverlay("pluginsOpen");
      },
      approveToolCall: (id) => {
        const task = currentTask();
        if (!task) return;
        const call = task.toolCalls.find((item) => item.id === id && item.status === "proposed");
        if (!call) return;
        if (denyReadOnly(task, "批准外部工具调用")) return;
        if (
          !requestPermission(task, {
            kind: "approve_tool",
            title: "批准外部工具调用",
            detail: `${call.server} · ${call.tool}：${call.args}。结果进入会话后仍视为 UNTRUSTED。`,
            targetId: id
          })
        ) {
          return;
        }
        const result = "2 repositories · 1 个 archive 相关仓库（演示数据，未联网）";
        mutateTask(task.id, (item) => ({
          ...item,
          toolCalls: item.toolCalls.map((entry) =>
            entry.id === id ? { ...entry, status: "approved", result } : entry
          ),
          messages: [
            ...item.messages,
            message(
              "agent",
              `工具结果已批准进入会话（演示数据）：${result}。外部内容一律视为 UNTRUSTED，不作为 claim 证据。`
            )
          ]
        }));
        notify("已批准本次只读调用（演示数据）");
      },
      denyToolCall: (id) => {
        const task = currentTask();
        if (!task) return;
        mutateTask(task.id, (item) => ({
          ...item,
          toolCalls: item.toolCalls.map((entry) => (entry.id === id ? { ...entry, status: "denied" } : entry)),
          messages: [...item.messages, message("system", "工具调用已被拒绝；没有产生外部结果。")]
        }));
        notify("已拒绝本次调用");
      },
      exportWorkspace: () => {
        const payload = {
          ...persistedSnapshot(get()),
          exportedAt: new Date().toISOString(),
          adapter: staticAdapter.label
        };
        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `research-agent-workspace-${new Date().toISOString().slice(0, 10)}.json`;
        link.click();
        URL.revokeObjectURL(url);
        notify("工作台状态已导出为 JSON");
      },
      resetWorkspace: () => {
        staticAdapter.clear();
        set({
          ...createSeedWorkspace(),
          preferences: { ...DEFAULT_PREFERENCES, shortcuts: { ...DEFAULT_SHORTCUTS } },
          ui: { ...defaultUI },
          toast: { id: uid("toast"), text: "已重置为示例工作区" }
        });
      },
      notify,
      dismissToast: () => set({ toast: null })
    }
  };
});

// Persistence pipeline (perf-critical): runtime polling / SSE can mutate task state
// many times per second, and each mutation used to pay for a full-workspace
// JSON.stringify plus a synchronous localStorage write. Two guards fix that:
//   1. reference short-circuit — persisted parts are only re-serialized when one of
//      their array/object references actually changed (zustand replaces references on
//      mutation, so unchanged parts are skipped outright);
//   2. trailing debounce — localStorage writes coalesce within 250ms while
//      folderStorage keeps its own 700ms queue.
const PERSIST_KEYS = [
  "version",
  "selectedTaskId",
  "activeWorkspaceId",
  "preferences",
  "workspaces",
  "tasks",
  "plugins",
  "skills",
  "memory",
  "archivedTaskIds"
] as const;

let lastSaved = "";
let saveTimer = 0;
let lastReferences: Record<string, unknown> = {};
let pendingSnapshot: PersistedWorkspace | null = null;

function persistNow(): void {
  if (!pendingSnapshot) return;
  const snapshot = pendingSnapshot;
  pendingSnapshot = null;
  const serialized = JSON.stringify(snapshot);
  if (serialized === lastSaved) return;
  lastSaved = serialized;
  staticAdapter.save(snapshot);
}

useWorkspaceStore.subscribe((state) => {
  const snapshot = persistedSnapshot(state);
  let changed = false;
  for (const key of PERSIST_KEYS) {
    if (lastReferences[key] !== snapshot[key]) {
      lastReferences[key] = snapshot[key];
      changed = true;
    }
  }
  if (!changed) return;
  pendingSnapshot = snapshot;
  folderStorage.queue(snapshot);
  if (saveTimer) window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    saveTimer = 0;
    persistNow();
  }, 250);
});

folderStorage.prime(persistedSnapshot(useWorkspaceStore.getState()));

// A debounced write must not lose the last mutation when the tab closes.
if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", () => {
    if (saveTimer) {
      window.clearTimeout(saveTimer);
      saveTimer = 0;
    }
    persistNow();
  });
}

export const selectCurrentTask = (state: WorkspaceStore): ResearchTask | undefined =>
  state.tasks.find((task) => task.id === state.selectedTaskId) ?? state.tasks[0];

export const selectCurrentWorkspace = (state: WorkspaceStore): Workspace | undefined =>
  state.workspaces.find((workspace) => workspace.id === state.activeWorkspaceId);

export const selectEnabledPlugins = (state: WorkspaceStore): Plugin[] => {
  const task = selectCurrentTask(state);
  return state.plugins.filter((plugin) => task?.plugins.includes(plugin.id));
};

export const selectPendingGuidance = (state: WorkspaceStore): Guidance[] =>
  selectCurrentTask(state)?.guidance.filter((item) => item.status === "pending") ?? [];
