import type { ShortcutAction, ShortcutMap } from "./types";

export const DEFAULT_SHORTCUTS: ShortcutMap = {
  commandPalette: "Mod+K",
  newSession: "Mod+N",
  openSettings: "Mod+,",
  focusComposer: "/",
  toggleContext: "Mod+.",
  openSkills: "Mod+Shift+K",
  openModel: "Mod+M",
  openEvidence: "Mod+E",
  openEval: "Mod+Shift+E"
};

export const SHORTCUT_ACTIONS: Array<{
  id: ShortcutAction;
  label: string;
  description: string;
  group: "全局" | "视图" | "工具";
}> = [
  {
    id: "commandPalette",
    label: "命令面板",
    description: "搜索并执行动作、打开设置",
    group: "全局"
  },
  {
    id: "newSession",
    label: "新会话",
    description: "回到欢迎页，选择工作区后开始",
    group: "全局"
  },
  {
    id: "openSettings",
    label: "打开设置",
    description: "打开全屏设置子页",
    group: "全局"
  },
  {
    id: "focusComposer",
    label: "聚焦输入框",
    description: "把焦点移到当前聊天框；输入中不会触发",
    group: "全局"
  },
  {
    id: "toggleContext",
    label: "收起 / 展开右侧上下文",
    description: "RUN / EVIDENCE / EVOLUTION / EVAL",
    group: "视图"
  },
  {
    id: "openEvidence",
    label: "查看证据链",
    description: "切到 EVIDENCE；欢迎页不可用",
    group: "视图"
  },
  {
    id: "openEval",
    label: "查看评估隔离",
    description: "切到 EVAL；欢迎页不可用",
    group: "视图"
  },
  {
    id: "openSkills",
    label: "打开 Skills",
    description: "查看目录、按需加载与创建技能",
    group: "工具"
  },
  {
    id: "openModel",
    label: "模型设置",
    description: "打开模型、上下文与思考小窗；欢迎页不可用",
    group: "工具"
  }
];

const MODIFIER_KEYS = new Set(["Shift", "Control", "Meta", "Alt", "AltGraph", "CapsLock", "Dead"]);
const RESERVED_KEYS = new Set(["Escape", "Enter", "Tab", "Backspace", "Delete"]);

function isMac(): boolean {
  return typeof navigator !== "undefined" && /mac|iphone|ipad/i.test(navigator.platform);
}

export function shortcutFromEvent(event: KeyboardEvent): string | null {
  if (event.repeat || event.isComposing) return null;
  if (MODIFIER_KEYS.has(event.key)) return null;
  const parts: string[] = [];
  if (event.metaKey || event.ctrlKey) parts.push("Mod");
  if (event.altKey) parts.push("Alt");
  if (event.shiftKey) parts.push("Shift");
  let key = event.key;
  if (key === " ") key = "Space";
  else if (key.length === 1) key = key.toUpperCase();
  if (!key || key === "Unidentified") return null;
  parts.push(key);
  return parts.join("+");
}

export function validateShortcut(shortcut: string): string | null {
  const parts = shortcut.split("+").filter(Boolean);
  const key = parts[parts.length - 1] ?? "";
  if (!key || RESERVED_KEYS.has(key)) return "Esc / Enter / Tab / Backspace / Delete 不能绑定";
  const hasModifier = parts.includes("Mod") || parts.includes("Alt");
  if (!hasModifier && key !== "/" && !/^F\d+$/.test(key)) {
    return "字母/数字/符号快捷键至少需要 Ctrl/⌘ 或 Alt";
  }
  if (parts.length === 1 && key.length === 1 && key !== "/") {
    return "单字符快捷键只允许 /";
  }
  return null;
}

export function shortcutConflict(
  shortcuts: ShortcutMap,
  action: ShortcutAction,
  shortcut: string
): { id: ShortcutAction; label: string } | null {
  const found = SHORTCUT_ACTIONS.find(
    (item) => item.id !== action && shortcuts[item.id] === shortcut
  );
  return found ? { id: found.id, label: found.label } : null;
}

export function formatShortcutLabel(shortcut: string): string {
  if (!shortcut) return "未设置";
  const mac = isMac();
  const parts = shortcut.split("+").filter(Boolean);
  return parts
    .map((part) => {
      if (part === "Mod") return mac ? "⌘" : "Ctrl";
      if (part === "Shift") return mac ? "⇧" : "Shift";
      if (part === "Alt") return mac ? "⌥" : "Alt";
      if (part === "Space") return "Space";
      return part;
    })
    .join(mac ? "" : "+");
}

export function isShortcutPressed(event: KeyboardEvent, shortcut: string): boolean {
  return shortcutFromEvent(event) === shortcut;
}
