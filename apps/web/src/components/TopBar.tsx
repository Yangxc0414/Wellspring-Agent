import { useEffect, useState } from "react";
import { formatShortcutLabel } from "../domain/shortcuts";
import { NARROW_LAYOUT_QUERY } from "../domain/breakpoints";
import { probeRuntime } from "../adapters/runtimeApi";
import { usePreviewStore } from "../state/previewStore";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

function useNarrowLayout(): boolean {
  const [narrow, setNarrow] = useState(() => window.matchMedia(NARROW_LAYOUT_QUERY).matches);
  useEffect(() => {
    const query = window.matchMedia(NARROW_LAYOUT_QUERY);
    const update = () => setNarrow(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}

export function TopBar() {
  const task = useWorkspaceStore(selectCurrentTask);
  const contextOpen = useWorkspaceStore((state) => state.ui.contextOpen);
  const contextCollapsed = useWorkspaceStore((state) => state.ui.contextCollapsed);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);
  const shortcuts = useWorkspaceStore((state) => state.preferences.shortcuts);
  const actions = useWorkspaceStore((state) => state.actions);
  const previewOpen = usePreviewStore((state) => state.open);
  const previewDock = usePreviewStore((state) => state.dock);
  const showPreview = usePreviewStore((state) => state.show);
  const closePreview = usePreviewStore((state) => state.close);
  const [apiConnected, setApiConnected] = useState(false);
  const narrow = useNarrowLayout();

  useEffect(() => {
    let cancelled = false;
    probeRuntime()
      .then((health) => {
        if (!cancelled) setApiConnected(health.status === "ok");
      })
      .catch(() => {
        if (!cancelled) setApiConnected(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const contextActive = narrow ? contextOpen : !contextCollapsed;
  const contextLabel = narrow
    ? contextOpen
      ? "关闭运行上下文"
      : "打开运行上下文"
    : contextCollapsed
      ? "展开运行上下文"
      : "收起运行上下文";

  const toggleContext = () => {
    if (narrow) {
      actions.setUI({ contextOpen: !contextOpen });
      return;
    }
    actions.setUI({ contextCollapsed: !contextCollapsed });
  };

  return (
    <header className={`topbar${welcomeOpen ? " is-home" : ""}`}>
      <button type="button" className="brand" onClick={() => actions.openWelcome()} title="回到新会话">
        <span className="brand-mark">
          <Icon name="logo" size={18} />
        </span>
        <span className="brand-copy">
          <b>Research Agent</b>
          <small>LOCAL WORKSPACE</small>
        </span>
      </button>

      <div className="brand-nav" aria-label="导航">
        <button
          type="button"
          className="chrome-nav"
          onClick={() => actions.openWelcome()}
          disabled={welcomeOpen}
          aria-label="回到新会话"
          title="回到新会话"
        >
          <span className="nav-arrow is-back"><Icon name="arrow" size={14} /></span>
        </button>
        <button
          type="button"
          className="chrome-nav"
          onClick={() => task && actions.selectTask(task.id)}
          disabled={!welcomeOpen || !task}
          aria-label="返回最近任务"
          title="返回最近任务"
        >
          <Icon name="arrow" size={14} />
        </button>
      </div>

      <div className="top-actions">
        <span
          className={`sim-badge${apiConnected && !__STATIC_ONLY__ ? " is-live" : ""}`}
          title={
            __STATIC_ONLY__
              ? "静态演示构建：runtime 已在编译时禁用，真实运行、人工签核与导出只在本地 CLI 可用"
              : apiConnected
                ? "本地 runtime API 已连接；工作台默认仍为本地会话，/live 运行才走真实 pipeline"
                : "静态适配器：不调用 API、不产生真实实验或 claim"
          }
        >
          {__STATIC_ONLY__
            ? "静态演示 · RUNTIME 已禁用"
            : apiConnected
              ? "API · LOCAL"
              : "演示数据 · 静态"}
        </span>
        <button
          type="button"
          className="icon-button mobile-tasks"
          onClick={() => actions.setUI({ sidebarOpen: true })}
          aria-label="打开会话列表"
          title="任务列表"
        >
          <Icon name="tasks" size={15} />
        </button>
        <button
          type="button"
          className="icon-button mobile-settings"
          onClick={() => actions.openSettings("general")}
          aria-label="设置"
          title="设置"
        >
          <Icon name="sliders" size={15} />
        </button>
        {!welcomeOpen && (
          <button
            type="button"
            className={`icon-button context-toggle${contextActive ? " is-on" : ""}`}
            onClick={() => {
              if (previewOpen && previewDock) {
                closePreview();
                return;
              }
              toggleContext();
            }}
            aria-label={previewOpen && previewDock ? "关闭预览并回到运行上下文" : contextLabel}
            aria-pressed={contextActive}
            title={previewOpen && previewDock ? "关闭预览并回到运行上下文" : contextLabel}
          >
            <Icon name="panel" size={15} />
          </button>
        )}
        <button
          type="button"
          className={`icon-button preview-trigger${previewOpen ? " is-on" : ""}`}
          onClick={() => (previewOpen ? closePreview() : showPreview())}
          aria-label="文件预览"
          aria-pressed={previewOpen}
          title="文件预览"
        >
          <Icon name="eye" size={15} />
        </button>
        <button
          type="button"
          className="icon-button"
          onClick={() => actions.openWelcome()}
          aria-label="新会话"
          title={`新会话 (${formatShortcutLabel(shortcuts.newSession)})`}
        >
          <Icon name="plus" size={15} />
        </button>
        <button
          type="button"
          className="icon-button palette-trigger"
          onClick={() => actions.openOverlay("paletteOpen")}
          aria-label="打开命令面板"
          title={`命令面板 (${formatShortcutLabel(shortcuts.commandPalette)})`}
        >
          <Icon name="command" size={14} />
        </button>
        <button
          type="button"
          className="icon-button desktop-only"
          onClick={() => actions.exportWorkspace()}
          aria-label="导出当前状态"
          title="导出当前状态 JSON"
        >
          <Icon name="download" size={14} />
        </button>
      </div>
    </header>
  );
}
