import type { ChangeEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { APP_VERSION } from "../domain/catalog";
import { siteHref } from "../domain/links";
import { formatShortcutLabel } from "../domain/shortcuts";
import type { ResearchTask } from "../domain/types";
import { formatBytes, isoNow, relativeTime } from "../domain/utils";
import { requestAutomationPlan } from "../adapters/runtimeApi";
import { usePreviewStore } from "../state/previewStore";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

type PendingDelete =
  | { kind: "task"; id: string; name: string }
  | { kind: "workspace"; id: string; name: string; count: number };

export function Sidebar() {
  const tasks = useWorkspaceStore((state) => state.tasks);
  const archivedTaskIds = useWorkspaceStore((state) => state.archivedTaskIds);
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const selectedTaskId = useWorkspaceStore((state) => state.selectedTaskId);
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);
  const search = useWorkspaceStore((state) => state.ui.search);
  const expanded = useWorkspaceStore((state) => state.ui.expandedWorkspaces);
  const sidebarOpen = useWorkspaceStore((state) => state.ui.sidebarOpen);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);
  const skills = useWorkspaceStore((state) => state.skills);
  const shortcuts = useWorkspaceStore((state) => state.preferences.shortcuts);
  const actions = useWorkspaceStore((state) => state.actions);
  const addPreviewFiles = usePreviewStore((state) => state.addFiles);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const previewInputRef = useRef<HTMLInputElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const [searchOpen, setSearchOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);

  useEffect(() => {
    if (!pendingDelete) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPendingDelete(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [pendingDelete]);

  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);

  const handleFolder = (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!files.length) {
      actions.notify("没有读取到文件；空文件夹未添加");
      return;
    }
    const name = (files[0].webkitRelativePath.split("/")[0] || "本地资料").slice(0, 40);
    const bytes = files.reduce((sum, file) => sum + file.size, 0);
    addPreviewFiles(files);
    actions.addWorkspace({
      name,
      note: `本地文件夹 · ${files.length} 个文件 · ${formatBytes(bytes)} · 可预览`,
      folder: { name, files: files.length, bytes, importedAt: isoNow() }
    });
  };

  const handlePreviewFiles = (event: ChangeEvent<HTMLInputElement>) => {
    addPreviewFiles(event.target.files ?? []);
    event.target.value = "";
  };

  const selectedTask = tasks.find((task) => task.id === selectedTaskId) ?? tasks[0];

  const handleAutomation = async () => {
    if (welcomeOpen) {
      actions.openNewTask("auto");
      return;
    }
    const task = selectedTask;
    if (!task) return;
    actions.setMode("auto");
    actions.setContextTab("run");
    const dataset = (task.run?.dataset ?? "").toLowerCase();
    const runDataset = dataset.includes("chemlab")
      ? "chemlab"
      : dataset.includes("breast")
        ? "breast_cancer"
        : dataset.includes("iris")
          ? "iris"
          : "";
    try {
      const plan = await requestAutomationPlan({
        topic: task.goal || task.name,
        max_sources: 6,
        run_dataset: runDataset,
        run_seeds: task.protocol?.seeds ?? 3
      });
      actions.setAutoPlan(task.id, plan);
      actions.notify(
        `后端运行计划 ${plan.fingerprint.slice(-8)} 已生成：${plan.stages.length} 阶段，停在 ${plan.stop_at}`
      );
    } catch {
      actions.notify("已切换到全自动；runtime 离线，使用本地阶段计划");
    }
  };

  const confirmDelete = () => {
    if (!pendingDelete) return;
    if (pendingDelete.kind === "task") actions.deleteTask(pendingDelete.id);
    else actions.deleteWorkspace(pendingDelete.id);
    setPendingDelete(null);
  };

  const query = search.trim().toLowerCase();
  const activeTasks = tasks.filter((task) => !archivedTaskIds.includes(task.id));
  const filtered = activeTasks.filter((task) => {
    if (!query) return true;
    const workspace = workspaces.find((item) => item.id === task.workspaceId);
    return `${task.name} ${task.goal} ${task.domain} ${workspace?.name ?? ""}`.toLowerCase().includes(query);
  });
  const sorted = [...filtered].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  const availableSkills = skills.filter((skill) => skill.activation !== "off").length;

  const taskStatus = (task: ResearchTask) => {
    if (task.auto.running) return task.auto.paused ? "暂停" : "运行中";
    if (task.status === "blocked") return "待签";
    return relativeTime(task.updatedAt);
  };

  const renderTask = (task: ResearchTask) => {
    const selected = !welcomeOpen && selectedTaskId === task.id;
    return (
      <div className="task-row-wrap" key={task.id}>
        <button
          type="button"
          className={`task-row${selected ? " is-selected" : ""}`}
          data-status={task.status}
          data-auto={task.auto.running ? (task.auto.paused ? "paused" : "running") : "idle"}
          onClick={() => actions.selectTask(task.id)}
          aria-current={selected ? "page" : undefined}
          title={`${task.name} · ${task.completedStages.length}/9 stages`}
        >
          <span className="task-dot" aria-hidden="true" />
          <span className="task-row-title">{task.name}</span>
          <span className="task-row-time">{taskStatus(task)}</span>
        </button>
        <button
          type="button"
          className="task-delete"
          onClick={() => setPendingDelete({ kind: "task", id: task.id, name: task.name })}
          title={`删除任务「${task.name}」`}
          aria-label={`删除任务 ${task.name}`}
        >
          <Icon name="trash" size={11} />
        </button>
      </div>
    );
  };

  return (
    <aside className={`sidebar${sidebarOpen ? " is-open" : ""}`} aria-label="任务与会话">
      <div className="sidebar-scroll">
        <nav className="sidebar-quick" aria-label="快捷入口">
          <button
            type="button"
            className="quick-primary"
            onClick={() => (welcomeOpen ? actions.openNewTask("research") : actions.openWelcome())}
            title="新建任务：已有会话时回到欢迎页，欢迎页直接打开表单"
          >
            <span className="quick-primary-icon"><Icon name="plus" size={15} /></span>
            <span className="quick-primary-copy">
              <b>新建任务</b>
              <small>从问题开始一个新会话</small>
            </span>
            <kbd>{formatShortcutLabel(shortcuts.newSession)}</kbd>
          </button>
          <div className="quick-grid">
            <button
              type="button"
              className="quick-tile"
              onClick={() => void handleAutomation()}
              title="自动化：欢迎页预填全自动；会话内生成后端运行计划并打开 RUN"
            >
              <span className="quick-tile-icon is-play"><Icon name="play" size={13} /></span>
              <span>自动化</span>
            </button>
            <button
              type="button"
              className="quick-tile"
              onClick={() => actions.openOverlay("skillsOpen")}
              title="技能：目录常驻；会话中按需加载，导入项仅手动"
            >
              <span className="quick-tile-icon is-violet"><Icon name="spark" size={13} /></span>
              <span>技能</span>
              <em>{availableSkills}</em>
            </button>
            <button
              type="button"
              className="quick-tile"
              onClick={() => actions.openOverlay("pluginsOpen")}
              title="插件：登记连接器；无会话时只登记不启用"
            >
              <span className="quick-tile-icon"><Icon name="grid" size={13} /></span>
              <span>插件</span>
            </button>
          </div>
        </nav>

        <section className="task-list-section">
          <div className="task-list-head">
            <span className="task-list-title">任务 <em>{activeTasks.length}</em></span>
            <div className="task-list-actions">
              <button
                type="button"
                className={`task-list-icon${searchOpen ? " is-on" : ""}`}
                onClick={() => {
                  setSearchOpen((open) => {
                    if (open) actions.setUI({ search: "" });
                    return !open;
                  });
                }}
                aria-label="搜索任务"
                title="搜索任务"
                aria-pressed={searchOpen}
              >
                <Icon name="search" size={13} />
              </button>
              <button
                type="button"
                className="task-list-icon"
                onClick={() => folderInputRef.current?.click()}
                aria-label="导入本地文件夹"
                title="导入本地文件夹（可预览，不上传）"
              >
                <Icon name="folder" size={13} />
              </button>
              <button
                type="button"
                className="task-list-icon"
                onClick={() => previewInputRef.current?.click()}
                aria-label="预览本地文件"
                title="预览本地文件（只读，不上传）"
              >
                <Icon name="eye" size={13} />
              </button>
            </div>
          </div>

          {searchOpen && (
            <label className="search-field task-search">
              <Icon name="search" size={12} />
              <input
                ref={searchInputRef}
                type="search"
                value={search}
                placeholder="搜索任务 / 目标 / 工作区…"
                onChange={(event) => actions.setUI({ search: event.target.value })}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    actions.setUI({ search: "" });
                    setSearchOpen(false);
                  }
                }}
                aria-label="搜索任务"
              />
              {search && (
                <button
                  type="button"
                  className="search-clear"
                  onClick={() => actions.setUI({ search: "" })}
                  aria-label="清空搜索"
                >
                  <Icon name="close" size={11} />
                </button>
              )}
            </label>
          )}

          <div className="side-label workspace-label">
            <span>工作区</span>
            <span className="side-label-count">{String(workspaces.length).padStart(2, "0")}</span>
          </div>

          <nav className="workspace-list" aria-label="工作区">
            {workspaces.map((workspace) => {
              const workspaceTasks = sorted.filter((task) => task.workspaceId === workspace.id);
              const allCount = activeTasks.filter((task) => task.workspaceId === workspace.id).length;
              const open = query ? true : (expanded[workspace.id] ?? true);
              const isActive = activeWorkspaceId === workspace.id;
              if (query && !workspaceTasks.length) return null;
              return (
                <div className={`workspace-group${isActive ? " is-active" : ""}${open ? " is-open" : ""}`} key={workspace.id}>
                  <div className="workspace-head-row">
                    <button
                      type="button"
                      className="workspace-head"
                      onClick={() => {
                        actions.activateWorkspace(workspace.id);
                        if (!query) actions.toggleWorkspace(workspace.id);
                      }}
                      aria-expanded={open}
                      title={workspace.folder
                        ? `${workspace.note} · 登记于 ${workspace.folder.importedAt.slice(0, 10)}`
                        : workspace.note}
                    >
                      <span className={`chevron${open ? " is-open" : ""}`}>
                        <Icon name="chevron" size={10} />
                      </span>
                      <span className="workspace-folder"><Icon name="folder" size={13} /></span>
                      <span className="workspace-name">{workspace.name}</span>
                      {workspace.folder && <span className="workspace-fs">FS</span>}
                      <span className="workspace-count">{allCount}</span>
                    </button>
                    <span className="workspace-actions">
                      <button
                        type="button"
                        className="workspace-action"
                        onClick={() => actions.openFiles(workspace.id)}
                        title={`浏览「${workspace.name}」本地文件`}
                        aria-label={`浏览 ${workspace.name} 文件`}
                      >
                        <Icon name="tasks" size={10} />
                      </button>
                      <button
                        type="button"
                        className="workspace-action"
                        onClick={() => actions.openWelcome(workspace.id)}
                        title={`在「${workspace.name}」新建任务`}
                        aria-label={`在 ${workspace.name} 新建任务`}
                      >
                        <Icon name="plus" size={10} />
                      </button>
                      <button
                        type="button"
                        className="workspace-action danger"
                        onClick={() => setPendingDelete({
                          kind: "workspace",
                          id: workspace.id,
                          name: workspace.name,
                          count: allCount
                        })}
                        disabled={workspaces.length <= 1}
                        title={workspaces.length <= 1 ? "至少保留一个工作区" : `删除工作区「${workspace.name}」`}
                        aria-label={`删除工作区 ${workspace.name}`}
                      >
                        <Icon name="trash" size={10} />
                      </button>
                    </span>
                  </div>
                  {open && (
                    <div className="workspace-tasks">
                      {workspaceTasks.length ? (
                        workspaceTasks.map(renderTask)
                      ) : (
                        <span className="sidebar-empty">暂无任务 · 点 + 新建</span>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
            {query && !filtered.length && <span className="sidebar-empty">没有匹配任务</span>}
          </nav>
        </section>
      </div>

      <div className="sidebar-profile">
        <button type="button" className="profile-main" onClick={() => actions.openSettings("general")} title="打开设置" aria-label="打开设置">
          <span className="profile-avatar"><Icon name="logo" size={15} /></span>
          <span className="profile-copy">
            <b>本地研究者</b>
            <small>v{APP_VERSION} · LOCAL · 演示数据</small>
          </span>
        </button>
        <a className="profile-icon profile-link" href={siteHref()} title="返回站点" aria-label="返回站点">
          <Icon name="globe" size={14} />
        </a>
        <button
          type="button"
          className="profile-icon"
          onClick={() => actions.openSettings("general")}
          title="设置"
          aria-label="设置"
        >
          <Icon name="sliders" size={14} />
        </button>
      </div>

      <input
        ref={(node) => {
          folderInputRef.current = node;
          node?.setAttribute("webkitdirectory", "");
          node?.setAttribute("directory", "");
        }}
        type="file"
        multiple
        className="folder-input"
        onChange={handleFolder}
        aria-hidden="true"
        tabIndex={-1}
      />

      <input
        ref={previewInputRef}
        type="file"
        multiple
        className="folder-input preview-input"
        onChange={handlePreviewFiles}
        aria-hidden="true"
        tabIndex={-1}
      />

      {pendingDelete && createPortal(
        <div
          className="confirm-layer"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setPendingDelete(null);
          }}
        >
          <section className="confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
            <span className="eyebrow">DELETE / LOCAL</span>
            <h3 id="confirm-title">
              {pendingDelete.kind === "task" ? "删除这个任务？" : "删除这个工作区？"}
            </h3>
            <p>
              {pendingDelete.kind === "task"
                ? `「${pendingDelete.name}」的会话、证据与本地状态会一起移除，无法撤销。`
                : `「${pendingDelete.name}」及其中 ${pendingDelete.count} 个任务会一起移除，无法撤销。`}
            </p>
            <div className="confirm-actions">
              <button type="button" className="text-button" onClick={() => setPendingDelete(null)}>取消</button>
              <button type="button" className="solid-button danger" onClick={confirmDelete}>确认删除</button>
            </div>
          </section>
        </div>,
        document.body
      )}
    </aside>
  );
}
