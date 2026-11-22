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
import { compareEmpiricalTasks, compareMethodProfiles } from "../../domain/taskCompare";
import {
  blockerCount,
  evidenceProfileFor,
  fitMap,
  iterationLabel,
  loadMethodRegistry,
  loadOrchestrationPlans,
  loadStrategySpace,
  recommendMethods,
  stagePlanFor,
  tagAnalysis,
  validityName,
  type MethodRecommendation,
  type MethodRegistryData,
  type OrchestrationPlansData,
  type StrategySpaceData
} from "../../domain/methodModel";
import {
  COMPOSITIONS,
  COMPOSITION_ORDER,
  validateComposition
} from "../../domain/composition";
import { ELEMENTS, isHumanElement } from "../../domain/elementGraph";
import { siteHref } from "../../domain/links";
import { folderStorage, folderStorageFileName } from "../../adapters/folderStorage";
import type { ModelProfile } from "../../domain/types";
import { useAllModelProfiles } from "../../state/modelStore";
import { useFolderStorage } from "../../state/useFolderStorage";
import { selectCurrentTask, useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";
import { ConfirmDialog } from "../ConfirmDialog";
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
  const [pendingReset, setPendingReset] = useState(false);
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
            onClick={() => setPendingReset(true)}
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
      <ConfirmDialog
        open={pendingReset}
        eyebrow="RESET / LOCAL"
        title="重置为示例？"
        body="本地演示状态（含你写入的记忆与归档改动）将被清空并重新播种；不会影响 claim / EA / 门禁。此操作无法撤销。"
        confirmLabel="重置"
        onConfirm={() => { actions.resetWorkspace(); setPendingReset(false); }}
        onCancel={() => setPendingReset(false)}
      />
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
      title: "一键演示完整流程",
      text: "回放教学版九阶段（S1→META）：自动逐步揭示、S5b 停在人工门、可切真实闭环版；不调用模型、不写盘、不生成签名。",
      action: "播放演示",
      run: () => {
        actions.closeSettings();
        actions.startDemoPlayer("teaching");
      }
    },
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

/**
 * 方法模型（design/149）： ten governance slots × nine research methods, from
 * the method registry EXPORTED AS DATA (workspace export -> method-registry.json).
 * This page renders the 共性/差异 split the thesis asks for: the slots and their
 * governance never move; what changes per method is where it fits, which
 * protocol fields it must freeze, and what it cannot support.
 */
export function MethodModelSettingsPage() {
  const tasks = useWorkspaceStore((state) => state.tasks);
  const [registry, setRegistry] = useState<MethodRegistryData | null>(null);
  const [strategySpace, setStrategySpace] = useState<StrategySpaceData | null>(null);
  const [orchestration, setOrchestration] = useState<OrchestrationPlansData | null>(null);
  const [missing, setMissing] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [brief, setBrief] = useState("");
  const [recommendation, setRecommendation] = useState<MethodRecommendation | null>(null);
  // design/159: 任务卡矩阵视图 — the advisor's 阶段×方法 two-dimensional model
  // rendered as data (cross cells = 方法论约束下的阶段性任务 from stage_tasks).
  const [taskMatrixView, setTaskMatrixView] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void loadMethodRegistry().then((data) => {
      if (cancelled) return;
      if (data) {
        setRegistry(data);
        setSelected(data.methods[0]?.id ?? null);
      } else {
        setMissing(true);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    let cancelled = false;
    void loadStrategySpace().then((data) => {
      if (!cancelled) setStrategySpace(data);
    });
    void loadOrchestrationPlans().then((data) => {
      if (!cancelled) setOrchestration(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  if (missing) {
    return (
      <div className="settings-section-body">
        <PageHead
          eyebrow="EVIDENCE / METHOD MODEL"
          title="方法模型"
          description="方法注册表快照缺失：运行 python -m research_agent workspace export 重新导出 method-registry.json。"
        />
      </div>
    );
  }
  if (!registry) {
    return (
      <div className="settings-section-body">
        <PageHead eyebrow="EVIDENCE / METHOD MODEL" title="方法模型" description="正在载入方法注册表…" />
      </div>
    );
  }

  const active = registry.methods.find((method) => method.id === selected) ?? registry.methods[0];
  // Cross-task comparison: the same governance slots instantiated by different
  // empirical tasks (design/150). Derived from each task's own fields.
  const compareRows = compareEmpiricalTasks(tasks, registry);
  const methodContrast = compareMethodProfiles(registry);
  // 标签化梳理 (design/155): the reproducible commonality/difference extraction.
  const tags = tagAnalysis(registry);
  const compositionList = registry.compositions ?? COMPOSITION_ORDER.map((id) => COMPOSITIONS[id]);

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="EVIDENCE / METHOD MODEL"
        title="方法模型"
        description="十个治理槽位对所有方法不变；每种方法声明它落在哪些槽位、要冻结哪些协议字段、不能支持什么——模型驱动复用，不为每种方法单设流程。"
      />

      <div className="settings-callout">
        <b>注册表边界</b>
        <p>{registry.boundary}</p>
      </div>

      <div className="settings-card variance-card">
        <div className="settings-card-title">变与不变控制表</div>
        <p className="method-contrast-note" style={{ margin: "0 0 8px" }}>
          框架不是固定的，也不是无界的——每个维度由谁控制、能变到什么程度，都在这张表上。
          控制层级：治理语义（代码+SPEC，L3）→ 方法数据（注册表+租约，L2）→ 任务实例（runtime）。
        </p>
        <div className="variance-table">
          <div className="variance-head">
            <span>维度</span>
            <span className="is-fixed">不变（治理语义）</span>
            <span className="is-method">随方法变（注册表数据）</span>
            <span className="is-content">随内容变（任务实例）</span>
          </div>
          <div className="variance-row">
            <b>治理槽位与门</b>
            <span>槽位语义与门位置固定</span>
            <span>方法声明核心槽位（fit）</span>
            <span>实际走过的槽位</span>
          </div>
          <div className="variance-row">
            <b>证据形态</b>
            <span>可固定 / 可复算 / 可核查（抽象要求）</span>
            <span>RunCapsule、应答集、语料快照…（具体形态）</span>
            <span>本次执行的产物</span>
          </div>
          <div className="variance-row">
            <b>流程顺序</b>
            <span>端口依赖推导（拓扑）</span>
            <span>组合接线（验证式 / 探索式）</span>
            <span>实际执行记录</span>
          </div>
          <div className="variance-row">
            <b>主张</b>
            <span>claim 三元组（主张+依据+范围）</span>
            <span>cannot_support 能力边界</span>
            <span>本次的 statement 与范围</span>
          </div>
          <div className="variance-row">
            <b>自改进</b>
            <span>租约 + 门 + 人签（治理不变）</span>
            <span>方法/矩阵/组合的修订提案</span>
            <span>过程经验与教训</span>
          </div>
        </div>
        <small className="method-contrast-note">
          每格的控制者不同：治理语义由代码与 SPEC 强制（不可经前端修改）；
          方法数据经组合提案租约修订（L2）；任务实例由 runtime 产生（L1 只读投影）。
        </small>
      </div>

      <div className="settings-card essence-card">
        <div className="settings-card-title">研究的本质 · 原模型</div>
        <p className="essence-def">
          <b>研究是在公共可核查的约束下，把一个问题转成能判别候选答案的证据，再把证据转成经审查、带范围的主张，并积累进公共知识的循环。</b>
          方法的差异不在步骤多少，而在三个变量：证据<b>类型</b>、证据的<b>判别力</b>、主张的<b>有效范围</b>。
        </p>
        <div className="essence-triad">
          <div className="essence-layer">
            <b>主张层</b>
            <span>ClaimRecord：可检验的话 + 依据 + 范围</span>
          </div>
          <div className="essence-layer">
            <b>证据层</b>
            <span>RunCapsule + EA：受控条件下按方案生产、可复算的制品</span>
          </div>
          <div className="essence-layer">
            <b>审查层</b>
            <span>人工门 + 评审 + closure + lineage：组织化怀疑的制度化</span>
          </div>
        </div>
        <table className="essence-map">
          <thead>
            <tr><th>原模型要素</th><th>系统对象</th></tr>
          </thead>
          <tbody>
            <tr><td>问题</td><td>S0 研究问题 · S1 子查询 · coverage gap</td></tr>
            <tr><td>已知（文献）</td><td>文献台账 · 跨来源综合矩阵</td></tr>
            <tr><td>猜想（假设）</td><td>候选假设 CAND/IDEA —— 不是 claim</td></tr>
            <tr><td>方案（判别设计）</td><td>冻结协议 protocol sha256 · 设计审计</td></tr>
            <tr><td>证据</td><td>RunCapsule · EA（immutable）</td></tr>
            <tr><td>推断</td><td>判定/统计（分层、置换） · run contract 边界</td></tr>
            <tr><td>主张</td><td>ClaimRecord（statement + scope + refs）</td></tr>
            <tr><td>审查</td><td>人工门 · 评审包 · closure · lineage</td></tr>
            <tr><td>积累</td><td>记忆/经验 · 自改进候选（知识增量 roadmap）</td></tr>
          </tbody>
        </table>
        <small className="essence-basis">
          依据：Popper《科学发现的逻辑》（可否证性）；Merton 1942（organized skepticism）；
          Longino 1990《Science as Social Knowledge》（客观性 = 批判性 discourse）；
          Creswell《Research Design》（研究设计要素框架）；Easterbrook et al. 2008（按问题选择实证方法，证据类型差异）。
        </small>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">研究内容 → 方法推荐（advisory）</div>
        <p className="method-contrast-note" style={{ margin: "0 0 8px" }}>
          写下研究问题、数据来源、是否有随机或对照。系统按注册表里的 <b>selection_signals</b> 排序候选，
          并给出该方法会走的阶段计划。<b>推荐不等于选定</b>：G1/G2 仍由人确认，信号不足时它不会猜。
        </p>
        <div className="method-recommend">
          <textarea
            value={brief}
            onChange={(event) => setBrief(event.target.value)}
            placeholder="例：分析开源仓库的提交历史与缺陷修复，看是否更常触碰测试"
            rows={3}
          />
          <button
            type="button"
            className="control primary"
            disabled={!brief.trim()}
            onClick={() => {
              const result = recommendMethods(registry, brief);
              setRecommendation(result);
              if (result.proposed) setSelected(result.proposed);
            }}
          >
            推荐方法
          </button>
        </div>
        {recommendation ? (
          <div className="method-recommend-result">
            {recommendation.status === "ok" && recommendation.candidates.length ? (
              <p className="method-contrast-note">
                <b>建议：{recommendation.candidates[0].name_zh}</b>
                （score {recommendation.candidates[0].score}）——命中：
                {recommendation.candidates[0].matched.join(" / ")}。
                <br />
                阶段计划：{recommendation.candidates[0].plan.join(" → ")}。
                仍由人在 G1/G2 确认；这不是自动选定。
              </p>
            ) : recommendation.status === "ambiguous" ? (
              <p className="method-contrast-note">
                <b>前两名同分，系统不替你选：</b>
                {recommendation.candidates.slice(0, 2).map((item) => `${item.name_zh}（${item.score}）`).join(" vs ")}。
                请补充“是否随机 / 有无对照 / 数据来源”后再试。
              </p>
            ) : (
              <p className="method-contrast-note">
                <b>信号不足，不做推荐。</b>请补充：研究问题、数据来源、是否有随机或对照、预期证据形态。
              </p>
            )}
            {recommendation.candidates.length > 1 ? (
              <div className="method-chips">
                {recommendation.candidates.slice(1).map((item) => (
                  <code key={item.id}>{item.name_zh} · {item.score}</code>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="settings-card">
        <div className="settings-card-title">研究方法 × 效力类型（变的部分也有依据）</div>
        <p className="method-contrast-note" style={{ margin: "0 0 8px" }}>
          不变的是“每个主张都要声明效力范围”；可变的是<b>买哪种效力</b>。下表每一行来自该方法的方法论文献，
          不是按经验分配——受控实验买内部效度，案例研究买可转移性，DSR 买效用，ML 迭代买判别力。
        </p>
        <table className="essence-map">
          <thead>
            <tr>
              <th>方法</th>
              <th>效力主类型</th>
              <th>证据形态</th>
              <th>停止规则</th>
              <th>组合</th>
            </tr>
          </thead>
          <tbody>
            {registry.methods.map((method) => (
              <tr key={method.id}>
                <td>{method.name_zh}</td>
                <td>
                  {validityName(registry, method.validity_focus?.primary)}
                  {method.validity_focus?.secondary?.length ? (
                    <small className="validity-secondary">
                      {" "}+ {method.validity_focus.secondary.map((key) => validityName(registry, key)).join(" / ")}
                    </small>
                  ) : null}
                </td>
                <td>{evidenceProfileFor(method.id)?.artifactForm ?? "—"}</td>
                <td>{iterationLabel(method.iteration_rule?.kind)}</td>
                <td>
                  {registry.compositions?.find((item) => item.id === method.composition_id)?.label
                    ?? method.composition_id
                    ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <small className="essence-basis">
          效力词表：{registry.validity_vocabulary?.map((entry) => entry.name_zh).join(" / ") ?? "—"}。
          “判别力”是 ESE 工程实验的扩展，不属于 Cook &amp; Campbell 四分。
        </small>
        {registry.not_research?.length ? (
          <p className="method-contrast-note">
            <b>边界（不算完整研究）</b>：
            {registry.not_research.map((entry) => `「${entry.label}」缺 ${entry.missing}`).join("；")}。
          </p>
        ) : null}
      </div>

      <div className="settings-card">
        <div className="settings-card-title">共性槽位（治理不变）</div>
        <div className="method-slots">
          {registry.stages.map((slot) => {
            const node = ELEMENTS.find((item) => item.id === slot.id);
            return (
              <span className="method-slot" key={slot.id} title={node?.goal ?? slot.name}>
                <b>{slot.id}</b>
                <span>{slot.name}</span>
                {node?.goal && <small className="method-slot-goal">{node.goal}</small>}
              </span>
            );
          })}
        </div>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">要素组合 · 端口与接线（变与不变的呈现）</div>
        <p className="method-contrast-note" style={{ margin: "0 0 8px" }}>
          元模型是<b>要素与端口</b>（每个要素消费什么、产出什么），方法是<b>接线方式</b>。
          验证式与探索式共享同一组治理要素与门；差异只在接线——方案的输入端口不同，
          产出也随之不同（判别式协议 vs 数据收集协议），假设的位置随接线移动。
          非法接线（如探索式里让方案消费尚不存在的假设）会被端口校验拒绝。
        </p>
        <div className="composition-grid">
          {compositionList.map((composition) => {
            const violations = validateComposition(composition as Parameters<typeof validateComposition>[0]);
            const other = compositionList.find((item) => item.id !== composition.id);
            // Mark the first position where the two wirings actually diverge, not a
            // fixed element: the difference is the order, not the element itself.
            const divergenceIndex = other
              ? composition.wiring.findIndex(
                  (step, index) => other.wiring[index]?.element !== step.element
                )
              : -1;
            return (
              <div className="composition-col" key={composition.id}>
                <div className="composition-head">
                  <b>{composition.label}</b>
                  <span>{composition.sub}</span>
                </div>
                <ol className="composition-wiring">
                  {composition.wiring.map((step, index) => {
                    const isDiverge = index === divergenceIndex;
                    return (
                      <li
                        key={`${composition.id}-${step.element}-${index}`}
                        className={`composition-step${isDiverge ? " is-diverge" : ""}`}
                      >
                        <b>{step.element}</b>
                        <small>{step.consumes ? `消费 ${step.consumes}` : "入口"}</small>
                        {step.rationale ? (
                          <small className="composition-rationale">{step.rationale}</small>
                        ) : null}
                      </li>
                    );
                  })}
                </ol>
                <small className={`composition-valid${violations.length ? " is-bad" : ""}`}>
                  {violations.length
                    ? `非法接线：${violations[0].message}`
                    : "✓ 端口校验通过：每步的输入都被上游产出满足"}
                </small>
              </div>
            );
          })}
        </div>
        <p className="method-contrast-note">
          自改进的组合化方向：智能体可提出新的接线（组合提案），必须通过同样的端口校验与治理门，租约由人授予——
          内部编排可变，用户面与治理语义不变。
        </p>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">要素组合视图 · 顺序由依赖推导</div>
        <p className="method-contrast-note" style={{ margin: "0 0 8px" }}>
          流程顺序不是经验预设：每个治理要素声明它<b>消费</b>什么、<b>产出</b>什么，顺序是这张依赖图的拓扑序。
          调换两个要素（如「问题与假设」与「研究方案」）会改变输入输出关系——所以顺序是被推导的，也是可按方法组合的。
        </p>
        <ol className="element-chain">
          {ELEMENTS.map((node) => (
            <li
              key={node.id}
              className={`element-node${isHumanElement(node) ? " is-human" : ""}`}
              id={`element-${node.id}`}
            >
              <div className="element-node-head">
                <b>{node.id}</b>
                <span className="element-name">{node.element}</span>
                {isHumanElement(node) && <span className="element-human-tag">人</span>}
              </div>
              <span className="element-goal"><i>目标</i>{node.goal}</span>
              {node.consumes.length > 0 && (
                <div className="element-consumes">
                  {node.consumes.map((edge) => (
                    <div className="element-edge" key={`${edge.from}-${edge.what}`}>
                      <i>← {edge.from}</i>
                      <span>{edge.what}</span>
                      <small>{edge.source}</small>
                    </div>
                  ))}
                </div>
              )}
              <div className="element-produces">
                {node.produces.map((product) => (
                  <code key={product}>{product}</code>
                ))}
              </div>
            </li>
          ))}
        </ol>
        <p className="method-contrast-note">
          边上的每条输入都标注后端出处（SPEC / 模块不变式）；要素的粒度与组合方式即「变与不变」中的不变层——
          治理语义不变，方法组合可变。
        </p>
      </div>

      <div className="settings-card">
        <div className="settings-card-title">
          方法 × 槽位矩阵（差异）
          <span className="matrix-view-switch" role="group" aria-label="矩阵视图切换">
            <button
              type="button"
              className={`matrix-view-btn${!taskMatrixView ? " is-on" : ""}`}
              onClick={() => setTaskMatrixView(false)}
            >
              适配点阵
            </button>
            <button
              type="button"
              className={`matrix-view-btn${taskMatrixView ? " is-on" : ""}`}
              onClick={() => setTaskMatrixView(true)}
              title="交叉格 = 方法论约束下的阶段性任务卡（stage_tasks）"
            >
              任务卡
            </button>
          </span>
        </div>
        <p className="method-contrast-note" style={{ margin: "0 0 7px" }}>
          二维模型：行 = <b>研究阶段</b>（治理不变），列 = <b>研究方法</b>（数据声明）；
          交叉点 = 方法论约束下的阶段性任务。一个任务 = 选一列方法，按行走有效格——
          流程不是固定的链，而是这张矩阵上的走法。
        </p>
        <div className="method-matrix" role="table" aria-label="方法与槽位的适配矩阵">
          <div className="method-matrix-row method-matrix-head">
            <span className="method-matrix-name">方法</span>
            {registry.stages.map((slot) => (
              <span key={slot.id} className="method-matrix-cell" title={slot.name}>
                {slot.id}
              </span>
            ))}
          </div>
          {registry.methods.map((method) => {
            const fit = fitMap(method);
            return (
              <button
                type="button"
                key={method.id}
                className={`method-matrix-row${selected === method.id ? " is-on" : ""}`}
                onClick={() => setSelected(method.id)}
                title={`${method.name_zh}（${method.name_en}）`}
              >
                <span className="method-matrix-name">{method.name_zh}</span>
                {registry.stages.map((slot) => {
                  const taskText = taskMatrixView ? (method.stage_tasks?.[slot.id] ?? "") : "";
                  const cellClass = taskMatrixView
                    ? `method-matrix-cell method-matrix-cell-task${taskText ? " has-task" : ""}${fit[slot.id] ? " is-fit" : ""}`
                    : `method-matrix-cell${fit[slot.id] ? " is-fit" : ""}`;
                  return (
                    <span
                      key={slot.id}
                      className={cellClass}
                      title={taskMatrixView && taskText ? taskText : fit[slot.id] ? "核心槽位" : "非核心槽位"}
                    >
                      {taskMatrixView ? (taskText ? taskText.slice(0, 46) : "—") : fit[slot.id] ? "●" : "·"}
                    </span>
                  );
                })}
              </button>
            );
          })}
        </div>
        <small className="method-contrast-note">
          任务卡文本逐字来自注册表 stage_tasks（advisor 待办"标签化梳理"的落点之一）；
          自改进的层级：改 skill = 微观，修订本矩阵交叉点 = <b>流程级</b>（须走组合提案租约）。
        </small>
      </div>

      {tags.length > 0 && (
        <div className="settings-card">
          <div className="settings-card-title">标签 × 方法（共性与差异的可复现提取）</div>
          {[{ group: "common" as const, label: "共性（≥3 方法）" }, { group: "partial" as const, label: "部分共性（2 方法）" }, { group: "difference" as const, label: "本质差异（单方法独有）" }].map(
            ({ group, label }) => {
              const rows = tags.filter((row) => row.group === group);
              if (!rows.length) return null;
              return (
                <div className="tag-group" key={group}>
                  <div className="tag-group-title">{label}</div>
                  {rows.map((row) => (
                    <div className="tag-row" key={row.tag}>
                      <b>{row.tag}</b>
                      <span className="tag-row-def">{row.definition}</span>
                      <div className="tag-row-methods">
                        {row.methods.map((methodId) => {
                          const method = registry.methods.find((item) => item.id === methodId);
                          return <code key={methodId}>{method?.name_zh ?? methodId}</code>;
                        })}
                      </div>
                      <small>依据：{row.basis}</small>
                    </div>
                  ))}
                </div>
              );
            }
          )}
          <p className="method-contrast-note">
            标签来自各方法已注册的协议字段、检查项与任务卡——共性/差异的提取是数据计算，不再凭直觉。
          </p>
        </div>
      )}

      {active && (
        <div className="settings-card">
          <div className="settings-card-title">
            {active.name_zh} <small>{active.name_en}</small>
          </div>
          <div className="method-detail-grid">
            <div>
              <b>输入（该方法消费什么）</b>
              <div className="method-chips">
                {(active.inputs ?? []).map((input) => (
                  <code key={input}>{input}</code>
                ))}
              </div>
            </div>
            <div>
              <b>证据源（证据从哪里来）</b>
              <div className="method-chips">
                {(active.evidence_sources ?? []).map((source) => (
                  <code key={source}>{source}</code>
                ))}
              </div>
            </div>
            <div>
              <b>评估维度（维度 + 文献依据）</b>
              <div className="method-dims">
                {(active.evaluation_dimensions ?? []).map((dim) => (
                  <div className="method-dim" key={dim.dimension}>
                    <span>{dim.dimension}</span>
                    <small>{dim.basis}</small>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <b>须冻结的协议字段</b>
              <div className="method-chips">
                {active.protocol_fields.map((field) => (
                  <code key={field}>{field}</code>
                ))}
              </div>
            </div>
            <div>
              <b>产物</b>
              <div className="method-chips">
                {active.artifacts.map((artifact) => (
                  <code key={artifact}>{artifact}</code>
                ))}
              </div>
            </div>
            <div>
              <b>检查（blocker {blockerCount(active)}/{active.checks.length}）</b>
              <div className="method-chips">
                {active.checks.map((check) => (
                  <code key={check.id} className={check.severity === "blocker" ? " is-blocker" : ""}>
                    {check.id}
                  </code>
                ))}
              </div>
            </div>
            <div>
              <b>证据类型与效力</b>
              <p className="method-evidence-kind">{evidenceProfileFor(active.id)?.kind ?? "—"}</p>
              <p className="method-artifact-form">
                <i>S5 证据形态：</i>{evidenceProfileFor(active.id)?.artifactForm ?? "—"}
              </p>
              <p className="method-artifact-form">
                <i>效力主类型：</i>{validityName(registry, active.validity_focus?.primary)}
                {active.validity_focus?.secondary?.length
                  ? `（次：${active.validity_focus.secondary.map((key) => validityName(registry, key)).join(" / ")}）`
                  : ""}
              </p>
              <p className="method-artifact-form">
                <i>停止规则：</i>{iterationLabel(active.iteration_rule?.kind)} —— {active.iteration_rule?.detail ?? "—"}
              </p>
              <small className="method-evidence-basis">{evidenceProfileFor(active.id)?.basis ?? ""}</small>
            </div>
            <div className="method-orchestration-block">
              <b>编排契约（元模型推导）</b>
              {orchestration?.plans[active.id] ? (
                <>
                  <p className="method-strategy-note">
                    实际顺序：
                    {orchestration.plans[active.id].order.map((element, index) => (
                      <span key={element}>
                        {index > 0 ? " → " : ""}
                        <code>{element}</code>
                      </span>
                    ))}
                    {orchestration.plans[active.id].order.join("") !==
                    orchestration.plans[active.id].full_order.join("") ? (
                      <small className="method-orchestration-gap">
                        （完整接线还含 {orchestration.plans[active.id].full_order
                          .filter((element) => !orchestration.plans[active.id].order.includes(element))
                          .join(" / ")}，本方法不覆盖）
                      </small>
                    ) : null}
                  </p>
                  {orchestration.plans[active.id].contracts
                    .filter((contract) => contract.covered)
                    .map((contract) => (
                      <div key={contract.stage} className="method-contract-row">
                        <span className="method-strategy-stage">{contract.stage}</span>
                        <b>{contract.element}</b>
                        {contract.role ? (
                          <code className="is-role">{contract.role}</code>
                        ) : null}
                        <em className={contract.human ? "is-human" : "is-agent"}>
                          {contract.executor === "human" ? "人" : contract.human ? "agent+人签" : "agent"}
                        </em>
                        {contract.human_sign ? (
                          <code className="is-gate">{contract.human_sign}</code>
                        ) : contract.gate ? (
                          <code className="is-gate">{contract.gate}</code>
                        ) : null}
                        <small>
                          入：{contract.requires.join(" / ") || "—"} · 出：
                          {contract.produces.join(" / ") || "—"}
                          {contract.agent_module ? ` · 实现：${contract.agent_module}` : ""}
                          {contract.tasks ? ` · ${contract.tasks}` : ""}
                        </small>
                      </div>
                    ))}
                  <small className="method-evidence-basis">
                    顺序由元素端口依赖拓扑推导，不由数组位置决定；门与角色来自元模型，不随方法变化。
                  </small>
                </>
              ) : (
                <small className="method-evidence-basis">
                  编排计划快照缺失：运行 python -m research_agent workspace export 重新导出
                  orchestration-plans.json。
                </small>
              )}
            </div>
            <div className="method-strategy-block">
              <b>护栏 / 可优化空间</b>
              {strategySpace?.methods[active.id]?.status === "modeled" ? (
                <>
                  <p className="method-strategy-note">
                    硬性约束（AI 不可改）：
                    {strategySpace.methods[active.id].hard_constraints.map((guard) => (
                      <code key={guard}>{guard}</code>
                    ))}
                  </p>
                  {strategySpace.methods[active.id].choice_points.map((point) => (
                    <div key={point.id} className="method-strategy-point">
                      <span className="method-strategy-stage">{point.stage}</span>
                      <b>{point.id}</b> — {point.description}
                      <div className="method-chips">
                        {point.options.map((option) => (
                          <code key={String(option)}>{String(option)}</code>
                        ))}
                      </div>
                      <small>guard：{point.guard.join(" / ")} · 判定：{point.evidence_of_effect}</small>
                    </div>
                  ))}
                  <small className="method-evidence-basis">{strategySpace.methods[active.id].boundary}</small>
                </>
              ) : (
                <small className="method-evidence-basis">
                  该方法尚未形式化建模可优化空间（只列护栏）；不据此处声称流程级自改进可用。
                </small>
              )}
            </div>
            <div>
              <b>对智能体设计的含义（Prompt 与基线）</b>
              <p className="method-design-baseline">
                <i>基线策略：</i>{evidenceProfileFor(active.id)?.baselinePolicy ?? "—"}
              </p>
              <p className="method-design-prompt">
                <i>Prompt 纪律：</i>不得宣称——
                {active.cannot_support.map((limit) => (
                  <code key={limit}>{limit}</code>
                ))}
              </p>
              <small>
                推导自该方法的证据类型与能力边界（cannot_support 逐字）；方法差异直接指导
                智能体 Prompt 与基线对比（研讨纪要）。
              </small>
            </div>
            <div>
              <b>不能支持（能力边界）</b>
              <ul className="method-limits">
                {active.cannot_support.map((limit) => (
                  <li key={limit}>{limit}</li>
                ))}
              </ul>
            </div>
            {active.guidelines && active.guidelines.length > 0 && (
              <div>
                <b>方法学依据</b>
                <ul className="method-limits">
                  {active.guidelines.map((guideline) => (
                    <li key={guideline.key}>{guideline.citation}</li>
                  ))}
                </ul>
              </div>
            )}
            {(active.tags ?? []).length > 0 && (
              <div>
                <b>标签（来自标签化梳理）</b>
                <div className="method-chips">
                  {(active.tags ?? []).map((tag) => (
                    <code key={tag}>{tag}</code>
                  ))}
                </div>
              </div>
            )}
            {active.stage_tasks && Object.keys(active.stage_tasks).length > 0 && (
              <div>
                <b>槽位任务卡（每槽位该做什么）</b>
                <div className="method-stage-tasks">
                  {Object.entries(active.stage_tasks).map(([slot, text]) => (
                    <div className="method-stage-task" key={slot}>
                      <b>{slot}</b>
                      <span>{text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {selected && (() => {
        const activeMethod = registry.methods.find((method) => method.id === selected);
        const plan = activeMethod ? stagePlanFor(activeMethod, registry) : null;
        if (!plan) return null;
        return (
          <div className="settings-card">
            <div className="settings-card-title">解析后的阶段计划 · {plan.label}</div>
            <p className="method-contrast-note" style={{ margin: "0 0 8px" }}>
              该方法实例化的组合接线，按治理槽位展开——<b>不同方法的计划顺序不同</b>，这就是「不是固定流程」的数据形态。
            </p>
            <ol className="method-plan">
              {plan.stages.map((step) => (
                <li key={step.slot} className={`method-plan-step${step.uncovered ? " is-uncovered" : ""}`}>
                  <b>{step.slot}</b>
                  <span>{step.task || "（无任务卡）"}</span>
                  {step.uncovered && <small>组合未编排 · 规范序补入</small>}
                </li>
              ))}
            </ol>
            <small className="method-contrast-note">
              执行器消费此计划仍为 roadmap（design/156 §4）；当前计划已通过端口校验。
            </small>
          </div>
        );
      })()}

      {methodContrast.length > 0 && (
        <div className="settings-card">
          <div className="settings-card-title">协议字段对比 · 两种实证方法</div>
          <div className="method-contrast">
            {methodContrast.map((method) => (
              <div className="method-contrast-col" key={method.id}>
                <b>{method.nameZh}</b>
                <div className="method-chips">
                  {method.protocolFields.map((field) => (
                    <code key={field}>{field}</code>
                  ))}
                </div>
                <small>blocker 检查：{method.blockers.join(" · ")}</small>
              </div>
            ))}
          </div>
          <p className="method-contrast-note">
            同一治理骨架：两边的差异只在「冻结什么、怎么检验」——执行、判定、签署的槽位与门完全复用。
          </p>
        </div>
      )}

      {compareRows.length > 0 && (
        <div className="settings-card">
          <div className="settings-card-title">实证任务对比 · 同一治理骨架，不同实例化</div>
          <div className="task-compare" role="table" aria-label="实证任务对比">
            <div className="task-compare-row task-compare-head">
              <span>维度</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.name}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>方法 profile</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.method?.name_zh ?? "—"}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>证据源</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.dataset ?? "—"}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>主指标</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.metric ?? "—"}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>seeds</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.seeds ?? "—"}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>基线策略</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.baseline ?? "—"}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>断言（claim）</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>
                  {row.claim ? (
                    <>
                      <b>{row.claim.id} · {row.claim.badge}</b>
                      <small>{row.claim.text}</small>
                      <small>范围：{row.claim.scope}</small>
                    </>
                  ) : (
                    "—"
                  )}
                </span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>已走槽位</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.stagesWalked.join(" → ")}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>开着的人工门</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>{row.openGates.length ? row.openGates.join(" / ") : "无"}</span>
              ))}
            </div>
            <div className="task-compare-row">
              <span>标签差异（单方法独有）</span>
              {compareRows.map((row) => (
                <span key={row.taskId}>
                  {row.uniqueTags.length ? (
                    row.uniqueTags.map((tag) => <code key={tag}>{tag}</code>)
                  ) : (
                    "—"
                  )}
                </span>
              ))}
            </div>
          </div>
          <p className="method-contrast-note">
            对比派生自各任务自身字段与转录；运行时任务应由任务元数据携带 method_id 后进入同一张表。
          </p>
        </div>
      )}
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
        description="Wellspring Agent · 证据闭合的对话式科研工作台。"
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
