import { useEffect, useRef } from "react";
import { APP_VERSION, BUILD_DATE } from "../../domain/catalog";
import type { SettingsSection } from "../../domain/types";
import { usePreviewStore } from "../../state/previewStore";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";
import type { IconName } from "../Icon";
import { LineagePage } from "./LineagePage";
import { ShortcutSettingsPage } from "./ShortcutSettings";
import { UsageStats } from "./UsageStats";
import { FeedbackModeSettings } from "./FeedbackModeSettings";
import {
  AgentsSettingsPage,
  ArchiveSettingsPage,
  CommandsSettingsPage,
  MemorySettingsPage,
  RuntimeSettingsPage
} from "./WorkspaceSettings";
import {
  AboutSettingsPage,
  AppearanceSettings,
  DataSettingsPage,
  EvolutionSettingsPage,
  GeneralSettings,
  GuideSettingsPage,
  ModelSettingsPage,
  PluginsSettingsPage
} from "./SettingsSections";

const NAV_GROUPS: Array<{
  label: string;
  items: Array<{ id: SettingsSection; label: string; icon: IconName }>;
}> = [
  {
    label: "基础设置",
    items: [
      { id: "general", label: "常规", icon: "sliders" },
      { id: "appearance", label: "外观", icon: "eye" },
      { id: "shortcuts", label: "快捷键", icon: "command" },
      { id: "commands", label: "命令", icon: "terminal" },
      { id: "model", label: "模型设置", icon: "cpu" }
    ]
  },
  {
    label: "Agent 能力",
    items: [
      { id: "memory", label: "记忆", icon: "book" },
      { id: "agents", label: "子智能体", icon: "bot" },
      { id: "plugins", label: "插件与 MCP", icon: "grid" },
      { id: "evolution", label: "自进化", icon: "evolution" }
    ]
  },
  {
    label: "运行与证据",
    items: [
      { id: "runtime", label: "执行环境", icon: "globe" },
      { id: "usage", label: "使用统计", icon: "chart" },
      { id: "lineage", label: "证据沿袭", icon: "branch" }
    ]
  },
  {
    label: "数据与归档",
    items: [
      { id: "archive", label: "归档管理", icon: "database" },
      { id: "data", label: "数据与备份", icon: "database" }
    ]
  },
  {
    label: "支持",
    items: [
      { id: "guide", label: "快速引导", icon: "compass" },
      { id: "about", label: "关于与边界", icon: "info" }
    ]
  }
];

const SECTION_META: Record<SettingsSection, { group: string; label: string }> = NAV_GROUPS.reduce(
  (meta, group) => {
    for (const item of group.items) meta[item.id] = { group: group.label, label: item.label };
    return meta;
  },
  {} as Record<SettingsSection, { group: string; label: string }>
);

const TASK_SECTIONS = new Set<SettingsSection>(["plugins", "evolution"]);

function SectionContent({ section }: { section: SettingsSection }) {
  switch (section) {
    case "general":
      return <GeneralSettings />;
    case "appearance":
      return <AppearanceSettings />;
    case "shortcuts":
      return <ShortcutSettingsPage />;
    case "model":
      return <ModelSettingsPage />;
    case "memory":
      return (
        <>
          <MemorySettingsPage />
          <FeedbackModeSettings />
        </>
      );
    case "agents":
      return <AgentsSettingsPage />;
    case "commands":
      return <CommandsSettingsPage />;
    case "plugins":
      return <PluginsSettingsPage />;
    case "evolution":
      return <EvolutionSettingsPage />;
    case "runtime":
      return <RuntimeSettingsPage />;
    case "usage":
      return <UsageStats />;
    case "lineage":
      return <LineagePage />;
    case "archive":
      return <ArchiveSettingsPage />;
    case "data":
      return <DataSettingsPage />;
    case "guide":
      return <GuideSettingsPage />;
    case "about":
      return <AboutSettingsPage />;
  }
}

export function SettingsPage() {
  const section = useWorkspaceStore((state) => state.ui.settingsSection);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);
  const origin = useWorkspaceStore((state) => state.ui.settingsOrigin);
  const actions = useWorkspaceStore((state) => state.actions);
  const scrollRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const activeSection = welcomeOpen && TASK_SECTIONS.has(section) ? "general" : section;
  const meta = SECTION_META[activeSection];
  const backLabel = origin.kind === "welcome" ? "返回欢迎页" : `返回任务 · ${origin.label}`;

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: 0, behavior: "auto" });
    navRef.current
      ?.querySelector<HTMLElement>(".settings-nav-item.is-on")
      ?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [activeSection]);

  useEffect(() => {
    usePreviewStore.getState().close();
  }, []);

  return (
    <div className="settings-page" role="dialog" aria-modal="true" aria-label="设置">
      <header className="settings-titlebar">
        <button
          type="button"
          className="settings-titlebar-brand settings-return"
          onClick={actions.closeSettings}
          aria-label={backLabel}
          title={backLabel}
        >
          <span className="settings-return-arrow"><Icon name="arrow" size={13} /></span>
          <span className="settings-brand-mark"><Icon name="logo" size={17} /></span>
          <b>Research Agent</b>
          <em>SETTINGS</em>
        </button>
        <div className="settings-titlebar-actions">
          <span className="settings-badge">LOCAL · WORKSPACE</span>
          <button
            type="button"
            className="icon-button settings-close"
            onClick={actions.closeSettings}
            aria-label="关闭设置"
          >
            <Icon name="close" size={14} />
          </button>
        </div>
      </header>

      <div className="settings-body">
        <aside className="settings-nav" aria-label="设置分组">
          <button type="button" className="settings-back" onClick={actions.closeSettings} aria-label={backLabel} title={backLabel}>
            <span className="settings-back-arrow"><Icon name="arrow" size={13} /></span>
            <span className="settings-back-label">{backLabel}</span>
          </button>
          <nav className="settings-nav-scroll" ref={navRef}>
            {NAV_GROUPS.map((group) => {
              const items = welcomeOpen
                ? group.items.filter((item) => !TASK_SECTIONS.has(item.id))
                : group.items;
              if (!items.length) return null;
              return (
                <div className="settings-nav-group" key={group.label}>
                  <span className="settings-nav-label">{group.label}</span>
                  <div className="settings-nav-items">
                    {items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`settings-nav-item${activeSection === item.id ? " is-on" : ""}`}
                        onClick={() => actions.setSettingsSection(item.id)}
                        aria-current={activeSection === item.id ? "page" : undefined}
                      >
                        <Icon name={item.icon} size={14} />
                        <span>{item.label}</span>
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </nav>
          <div className="settings-nav-foot">
            <span>LOCAL WORKSPACE</span>
            <b>v{APP_VERSION}</b>
            <small>{BUILD_DATE} · STATIC ADAPTER</small>
            {welcomeOpen && <small>模型 / 插件 / 自进化将在会话内开放</small>}
          </div>
        </aside>

        <main className="settings-main">
          <div className="settings-scroll" ref={scrollRef}>
            <div className="settings-content">
              <div className="settings-breadcrumb">
                <span>{meta.group}</span>
                <i>/</i>
                <span>{meta.label}</span>
              </div>
              <SectionContent section={activeSection} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
