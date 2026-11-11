import { useEffect, useMemo, useState } from "react";
import type { IconName } from "./Icon";
import { Icon } from "./Icon";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";

interface PaletteItem {
  label: string;
  hint: string;
  keywords: string;
  icon: IconName;
  run: () => void;
}

export function CommandPalette() {
  const actions = useWorkspaceStore((state) => state.actions);
  const task = useWorkspaceStore(selectCurrentTask);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);
  const autoRunning = Boolean(task?.auto.running);
  const autoPaused = Boolean(task?.auto.paused);
  const gateUnsigned = Boolean(task?.auto.running && task.auto.gate === "claim" && !task.auto.gateApproved);
  const hasEvidence = Boolean((task?.coverage.spans ?? 0) > 0);
  const hasProtocol = Boolean(task?.protocol);
  const protocolFrozen = Boolean(task?.protocolFrozen);
  const unsignedClaim = Boolean(task?.evidence.some((item) => item.kind === "claim" && item.status === "unsigned"));
  const evaluated = Boolean((task?.evaluation.hiddenAccessCount ?? 0) > 0);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);

  const items = useMemo<PaletteItem[]>(() => {
    if (welcomeOpen) {
      return [
        { label: "Skills / 技能", hint: "SKILLS", keywords: "skill 技能 调用 创建", icon: "spark", run: () => actions.openOverlay("skillsOpen") },
        { label: "工作区文件", hint: "FILES", keywords: "files folder workspace 文件 文件夹 项目说明", icon: "folder", run: () => actions.openFiles() },
        { label: "表单新建任务", hint: "FORM", keywords: "new task form 任务 表单", icon: "plus", run: () => actions.openOverlay("newTaskOpen") },
        { label: "设置与使用统计", hint: "SETTINGS", keywords: "settings usage token 设置 统计", icon: "chart", run: () => actions.openSettings("usage") },
        { label: "证据沿袭与变更影响", hint: "LINEAGE", keywords: "lineage stale change closure 沿袭 变更 失效", icon: "branch", run: () => actions.openSettings("lineage") },
        { label: "外观与字体", hint: "APPEARANCE", keywords: "font appearance 字体 外观", icon: "eye", run: () => actions.openSettings("appearance") },
        { label: "导出工作台状态", hint: "JSON", keywords: "export download 导出", icon: "download", run: actions.exportWorkspace },
        {
          label: "重置示例",
          hint: "LOCAL",
          keywords: "reset 重置 clear",
          icon: "trash",
          run: () => {
            if (window.confirm("重置会清空本地示例状态，确定继续？")) actions.resetWorkspace();
          }
        }
      ];
    }
    const manualItems: PaletteItem[] = [
      { label: "工作区文件", hint: "FILES", keywords: "files folder workspace 文件 文件夹 项目说明", icon: "folder", run: () => actions.openFiles(task?.workspaceId) },
      { label: hasEvidence ? "扩展检索" : "开始检索", hint: "S1", keywords: "检索 research literature", icon: "search", run: actions.runResearch },
      ...(hasEvidence && !hasProtocol ? [{ label: "送入实验设计", hint: "S2–S4", keywords: "假设 experiment design", icon: "branch" as IconName, run: actions.designExperiment }] : []),
      ...(hasProtocol && !protocolFrozen ? [{ label: "G2 人签冻结命令", hint: "CLI ONLY", keywords: "protocol freeze 冻结 g2 人工门 cli", icon: "lock" as IconName, run: actions.freezeProtocol }] : []),
      ...(protocolFrozen && !evaluated ? [{ label: "运行实验", hint: "S5", keywords: "run experiment seeds", icon: "play" as IconName, run: actions.runExperiment }] : []),
      ...(unsignedClaim ? [{ label: "签署 claim · 打开人工门", hint: "打开面板", keywords: "claim sign 签核 人工门 cli", icon: "lock" as IconName, run: actions.signClaim }] : [])
    ];
    const autoItems: PaletteItem[] = autoRunning
      ? [
          gateUnsigned
            ? { label: "签署 claim · 打开人工门", hint: "打开面板", keywords: "claim sign 签核 人工门 cli", icon: "lock", run: actions.signClaim }
            : autoPaused
              ? { label: "继续全自动", hint: "RESUME", keywords: "auto continue resume 自动 继续", icon: "play", run: actions.resumeAuto }
              : { label: "暂停全自动", hint: "PAUSE", keywords: "auto pause 自动 暂停", icon: "pause", run: actions.pauseAuto },
          ...(gateUnsigned ? [] : [{ label: "单步执行", hint: "STEP", keywords: "step 单步", icon: "step" as IconName, run: actions.stepAuto }]),
          { label: "停止全自动", hint: "STOP", keywords: "auto stop 停止", icon: "stop", run: actions.stopAuto }
        ]
      : [
          { label: "启动全自动", hint: "GOVERNED", keywords: "auto 自动 start", icon: "spark", run: actions.startAuto },
          { label: "单步执行", hint: "STEP", keywords: "step 单步", icon: "step", run: actions.stepAuto }
        ];
    return [
      { label: "新会话", hint: "HOME", keywords: "new session home 新会话", icon: "plus", run: () => actions.openWelcome() },
      { label: "表单新建任务", hint: "FORM", keywords: "new task form 任务 表单", icon: "tasks", run: () => actions.openOverlay("newTaskOpen") },
      ...(autoRunning ? [] : manualItems),
      ...(autoRunning
        ? []
        : [{ label: "生成写作槽位", hint: "S8–S12", keywords: "writing paper slot 写作 槽位 摘要 正文", icon: "book" as IconName, run: actions.prepareWriting }]),
      ...autoItems,
      { label: "Skills / 技能", hint: "SKILLS", keywords: "skill 技能 调用 创建 工具", icon: "spark", run: () => actions.openOverlay("skillsOpen") },
      { label: "查看证据链", hint: "EVIDENCE", keywords: "evidence claim gap span", icon: "evidence", run: () => actions.setContextTab("evidence") },
      { label: "查看评估隔离", hint: "EVAL", keywords: "eval audit held-out baseline 评估 审计 基线", icon: "shield", run: () => actions.setContextTab("eval") },
      { label: "查看自进化", hint: "EVOLUTION", keywords: "evolution rsi lease 候选", icon: "evolution", run: () => actions.setContextTab("evolution") },
      { label: "模型设置", hint: "MODEL", keywords: "model context thinking 模型", icon: "cpu", run: () => actions.openOverlay("modelOpen") },
      { label: "插件 / MCP", hint: "TOOLS", keywords: "plugin mcp github 工具", icon: "terminal", run: () => actions.openOverlay("pluginsOpen") },
      { label: "设置与使用统计", hint: "SETTINGS", keywords: "settings usage token 设置 统计", icon: "chart", run: () => actions.openSettings("usage") },
      { label: "证据沿袭与变更影响", hint: "LINEAGE", keywords: "lineage stale change closure 沿袭 变更 失效", icon: "branch", run: () => actions.openSettings("lineage") },
      { label: "外观与字体", hint: "APPEARANCE", keywords: "font appearance 字体 外观", icon: "eye", run: () => actions.openSettings("appearance") },
      { label: "导出工作台状态", hint: "JSON", keywords: "export download 导出", icon: "download", run: actions.exportWorkspace },
      {
        label: "重置示例",
        hint: "LOCAL",
        keywords: "reset 重置 clear",
        icon: "trash",
        run: () => {
          if (window.confirm("重置会清空本地示例状态，确定继续？")) actions.resetWorkspace();
        }
      }
    ];
  }, [actions, autoPaused, autoRunning, evaluated, gateUnsigned, hasEvidence, hasProtocol, protocolFrozen, unsignedClaim, welcomeOpen]);

  const filtered = items.filter((item) =>
    `${item.label} ${item.hint} ${item.keywords}`.toLowerCase().includes(query.trim().toLowerCase())
  );

  useEffect(() => setIndex(0), [query]);

  const execute = (item: PaletteItem | undefined) => {
    if (!item) return;
    actions.setUI({ paletteOpen: false });
    item.run();
  };

  return (
    <div className="palette-layer" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) actions.setUI({ paletteOpen: false });
    }}>
      <section className="palette" role="dialog" aria-modal="true" aria-label="命令面板">
        <div className="palette-input">
          <span>/</span>
          <input
            autoFocus
            value={query}
            placeholder="搜索动作：检索、实验、自动、证据、回滚…"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown") {
                event.preventDefault();
                setIndex((current) => Math.min(current + 1, filtered.length - 1));
              } else if (event.key === "ArrowUp") {
                event.preventDefault();
                setIndex((current) => Math.max(current - 1, 0));
              } else if (event.key === "Enter") {
                event.preventDefault();
                execute(filtered[index]);
              }
            }}
          />
          <kbd>ESC</kbd>
        </div>
        <div className="palette-list" role="listbox" aria-label="命令">
          {filtered.length ? filtered.map((item, itemIndex) => (
            <button
              type="button"
              key={item.label}
              role="option"
              aria-selected={itemIndex === index}
              className={itemIndex === index ? "is-on" : ""}
              onMouseEnter={() => setIndex(itemIndex)}
              onClick={() => execute(item)}
            >
              <span className="palette-icon"><Icon name={item.icon} size={13} /></span>
              <b>{item.label}</b>
              <em>{item.hint}</em>
            </button>
          )) : (
            <p className="palette-empty">没有匹配动作</p>
          )}
        </div>
        <footer className="palette-foot">
          <span>↑↓ 选择 · Enter 执行 · Esc 关闭</span>
          <span>COMMAND</span>
        </footer>
      </section>
    </div>
  );
}
