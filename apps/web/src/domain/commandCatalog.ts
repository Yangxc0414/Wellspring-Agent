import type { ResearchTask } from "./types";

export type SlashCommandGroup = "run" | "work" | "view" | "tools";

export interface SlashCommand {
  id: string;
  name: string;
  description: string;
  hint: string;
  group: SlashCommandGroup;
  aliases?: string[];
  available?: (task: ResearchTask) => boolean;
}

const isRunning = (task: ResearchTask): boolean => task.auto.running;
const isPaused = (task: ResearchTask): boolean => task.auto.running && task.auto.paused;
const readOnly = (task: ResearchTask): boolean => task.access === "read_only";
const claimGate = (task: ResearchTask): boolean =>
  task.auto.gate === "claim" && !task.auto.gateApproved;
const hasSpans = (task: ResearchTask): boolean => task.coverage.spans > 0;
const hasProtocol = (task: ResearchTask): boolean => Boolean(task.protocol);
const protocolFrozen = (task: ResearchTask): boolean => task.protocolFrozen;
const hasUnsignedClaim = (task: ResearchTask): boolean =>
  task.evidence.some((item) => item.kind === "claim" && item.status === "unsigned");
const heldoutUsed = (task: ResearchTask): boolean => task.evaluation.hiddenAccessCount > 0;

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: "start",
    name: "启动全自动",
    description: "从 S1 连续执行，停在 claim 人工门",
    hint: "无需参数",
    group: "run",
    aliases: ["auto"],
    available: (task) => !isRunning(task) && !heldoutUsed(task) && !readOnly(task)
  },
  {
    id: "live",
    name: "运行真实 pipeline",
    description: "提交本地 runtime 任务（SSE + 轮询），只生成待审包，不自动签 claim",
    hint: "/live <研究问题>",
    group: "run",
    available: (task) => !isRunning(task) && !readOnly(task)
  },
  {
    id: "pause",
    name: "暂停",
    description: "暂停当前运行，保留未完成阶段",
    hint: "运行中可用",
    group: "run",
    available: (task) => isRunning(task) && !isPaused(task)
  },
  {
    id: "resume",
    name: "继续",
    description: "从当前暂停阶段继续",
    hint: "暂停后可用",
    group: "run",
    available: (task) => isPaused(task) && !claimGate(task)
  },
  {
    id: "step",
    name: "单步",
    description: "只推进一个阶段后暂停",
    hint: "运行或暂停时可用",
    group: "run",
    available: (task) => !claimGate(task) && (isRunning(task) || !readOnly(task))
  },
  {
    id: "stop",
    name: "停止",
    description: "停止全自动，保留已封存证据",
    hint: "运行中可用",
    group: "run",
    available: isRunning
  },
  {
    id: "research",
    name: "检索",
    description: "生成或扩展 S1 检索与覆盖",
    hint: "可补检索重点",
    group: "work",
    available: (task) => !isRunning(task)
  },
  {
    id: "review",
    name: "运行审阅包",
    description: "让已启用的审阅角色检查当前证据，只读 advisory",
    hint: "不写 Claim/EA/gate",
    group: "work",
    available: (task) => !isRunning(task)
  },
  {
    id: "experiment",
    name: "实验设计",
    description: "从 gap 进入 S4 协议草案",
    hint: "需已有 span/gap",
    group: "work",
    available: (task) => !isRunning(task) && !readOnly(task) && hasSpans(task) && !hasProtocol(task)
  },
  {
    id: "freeze",
    name: "G2 冻结命令",
    description: "显示终端里的人工冻结命令；网页不冻结协议",
    hint: "需已有协议草案",
    group: "work",
    available: (task) => !isRunning(task) && !readOnly(task) && hasProtocol(task) && !protocolFrozen(task)
  },
  {
    id: "run",
    name: "运行实验",
    description: "按冻结协议运行 seeds 并封存 EA",
    hint: "需先冻结协议",
    group: "work",
    available: (task) => !isRunning(task) && !readOnly(task) && protocolFrozen(task) && !heldoutUsed(task)
  },
  {
    id: "writing",
    name: "写作槽位",
    description: "按已签 claim 刷新六个槽位",
    hint: "需已有 claim",
    group: "work",
    available: (task) => !isRunning(task)
  },
  {
    id: "sign",
    name: "claim 人签命令",
    description: "显示终端里的人签命令；claim 保持待签，签名不经过浏览器",
    hint: "需已有 EA",
    group: "work",
    aliases: ["claim"],
    available: (task) => !readOnly(task) && hasUnsignedClaim(task)
  },
  {
    id: "evidence",
    name: "查看证据链",
    description: "切换到 span / EA / claim / gate",
    hint: "只读",
    group: "view"
  },
  {
    id: "eval",
    name: "评估隔离",
    description: "查看 held-out、规则、复现基线与审计",
    hint: "只读",
    group: "view"
  },
  {
    id: "evolution",
    name: "查看自进化",
    description: "打开候选、租约与回滚",
    hint: "只读",
    group: "view"
  },
  {
    id: "lineage",
    name: "证据沿袭",
    description: "查看变更影响与 stale 传播",
    hint: "只读",
    group: "view"
  },
  {
    id: "skills",
    name: "Skills",
    description: "查看目录与按需加载状态",
    hint: "目录常驻",
    group: "tools"
  },
  {
    id: "agents",
    name: "子智能体",
    description: "查看或添加 advisory 子智能体",
    hint: "设置 → 子智能体",
    group: "tools"
  },
  {
    id: "files",
    name: "文件",
    description: "浏览当前工作区文件，只读预览",
    hint: "本地文件夹",
    group: "tools"
  },
  {
    id: "memory",
    name: "记忆",
    description: "查看会话记忆与归档",
    hint: "设置 → 记忆",
    group: "tools"
  },
  {
    id: "new",
    name: "新会话",
    description: "回到欢迎页新建会话",
    hint: "当前任务保留",
    group: "tools"
  },
  {
    id: "model",
    name: "模型选择",
    description: "切换模型、思考强度与上下文预算",
    hint: "当前会话",
    group: "tools"
  },
  {
    id: "plugins",
    name: "插件 / MCP",
    description: "查看连接器与工具审批",
    hint: "只读登记",
    group: "tools"
  },
  {
    id: "export",
    name: "导出状态",
    description: "导出当前工作台 JSON 快照",
    hint: "本地下载",
    group: "tools"
  },
  {
    id: "settings",
    name: "设置",
    description: "打开设置中心",
    hint: "全屏",
    group: "tools"
  },
  {
    id: "help",
    name: "帮助",
    description: "列出所有可用命令",
    hint: "无需参数",
    group: "tools"
  }
];

const DEFAULT_SLASH_COMMAND_IDS = [
  "start",
  "research",
  "review",
  "freeze",
  "run",
  "sign",
  "evidence",
  "eval",
  "skills"
];

function defaultCommandIds(task: ResearchTask): string[] {
  const ids: string[] = [];
  if (task.auto.running) {
    if (claimGate(task)) return ["sign", "evidence", "eval", "skills"];
    ids.push(isPaused(task) ? "resume" : "pause", "step", "stop");
  } else if (!readOnly(task) && !heldoutUsed(task) && !hasUnsignedClaim(task)) {
    ids.push("start");
  }
  if (!hasSpans(task)) {
    ids.push("research");
  } else if (!hasProtocol(task)) {
    if (!readOnly(task)) ids.push("experiment");
  } else if (!protocolFrozen(task)) {
    if (!readOnly(task)) ids.push("freeze");
  } else if (!heldoutUsed(task) && !readOnly(task)) {
    ids.push("run");
  }
  if (hasUnsignedClaim(task)) ids.push("sign");
  if (task.evidence.some((item) => item.kind === "claim" && item.status === "signed")) {
    ids.push("writing");
  }
  ids.push("evidence", "eval", "skills", "files");
  return ids;
}

export const COMMAND_GROUP_LABELS: Record<SlashCommandGroup, string> = {
  run: "RUN",
  work: "WORK",
  view: "VIEW",
  tools: "TOOLS"
};

export function matchSlashCommands(
  query: string,
  limit = 6,
  task?: ResearchTask
): SlashCommand[] {
  const needle = query.toLowerCase();
  const pool = needle
    ? SLASH_COMMANDS.filter((command) =>
        `${command.id} ${command.name} ${command.description} ${(command.aliases ?? []).join(" ")}`
          .toLowerCase()
          .includes(needle)
      )
    : SLASH_COMMANDS.filter((command) =>
        (task ? defaultCommandIds(task) : DEFAULT_SLASH_COMMAND_IDS).includes(command.id)
      );
  return pool
    .filter((command) => !task || !command.available || command.available(task))
    .slice(0, limit);
}
