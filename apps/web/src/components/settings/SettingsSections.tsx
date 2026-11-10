import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";
import { probeRuntime } from "../../adapters/runtimeApi";
import {
  APP_VERSION,
  BUILD_DATE,
  FONT_SCALE_OPTIONS,
  clampModel,
  compressionNote,
  formatTokens,
  formatUsageTokens,
  modelProfile,
  thinkingLabel
} from "../../domain/catalog";
import { siteHref } from "../../domain/links";
import { folderStorage, folderStorageFileName } from "../../adapters/folderStorage";
import type { ModelProfile } from "../../domain/types";
import { useAllModelProfiles } from "../../state/modelStore";
import { useFolderStorage } from "../../state/useFolderStorage";
import { selectCurrentTask, useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";
import { ModelBindings } from "./ModelBindings";
import { ModelProviderManager } from "./ModelProviderManager";

export function PageHead({
  eyebrow,
  title,
  description,
  tag
}: {
  eyebrow: string;
  title: string;
  description: string;
  tag?: string;
}) {
  return (
    <div className="settings-page-head">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <div className="settings-heading-line">
          <h1>{title}</h1>
          {tag && <span className="settings-tag">{tag}</span>}
        </div>
        <p>{description}</p>
      </div>
    </div>
  );
}

export function Card({
  title,
  description,
  children,
  className = ""
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`settings-card ${className}`.trim()}>
      <div className="settings-card-head">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

export function GeneralSettings() {
  const preferences = useWorkspaceStore((state) => state.preferences);
  const tasks = useWorkspaceStore((state) => state.tasks);
  const archivedTaskIds = useWorkspaceStore((state) => state.archivedTaskIds);
  const plugins = useWorkspaceStore((state) => state.plugins);
  const actions = useWorkspaceStore((state) => state.actions);
  const totalMessages = tasks.reduce((sum, task) => sum + task.messages.length, 0);
  const activeTaskCount = tasks.filter((task) => !archivedTaskIds.includes(task.id)).length;

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="BASIC / GENERAL"
        title="常规"
        description="工作台行为、人工门与本地状态。所有设置只影响当前浏览器。"
      />

      <Card title="工作台行为" description="这些偏好在任务、模型与插件之间共享。">
        <label className="switch-row settings-switch-row">
          <span><b>自动展开运行中</b><small>运行阶段与进行中对话自动展开</small></span>
          <input
            type="checkbox"
            checked={preferences.autoExpandRunning}
            onChange={(event) => actions.setPreference("autoExpandRunning", event.target.checked)}
          />
        </label>
        <label className="switch-row settings-switch-row">
          <span><b>自动滚动新消息</b><small>关闭后保持当前阅读位置</small></span>
          <input
            type="checkbox"
            checked={preferences.autoScroll}
            onChange={(event) => actions.setPreference("autoScroll", event.target.checked)}
          />
        </label>
      </Card>

      <div className="settings-two-col">
        <Card title="人工门" description="这些约束不可在设置中关闭。">
          <div className="settings-lock-row">
            <Icon name="lock" size={14} />
            <span><b>claim 必须人工签署</b><small>全自动停在 S5b；系统不会自动生成结论。</small></span>
          </div>
          <div className="settings-lock-row">
            <Icon name="lock" size={14} />
            <span><b>closure 未通过时锁定导出</b><small>写作槽位与导出保持 pending。</small></span>
          </div>
        </Card>
        <Card title="本地状态" description="STATIC adapter · localStorage。">
          <div className="settings-kv-list">
            <div><span>任务</span><b>{activeTaskCount} active · {archivedTaskIds.length} archived</b></div>
            <div><span>消息</span><b>{totalMessages}</b></div>
            <div><span>连接器</span><b>{plugins.length} registered</b></div>
          </div>
        </Card>
      </div>
    </div>
  );
}

export function AppearanceSettings() {
  const preferences = useWorkspaceStore((state) => state.preferences);
  const actions = useWorkspaceStore((state) => state.actions);

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="BASIC / APPEARANCE"
        title="外观"
        description="字体大小与动效。字体缩放只影响文字，不改变三栏结构和卡片宽度。"
      />

      <Card title="页面字体大小" description="选择一档后立即应用；设置保存在当前浏览器。">
        <div className="font-size-control settings-font-control">
          <div className="font-size-head">
            <span>当前缩放</span>
            <b>{Math.round(preferences.fontScale * 100)}%</b>
          </div>
          <div className="font-size-options" role="group" aria-label="页面字体大小">
            {FONT_SCALE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={preferences.fontScale === option.value}
                className={preferences.fontScale === option.value ? "is-on" : ""}
                onClick={() => actions.setPreference("fontScale", option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="font-preview" aria-hidden="true">
            Aa 证据链 · Claim / Gate · Run 09
          </div>
          <small>90% / 100% / 110% / 120% · 只调整文字大小，不改变图标与布局。</small>
        </div>
        <label className="switch-row settings-switch-row">
          <span><b>减少动效</b><small>关闭入场、脉冲与过渡动画，保留状态文字。</small></span>
          <input
            type="checkbox"
            checked={preferences.reduceMotion}
            onChange={(event) => actions.setPreference("reduceMotion", event.target.checked)}
          />
        </label>
      </Card>

      <Card title="主题" description="静态工作台当前只有一套淡蓝主题。">
        <div className="settings-theme-row">
          <span className="theme-swatch" />
          <span><b>淡蓝证据工作台</b><small>白卡、细线、等宽标签；不引入第二套暗色主题。</small></span>
          <span className="quiet-chip">DEFAULT</span>
        </div>
      </Card>
    </div>
  );
}

export function ModelSettingsPage() {
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const profiles = useAllModelProfiles();
  const profile = task ? modelProfile(task.model) : null;
  const usage = task && profile
    ? task.usage[profile.id] ?? { prompt: 0, completion: 0, requests: 0 }
    : { prompt: 0, completion: 0, requests: 0 };

  const selectProfile = (next: ModelProfile) => {
    if (!task) return;
    const maxReply = Math.min(task.model.maxReply, next.maxOutput);
    actions.saveModel(clampModel({
      ...task.model,
      profileId: next.id,
      contextLimit: Math.min(task.model.contextLimit, next.contextWindow),
      maxReply,
      thinkingStop: next.kind === "unsupported" ? null : next.defaultStop
    }));
    actions.notify(`已切换到 ${next.short}；新消息记到该模型`);
  };

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="BASIC / MODEL"
        title="模型设置"
        description="模型能力来自 Profile 声明；用量与上下文策略只保存在本地任务。"
      />

      {task && profile && <Card title="当前任务模型" description={`${task.name} · 切换模型只影响之后的新消息`}>
        <div className="settings-profile-grid">
          {profiles.map((item) => {
            const itemUsage = task.usage[item.id] ?? { prompt: 0, completion: 0, requests: 0 };
            const active = item.id === task.model.profileId;
            return (
              <button
                key={item.id}
                type="button"
                className={`settings-profile-card${active ? " is-on" : ""}`}
                onClick={() => selectProfile(item)}
                aria-pressed={active}
              >
                <span className="settings-profile-name">
                  <b>{item.short}</b>
                  {active && <em>CURRENT</em>}
                </span>
                <small>{item.provider}</small>
                <span className="settings-profile-meta">{formatTokens(item.contextWindow)} ctx · {formatTokens(item.maxOutput)} out</span>
                <span className="settings-profile-usage">
                  {formatUsageTokens(itemUsage.prompt + itemUsage.completion)} tokens
                </span>
              </button>
            );
          })}
        </div>

        <div className="settings-kv-grid">
          <div><span>最大上下文</span><b>{formatTokens(task.model.contextLimit)}</b></div>
          <div><span>最大回复</span><b>{formatTokens(task.model.maxReply)}</b></div>
          <div><span>思考强度</span><b>{thinkingLabel(task.model)}</b></div>
          <div><span>上下文压缩</span><b>{task.model.compression}</b></div>
        </div>
        <p className="settings-note">{compressionNote(task.model)}</p>
        <p className="settings-note">
          本任务 {profile.short}：{formatUsageTokens(usage.prompt)} in · {formatUsageTokens(usage.completion)} out · {usage.requests} requests
        </p>

        <div className="settings-actions">
          <button type="button" className="settings-btn primary" onClick={() => actions.openOverlay("modelOpen")}>
            细调上下文与思考
          </button>
          <a className="settings-btn" href={siteHref("models/")} target="_blank" rel="noopener noreferrer">
            Provider / Profile <Icon name="external" size={11} />
          </a>
        </div>
      </Card>}

      <ModelProviderManager />

      <ModelBindings />

      <Card title="能力边界" description="模型设置不能突破服务端声明的能力。">
        <div className="settings-boundary">
          <Icon name="shield" size={14} />
          <span>
            Anthropic thinking budget 必须小于最大回复长度；未声明思考能力的模型滑块保持禁用。
            真实 API 密钥不会进入浏览器，本页只修改本地预算。
          </span>
        </div>
      </Card>
    </div>
  );
}

export function PluginsSettingsPage() {
  const task = useWorkspaceStore(selectCurrentTask);
  const plugins = useWorkspaceStore((state) => state.plugins);
  const actions = useWorkspaceStore((state) => state.actions);

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="AGENT / TOOLS"
        title="插件与 MCP"
        description="连接器按任务启用；工具结果进入会话前必须逐次批准。当前没有真实 transport。"
      />

      <Card title="已登记连接器" description="静态配置；OAuth 与 token 只应留在 runtime。">
        <div className="settings-plugin-list">
          {plugins.map((plugin) => {
            const enabled = task?.plugins.includes(plugin.id) ?? false;
            return (
              <div className={`settings-plugin-row${enabled ? " is-on" : ""}`} key={plugin.id}>
                <span className="settings-plugin-icon"><Icon name="terminal" size={15} /></span>
                <span className="settings-plugin-copy">
                  <b>{plugin.name}</b>
                  <small>{plugin.transport} · {plugin.auth} · {plugin.readonly ? "read-only" : "writable"}</small>
                  <span className="settings-plugin-toolsets">
                    {plugin.toolsets.map((tool) => <em key={tool}>{tool}</em>)}
                  </span>
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={enabled}
                  className={`switch${enabled ? " is-on" : ""}`}
                  onClick={() => actions.togglePlugin(plugin.id)}
                  aria-label={`${enabled ? "停用" : "启用"} ${plugin.name}`}
                >
                  <i />
                </button>
              </div>
            );
          })}
        </div>
        <div className="settings-actions">
          <button type="button" className="settings-btn primary" onClick={() => actions.openOverlay("pluginsOpen")}>
            打开审批抽屉
          </button>
          <button type="button" className="settings-btn" onClick={actions.proposeToolCall}>
            提议只读调用
          </button>
        </div>
      </Card>

      <Card title="待处理工具调用" description="只读结果也会被视为 UNTRUSTED。">
        {task?.toolCalls.length ? (
          <div className="settings-toolcall-list">
            {task.toolCalls.map((call) => (
              <div className={`settings-toolcall${call.status === "proposed" ? " is-pending" : ""}`} key={call.id}>
                <div className="settings-toolcall-head">
                  <span><Icon name="terminal" size={12} />{call.server} · <code>{call.tool}</code></span>
                  <span className={`badge ${call.status === "approved" ? "ok" : call.status === "denied" ? "bad" : "warn"}`}>
                    {call.status}
                  </span>
                </div>
                <small>{call.args}</small>
                {call.result && <p>{call.result}</p>}
                {call.status === "proposed" && (
                  <div className="settings-actions compact">
                    <button type="button" className="settings-btn primary" onClick={() => actions.approveToolCall(call.id)}>批准结果</button>
                    <button type="button" className="settings-btn danger" onClick={() => actions.denyToolCall(call.id)}>拒绝</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="settings-empty">还没有工具调用。启用 GitHub MCP 后可在此审批。</p>
        )}
      </Card>
    </div>
  );
}

export function EvolutionSettingsPage() {
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  if (!task) return null;
  const candidate = task.evolution.candidate;
  const status = candidate?.status;

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="AGENT / EVOLUTION"
        title="自进化"
        description="只对策略层提案；claim、evidence、gate、rubric、export、signature 不可写。"
      />

      <Card title="候选与租约" description={`状态：${task.evolution.status}`}>
        {candidate ? (
          <>
            <div className="settings-evo-head">
              <Icon name="spark" size={15} />
              <b>{candidate.id}</b>
              <span className={`badge ${status === "active" ? "ok" : status === "rejected" ? "bad" : "warn"}`}>{status}</span>
            </div>
            <div className="settings-kv-grid">
              <div><span>Target</span><b>{candidate.target}</b></div>
              <div><span>Lease</span><b>{candidate.lease}</b></div>
              <div><span>Evidence</span><b>{candidate.evidence}</b></div>
              <div><span>Predicted</span><b>{candidate.predicted}</b></div>
            </div>
            <p className="settings-note">{candidate.patch}</p>
            <div className="settings-actions">
              {status === "pending" && (
                <>
                  <button type="button" className="settings-btn primary" onClick={actions.approveCandidate}>批准候选</button>
                  <button type="button" className="settings-btn danger" onClick={actions.rejectCandidate}>拒绝并保留负结果</button>
                </>
              )}
              {status === "active" && (
                <button type="button" className="settings-btn danger" onClick={actions.rollbackHarness}>撤销租约并回滚</button>
              )}
            </div>
          </>
        ) : (
          <div className="settings-empty-card">
            <Icon name="evolution" size={22} />
            <p>还没有候选。运行全自动到 META 阶段，或在这里生成一个静态候选查看准入流程。</p>
            <button type="button" className="settings-btn primary" onClick={actions.previewCandidate}>模拟生成候选</button>
          </div>
        )}
        <div className="settings-actions">
          <button
            type="button"
            className="settings-btn"
            onClick={() => {
              actions.closeSettings();
              actions.setContextTab("evolution");
            }}
          >
            打开工作台 EVOLUTION <Icon name="arrow" size={11} />
          </button>
        </div>
      </Card>

      <Card title="不可写面" description="RSI 不能修改这些对象。">
        <div className="settings-surface-list">
          {["claim", "evidence", "gate", "rubric", "export", "signature"].map((surface) => (
            <span key={surface}><Icon name="lock" size={11} />{surface}</span>
          ))}
        </div>
      </Card>
    </div>
  );
}

export function DataSettingsPage() {
  const tasks = useWorkspaceStore((state) => state.tasks);
  const archivedTaskIds = useWorkspaceStore((state) => state.archivedTaskIds);
  const plugins = useWorkspaceStore((state) => state.plugins);
  const actions = useWorkspaceStore((state) => state.actions);
  const storage = useFolderStorage();
  const importRef = useRef<HTMLInputElement>(null);
  const [storageBusy, setStorageBusy] = useState("");
  const totalMessages = tasks.reduce((sum, task) => sum + task.messages.length, 0);
  const usageDays = tasks.reduce((sum, task) => sum + Object.keys(task.usageDays ?? {}).length, 0);
  const activeTaskCount = tasks.filter((task) => !archivedTaskIds.includes(task.id)).length;

  const chooseFolder = async () => {
    setStorageBusy("choose");
    try {
      await folderStorage.choose();
      actions.notify("已选择本地文件夹；当前工作区已写入 workspace.json");
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : "选择本地文件夹失败");
    } finally {
      setStorageBusy("");
    }
  };

  const saveNow = async () => {
    setStorageBusy("save");
    try {
      const savedAt = await folderStorage.saveNow();
      actions.notify(savedAt ? "工作区已写入本地文件夹" : "没有可写入的数据，或文件夹权限已失效");
    } finally {
      setStorageBusy("");
    }
  };

  const restore = async () => {
    setStorageBusy("restore");
    try {
      const snapshot = await folderStorage.restore();
      if (!snapshot) {
        actions.notify("文件夹中没有 workspace.json");
        return;
      }
      actions.hydrateSnapshot(snapshot);
    } catch (error) {
      actions.notify(error instanceof Error ? error.message : "从文件夹恢复失败");
    } finally {
      setStorageBusy("");
    }
  };

  const importJson = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const snapshot = JSON.parse(await file.text());
      actions.hydrateSnapshot(snapshot, false, "已从 JSON 恢复工作区");
    } catch {
      actions.notify("导入失败：不是有效的工作区 JSON");
    }
  };

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="DATA / STORAGE"
        title="数据与备份"
        description="默认写入浏览器 localStorage；可以改用本地文件夹作为主副本，或导出/导入完整工作区 JSON。"
      />

      <Card
        title="存储位置"
        description="选择一个本地文件夹后，应用只写 workspace.json 与 storage.json，不扫描其他文件。"
      >
        <div className="storage-choice">
          <div className={`storage-option${storage.active ? "" : " is-on"}`}>
            <span className="storage-option-icon"><Icon name="database" size={15} /></span>
            <div><b>浏览器本地</b><small>localStorage · 默认 · 无权限弹窗</small></div>
            <span className="settings-state" data-state={storage.active ? "draft" : "ok"}>
              {storage.active ? "CACHE" : "ACTIVE"}
            </span>
          </div>
          <div className={`storage-option${storage.active ? " is-on" : ""}`}>
            <span className="storage-option-icon"><Icon name="folder" size={15} /></span>
            <div><b>本地文件夹</b><small>workspace.json · File System Access</small></div>
            <span className="settings-state" data-state={storage.active ? "ok" : storage.supported ? "draft" : "offline"}>
              {storage.active ? "ACTIVE" : storage.supported ? "OPTIONAL" : "UNSUPPORTED"}
            </span>
          </div>
        </div>

        {storage.active || storage.needsPermission ? (
          <div className="storage-kv">
            <div><span>文件夹</span><b>{storage.folderName || "已记录目录句柄"}</b></div>
            <div><span>工作区文件</span><b className="storage-path">{folderStorageFileName}</b></div>
            <div><span>最近写入</span><b>{storage.lastSavedAt ? storage.lastSavedAt.slice(0, 16).replace("T", " ") : "尚未写入"}</b></div>
          </div>
        ) : (
          <p className="settings-note">
            {storage.supported
              ? "选择文件夹后，当前工作区会立即写入；刷新页面会尝试从该文件夹恢复。"
              : "当前浏览器不支持文件夹直写。你仍可使用下方导出/导入 JSON。"}
          </p>
        )}

        {storage.error && <p className="storage-warning">{storage.error}</p>}
        {!storage.active && storage.needsPermission && (
          <p className="storage-warning">文件夹权限需要重新确认；点击“重新连接并恢复”后再写入。</p>
        )}

        <div className="settings-actions storage-actions">
          {storage.supported && !storage.active && (
            <button type="button" className="settings-btn primary" onClick={() => void chooseFolder()} disabled={Boolean(storageBusy)}>
              <Icon name="folder" size={12} />{storageBusy === "choose" ? "选择中…" : "选择本地文件夹"}
            </button>
          )}
          {(storage.active || storage.needsPermission) && (
            <button type="button" className="settings-btn primary" onClick={() => void restore()} disabled={Boolean(storageBusy)}>
              <Icon name="refresh" size={12} />{storageBusy === "restore" ? "恢复中…" : "重新连接并恢复"}
            </button>
          )}
          {storage.active && (
            <button type="button" className="settings-btn" onClick={() => void saveNow()} disabled={Boolean(storageBusy)}>
              <Icon name="download" size={12} />{storageBusy === "save" ? "写入中…" : "立即保存到文件夹"}
            </button>
          )}
          {(storage.active || storage.needsPermission) && (
            <button type="button" className="settings-btn danger" onClick={() => void folderStorage.disconnect()}>
              断开文件夹
            </button>
          )}
          <button type="button" className="settings-btn" onClick={() => importRef.current?.click()}>
            <Icon name="paperclip" size={12} />导入工作区 JSON
          </button>
        </div>

        <p className="settings-note">
          双写策略：文件夹是主副本，localStorage 保留启动缓存和权限失败时的回退。断开文件夹不会删除磁盘上的 workspace.json。
        </p>
        <input ref={importRef} type="file" accept="application/json,.json" className="folder-input storage-import" onChange={importJson} aria-hidden="true" tabIndex={-1} />
      </Card>

      <div className="settings-stat-row is-five">
        <div><b>{activeTaskCount}</b><span>活跃任务</span></div>
        <div><b>{archivedTaskIds.length}</b><span>已归档</span></div>
        <div><b>{totalMessages}</b><span>消息</span></div>
        <div><b>{usageDays}</b><span>用量日</span></div>
        <div><b>{plugins.length}</b><span>连接器</span></div>
      </div>

      <Card title="导出与重置" description="导出包含任务、证据、模型用量与每日 usage。">
        <div className="settings-actions">
          <button type="button" className="settings-btn primary" onClick={actions.exportWorkspace}>
            <Icon name="download" size={12} />导出工作区 JSON
          </button>
          <button
            type="button"
            className="settings-btn danger"
            onClick={() => {
              if (window.confirm("重置会清空本地示例状态，确定继续？")) {
                actions.resetWorkspace();
              }
            }}
          >
            <Icon name="trash" size={12} />重置为示例
          </button>
        </div>
        <p className="settings-note">
          导出文件名形如 <code>research-agent-workspace-YYYY-MM-DD.json</code>；刷新不会上传任何内容。
        </p>
      </Card>

      <Card title="状态边界" description="存储位置的职责范围。">
        <div className="settings-boundary">
          <Icon name="shield" size={14} />
          <span>工作区快照只写入 workspace.json；不包含 API 密钥，不读取文件夹中的其他文件。演示数据、模型设置与 usageDays 仍不调用 API、不生成真实 claim、不执行真实实验。</span>
        </div>
      </Card>
    </div>
  );
}

export function GuideSettingsPage() {
  const actions = useWorkspaceStore((state) => state.actions);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);

  const requireSession = () => {
    if (!welcomeOpen) return true;
    actions.notify("先开始一个会话，再执行这一步");
    return false;
  };

  const steps = [
    {
      title: "新建一个任务",
      text: "命名目标并选择工作区；所有任务都会出现在左侧工作区树。",
      action: "新建任务",
      run: () => actions.openOverlay("newTaskOpen")
    },
    {
      title: "从调研开始",
      text: "先生成检索计划与 span/gap，再把 gap 送入实验设计。",
      action: "进入调研",
      run: () => {
        if (!requireSession()) return;
        actions.closeSettings();
        actions.setMode("research");
        actions.focusComposer();
      }
    },
    {
      title: "运行受治理全自动",
      text: "S1→META 连续执行，在 claim 人工门暂停；输入指导会在下一阶段边界生效。",
      action: "启动全自动",
      run: () => {
        if (!requireSession()) return;
        actions.closeSettings();
        actions.startAuto();
      }
    },
    {
      title: "签署与回看",
      text: "claim 由人在终端签署；工作台只显示 CLI 命令、检查 closure，并在 EVOLUTION 批准或回滚候选。",
      action: "查看证据链",
      run: () => {
        if (!requireSession()) return;
        actions.closeSettings();
        actions.setContextTab("evidence");
      }
    },
    {
      title: "绑定写作槽位",
      text: "把已签 claim、冻结协议与图 manifest 绑到写作槽位；缺证据的槽位保持 locked。",
      action: "进入写作",
      run: () => {
        if (!requireSession()) return;
        actions.closeSettings();
        actions.setMode("writing");
        actions.focusComposer();
      }
    },
    {
      title: "选择访问级别",
      text: "在输入框左下选择只读 / 每次询问 / 完全访问；高权限动作会按级别拦截或弹窗确认。",
      action: "返回工作台",
      run: () => actions.closeSettings()
    },
    {
      title: "调用或创建 Skill",
      text: "输入 /skill-id 调用技能，或打开 SKILLS 面板创建只读检查技能。",
      action: "打开 Skills",
      run: () => {
        actions.closeSettings();
        actions.openOverlay("skillsOpen");
      }
    },
    {
      title: "自定义快捷键",
      text: "在设置 → 快捷键录制组合键；冲突会拒绝保存，Backspace 恢复当前项默认。",
      action: "打开快捷键",
      run: () => actions.setSettingsSection("shortcuts")
    }
  ];

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="SUPPORT / GUIDE"
        title="快速引导"
        description="工作台是对话式控制面；全自动仍要停在人工门。"
      />
      <div className="settings-guide-list">
        {steps.map((step, index) => (
          <div className="settings-guide-step" key={step.title}>
            <span className="guide-index">{String(index + 1).padStart(2, "0")}</span>
            <span className="guide-copy"><b>{step.title}</b><small>{step.text}</small></span>
            <button type="button" className="settings-btn" onClick={step.run}>{step.action}</button>
          </div>
        ))}
      </div>
      <p className="settings-inline-note">引导步骤使用本地演示状态；真实 pipeline 请用 /live 或 RUN 面板的「运行任务」。人工门只在本地 CLI 完成，浏览器不会代为签署。</p>
    </div>
  );
}

export function AboutSettingsPage() {
  const [runtime, setRuntime] = useState<"checking" | "connected" | "offline" | "static">(
    "checking"
  );
  useEffect(() => {
    if (__STATIC_ONLY__) {
      setRuntime("static");
      return;
    }
    let cancelled = false;
    probeRuntime()
      .then(() => {
        if (!cancelled) setRuntime("connected");
      })
      .catch(() => {
        if (!cancelled) setRuntime("offline");
      });
    return () => {
      cancelled = true;
    };
  }, []);
  const runtimeLabel =
    runtime === "connected"
      ? "connected · local"
      : runtime === "static"
        ? "disabled in static build"
        : runtime === "checking"
          ? "checking…"
          : "not connected";

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="SUPPORT / ABOUT"
        title="关于与边界"
        description="Research Agent Workspace · 证据闭合的对话式科研工作台。"
      />

      <Card title="版本" description="静态工作台与部署信息。">
        <div className="settings-kv-list">
          <div><span>Workspace</span><b>v{APP_VERSION}</b></div>
          <div><span>Build</span><b>{BUILD_DATE}</b></div>
          <div><span>Adapter</span><b>STATIC · localStorage</b></div>
          <div><span>Runtime</span><b>{runtimeLabel}</b></div>
        </div>
      </Card>

      <Card title="不可宣称" description="这个版本能演示什么，不能声称什么。">
        <ul className="settings-boundary-list">
          <li>人工门（approve / claim / sign / freeze / publish）不在浏览器执行；页面只显示终端命令。</li>
          <li>fixture 与演示数值不构成研究证据；结果数值须来自 runtime 产物并经 CLI 人签。</li>
          <li>静态构建在编译期禁用 runtime，页面只展示快照与本地状态（见顶部模式提示）。</li>
          <li>模型设置不改变服务端能力，也不会把密钥写入浏览器。</li>
        </ul>
      </Card>

      <Card title="相关入口" description="这些是子页面，不是日常工作流。">
        <div className="settings-link-grid">
          <a href={siteHref("models/")} target="_blank" rel="noopener noreferrer">
            <Icon name="cpu" size={14} />
            <span><b>Provider / Profile</b><small>高级模型接入</small></span>
            <Icon name="external" size={11} />
          </a>
          <a href={siteHref("live/")} target="_blank" rel="noopener noreferrer">
            <Icon name="play" size={14} />
            <span><b>运行控制台</b><small>runtime / SSE</small></span>
            <Icon name="external" size={11} />
          </a>
        </div>
      </Card>
    </div>
  );
}
