import { lazy, Suspense, useEffect } from "react";
import type { CSSProperties } from "react";
import { AUTO_TICK_MS } from "./domain/catalog";
import { demoDwell } from "./domain/demoPlayer";
import { NARROW_LAYOUT_QUERY } from "./domain/breakpoints";
import { SHORTCUT_ACTIONS, shortcutFromEvent } from "./domain/shortcuts";
import { selectCurrentTask, useWorkspaceStore } from "./state/workspaceStore";
import { ContextPanel } from "./components/ContextPanel";
import { Conversation } from "./components/Conversation";
import { PreviewWindow } from "./components/PreviewWindow";
import { Sidebar } from "./components/Sidebar";
import { Toast } from "./components/Toast";
import { TopBar } from "./components/TopBar";
import { StaticModeNotice } from "./components/StaticModeNotice";
import { WelcomeHome } from "./components/WelcomeHome";
const SettingsPage = lazy(() =>
  import("./components/settings/SettingsPage").then((module) => ({ default: module.SettingsPage }))
);
const CommandPalette = lazy(() =>
  import("./components/CommandPalette").then((module) => ({ default: module.CommandPalette }))
);
const ModelDialog = lazy(() =>
  import("./components/ModelDialog").then((module) => ({ default: module.ModelDialog }))
);
const NewTaskDialog = lazy(() =>
  import("./components/NewTaskDialog").then((module) => ({ default: module.NewTaskDialog }))
);
const PermissionDialog = lazy(() =>
  import("./components/PermissionDialog").then((module) => ({ default: module.PermissionDialog }))
);
const PluginsDrawer = lazy(() =>
  import("./components/PluginsDrawer").then((module) => ({ default: module.PluginsDrawer }))
);
const SkillsDrawer = lazy(() =>
  import("./components/SkillsDrawer").then((module) => ({ default: module.SkillsDrawer }))
);
const WorkspaceFilesDialog = lazy(() =>
  import("./components/WorkspaceFilesDialog").then((module) => ({ default: module.WorkspaceFilesDialog }))
);
const ClaimGateDialog = lazy(() =>
  import("./components/ClaimGateDialog").then((module) => ({ default: module.ClaimGateDialog }))
);
const GateDialog = lazy(() =>
  import("./components/GateDialog").then((module) => ({ default: module.GateDialog }))
);

import { folderStorage } from "./adapters/folderStorage";
import { usePreviewStore } from "./state/previewStore";

export default function App() {
  const reduceMotion = useWorkspaceStore((state) => state.preferences.reduceMotion);
  const fontScale = useWorkspaceStore((state) => state.preferences.fontScale);
  const ui = useWorkspaceStore((state) => state.ui);
  const actions = useWorkspaceStore((state) => state.actions);
  const task = useWorkspaceStore(selectCurrentTask);
  const previewOpen = usePreviewStore((state) => state.open);
  const previewDock = usePreviewStore((state) => state.dock);

  const autoKey = task
    ? `${task.id}|${task.auto.running}|${task.auto.paused}|${task.auto.index}|${task.auto.gate}`
    : "";
  const shouldTick = Boolean(
    task?.auto.running &&
    !task.auto.paused &&
    !(task.auto.gate === "claim" && !task.auto.gateApproved)
  );

  useEffect(() => {
    if (!shouldTick) return;
    const timer = window.setTimeout(() => actions.autoStep(), AUTO_TICK_MS);
    return () => window.clearTimeout(timer);
  }, [autoKey, shouldTick, actions]);

  // Demo player engine: reveal the next transcript message after its dwell
  // time (cards hold longer than plain text). Pauses happen inside demoTick —
  // at the claim gate and at the end of the transcript.
  const demoPlayer = useWorkspaceStore((state) => state.ui.demoPlayer);
  const demoTask = useWorkspaceStore((state) =>
    state.ui.demoPlayer
      ? state.tasks.find((item) => item.id === state.ui.demoPlayer?.taskId)
      : undefined
  );
  const demoNext = demoPlayer ? demoTask?.messages[demoPlayer.revealCount] : undefined;
  const demoKey = demoPlayer
    ? `${demoPlayer.taskId}|${demoPlayer.revealCount}|${demoPlayer.playing}|${demoPlayer.finished}`
    : "";

  useEffect(() => {
    if (!demoPlayer || !demoPlayer.playing || demoPlayer.finished) return;
    if (!demoNext) {
      actions.demoTick();
      return;
    }
    const timer = window.setTimeout(() => actions.demoTick(), demoDwell(demoNext));
    return () => window.clearTimeout(timer);
  }, [demoKey, actions]);

  useEffect(() => {
    let cancelled = false;
    folderStorage.init().then((snapshot) => {
      if (snapshot && !cancelled) actions.hydrateSnapshot(snapshot, true);
    }).catch(() => {
      /* folder storage stays optional; localStorage remains the boot source */
    });
    return () => {
      cancelled = true;
    };
  }, [actions]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const store = useWorkspaceStore.getState();
      const { ui, preferences } = store;
      const target = event.target as HTMLElement | null;
      const typing =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.tagName === "SELECT" ||
        target?.isContentEditable;

      if (event.key === "Escape") {
        if (ui.permissionRequest) {
          actions.cancelPermission();
          return;
        }
        if (ui.claimGateOpen) {
          actions.closeClaimGate();
          return;
        }
        if (ui.gateDialog) {
          actions.closeGateDialog();
          return;
        }
        if (ui.paletteOpen || ui.modelOpen || ui.pluginsOpen || ui.skillsOpen || ui.newTaskOpen) {
          actions.closeOverlays();
          return;
        }
        if (ui.settingsOpen) {
          actions.closeSettings();
          return;
        }
        const preview = usePreviewStore.getState();
        if (preview.open) {
          preview.close();
          return;
        }
        actions.setUI({ sidebarOpen: false, contextOpen: false });
        return;
      }

      const pressed = shortcutFromEvent(event);
      if (!pressed) return;
      const action = SHORTCUT_ACTIONS.find(
        (item) => preferences.shortcuts[item.id] === pressed
      )?.id;
      if (!action) return;

      if (action === "focusComposer") {
        if (typing || ui.paletteOpen || ui.modelOpen || ui.newTaskOpen || ui.settingsOpen) return;
        event.preventDefault();
        actions.focusComposer();
        return;
      }

      if (action === "toggleContext" && ui.welcomeOpen) {
        event.preventDefault();
        actions.notify("先开始一个会话，再打开运行上下文");
        return;
      }
      if ((action === "openEvidence" || action === "openEval" || action === "openModel") && ui.welcomeOpen) {
        event.preventDefault();
        actions.notify("先开始一个会话，再使用这个快捷键");
        return;
      }

      event.preventDefault();
      switch (action) {
        case "commandPalette":
          actions.openOverlay("paletteOpen");
          break;
        case "newSession":
          actions.openWelcome();
          break;
        case "openSettings":
          actions.openSettings("general");
          break;
        case "toggleContext": {
          const narrow = window.matchMedia(NARROW_LAYOUT_QUERY).matches;
          if (narrow) actions.setUI({ contextOpen: !ui.contextOpen });
          else actions.setUI({ contextCollapsed: !ui.contextCollapsed });
          break;
        }
        case "openSkills":
          actions.openOverlay("skillsOpen");
          break;
        case "openModel":
          actions.openOverlay("modelOpen");
          break;
        case "openEvidence":
          actions.setContextTab("evidence");
          break;
        case "openEval":
          actions.setContextTab("eval");
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [actions]);

  return (
    <div
      className={`ra-app${reduceMotion ? " reduce-motion" : ""}`}
      style={{ "--font-scale": fontScale } as CSSProperties}
    >
      <a className="skip-link" href="#thread">跳到会话</a>
      <TopBar />
      <StaticModeNotice />
      <div className={`app-grid${ui.contextCollapsed ? " is-context-collapsed" : ""}${ui.welcomeOpen ? " is-welcome" : ""}${previewOpen && previewDock && !ui.welcomeOpen ? " is-preview-docked" : ""}`}>
        {ui.sidebarOpen && (
          <button
            type="button"
            className="scrim sidebar-scrim"
            aria-label="关闭会话列表"
            onClick={() => actions.setUI({ sidebarOpen: false })}
          />
        )}
        <Sidebar />
        {ui.welcomeOpen ? <WelcomeHome /> : <Conversation />}
        {!ui.welcomeOpen && ui.contextOpen && (
          <button
            type="button"
            className="scrim context-scrim"
            aria-label="关闭运行上下文"
            onClick={() => actions.setUI({ contextOpen: false })}
          />
        )}
        {!ui.welcomeOpen && <ContextPanel />}
        {previewOpen && !ui.settingsOpen && <PreviewWindow />}
      </div>

      <Suspense fallback={<div className="overlay-loading" role="status">正在载入面板…</div>}>
        {ui.settingsOpen && <SettingsPage />}
        {ui.newTaskOpen && <NewTaskDialog />}
        {ui.modelOpen && <ModelDialog />}
        {ui.pluginsOpen && <PluginsDrawer />}
        {ui.skillsOpen && <SkillsDrawer />}
        {ui.filesOpen && <WorkspaceFilesDialog />}
        {ui.permissionRequest && <PermissionDialog />}
        {ui.claimGateOpen && <ClaimGateDialog />}
        {ui.gateDialog && <GateDialog />}
        <CommandPalette />
      </Suspense>
      <Toast />
    </div>
  );
}
