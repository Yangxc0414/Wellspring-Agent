import { useEffect, useMemo, useState } from "react";
import {
  createRun,
  createRuntimeArchive,
  createRuntimeMemory,
  deleteRuntimeArchive,
  deleteRuntimeMemory,
  getRun,
  loadAgents,
  loadCommands,
  loadRunArtifacts,
  loadRuns,
  loadRuntimeArchive,
  loadRuntimeMemory,
  loadSigners,
  probeRuntime,
  runtimeBaseLabel,
  runtimeUrl
} from "../../adapters/runtimeApi";
import type {
  AgentRegistrySnapshot,
  CommandCatalogSnapshot,
  RunArtifact,
  RunJob,
  RuntimeArchiveSnapshot,
  RuntimeHealth,
  RuntimeMemorySnapshot,
  SignerSnapshot,
  SnapshotResult
} from "../../adapters/runtimeApi";
import { SHORTCUT_ACTIONS, formatShortcutLabel } from "../../domain/shortcuts";
import { siteHref } from "../../domain/links";
import type { MemoryKind } from "../../domain/types";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";
import { SourcePill } from "../SourcePill";
import { AgentManagement } from "./AgentManagement";
import { OrchestrationOverview } from "./OrchestrationOverview";
import { Card, PageHead } from "./SettingsSections";

const MEMORY_KINDS: Array<{ id: MemoryKind; label: string }> = [
  { id: "decision", label: "决策" },
  { id: "preference", label: "偏好" },
  { id: "constraint", label: "约束" },
  { id: "note", label: "笔记" }
];

const SAFETY_LABEL = {
  read_only: "只读",
  local_write: "本地写入",
  network_opt_in: "显式联网",
  human_gate: "人工门",
  catalog_only: "未分类"
} as const;

function shortTime(value: string): string {
  return value ? value.slice(0, 16).replace("T", " ") : "—";
}

function useAgentsResource() {
  const [state, setState] = useState<{
    loading: boolean;
    result: SnapshotResult<AgentRegistrySnapshot> | null;
    error: string;
  }>({ loading: true, result: null, error: "" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: "" }));
    loadAgents()
      .then((result) => {
        if (!cancelled) setState({ loading: false, result, error: "" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ loading: false, result: null, error: String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { ...state, reload: () => setTick((value) => value + 1) };
}

function useCommandsResource() {
  const [state, setState] = useState<{
    loading: boolean;
    result: SnapshotResult<CommandCatalogSnapshot> | null;
    error: string;
  }>({ loading: true, result: null, error: "" });
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState((current) => ({ ...current, loading: true, error: "" }));
    loadCommands()
      .then((result) => {
        if (!cancelled) setState({ loading: false, result, error: "" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ loading: false, result: null, error: String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  return { ...state, reload: () => setTick((value) => value + 1) };
}

const SPEC_SOURCE_LABELS = { snapshot: "SPEC SNAPSHOT" };

function SourceBadge({ source }: { source: "runtime" | "snapshot" | null }) {
  return (
    <SourcePill
      source={source}
      labels={SPEC_SOURCE_LABELS}
      emptyLabel="STATIC · NO SNAPSHOT"
    />
  );
}

export function MemorySettingsPage() {
  const memory = useWorkspaceStore((state) => state.memory);
  const tasks = useWorkspaceStore((state) => state.tasks);
  const actions = useWorkspaceStore((state) => state.actions);
  const [text, setText] = useState("");
  const [kind, setKind] = useState<MemoryKind>("note");
  const [scope, setScope] = useState("workspace");
  const [syncBusy, setSyncBusy] = useState(false);
  const [remote, setRemote] = useState<RuntimeMemorySnapshot | null>(null);
  const [remoteError, setRemoteError] = useState("");

  const candidates = useMemo(
    () =>
      tasks
        .flatMap((task) =>
          task.evidence
            .filter((item) => item.kind === "claim" || item.kind === "hypothesis" || item.kind === "gap")
            .map((item) => ({ task, item }))
        )
        .filter(({ item }) => item.text.trim())
        .slice(0, 8),
    [tasks]
  );

  useEffect(() => {
    loadRuntimeMemory()
      .then((snapshot) => {
        setRemote(snapshot);
        setRemoteError("");
      })
      .catch((error: unknown) => {
        setRemote(null);
        setRemoteError(String(error));
      });
  }, []);

  const add = () => {
    if (!text.trim()) return;
    actions.addMemory({ text, kind, scope, source: "user" });
    setText("");
  };

  const sync = async () => {
    const unsynced = memory.filter((entry) => !entry.syncedAt);
    if (!unsynced.length) {
      actions.notify("没有待同步的本地记忆");
      return;
    }
    setSyncBusy(true);
    try {
      for (const entry of unsynced) {
        await createRuntimeMemory({
          text: entry.text,
          kind: entry.kind,
          scope: entry.scope,
          source: entry.source
        });
      }
      actions.markMemorySynced(unsynced.map((entry) => entry.id));
      setRemote(await loadRuntimeMemory());
      setRemoteError("");
      actions.notify(`已同步 ${unsynced.length} 条记忆到本地 runtime`);
    } catch {
      actions.notify("runtime 未连接；记忆已保存在本地");
    } finally {
      setSyncBusy(false);
    }
  };

  const removeRemote = async (id: string) => {
    try {
      await deleteRuntimeMemory(id);
      setRemote(await loadRuntimeMemory());
    } catch {
      actions.notify("删除 runtime 记忆失败；请检查连接");
    }
  };

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="AGENT / MEMORY"
        title="记忆"
        description="用户自管的工作记忆：记录决策、约束与偏好。它不是证据，不进入 Claim、EA、门禁或导出。"
      />

      <Card title="写入一条记忆" description="本地即时保存；连接 runtime 后可同步到本地工作区存储。">
        <div className="memory-compose">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="例如：只在 85°C / 85% RH 条件下比较 T80；摘要-only 不能当证据。"
            rows={3}
            maxLength={2000}
          />
          <div className="memory-compose-row">
            <label>
              类型
              <select value={kind} onChange={(event) => setKind(event.target.value as MemoryKind)}>
                {MEMORY_KINDS.map((item) => (
                  <option key={item.id} value={item.id}>{item.label}</option>
                ))}
              </select>
            </label>
            <label>
              范围
              <input value={scope} onChange={(event) => setScope(event.target.value)} maxLength={120} />
            </label>
            <button type="button" className="settings-btn primary" onClick={add} disabled={!text.trim()}>
              <Icon name="plus" size={12} />记入本地
            </button>
          </div>
        </div>
      </Card>

      <div className="settings-two-col">
        <Card title={`本地记忆 · ${memory.length}`} description="随工作区持久化；刷新后保留。">
          {memory.length ? (
            <div className="memory-list">
              {memory.map((entry) => (
                <div className="memory-row" key={entry.id}>
                  <span className="memory-kind" data-kind={entry.kind}>{entry.kind}</span>
                  <div>
                    <b>{entry.text}</b>
                    <small>{entry.scope} · {entry.source} · {shortTime(entry.createdAt)}{entry.syncedAt ? " · 已同步" : ""}</small>
                  </div>
                  <button type="button" className="icon-button" onClick={() => actions.deleteMemory(entry.id)} aria-label="删除本地记忆">
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="settings-empty">还没有本地记忆。可以从下方任务证据中固定一条，或手动写入。</p>
          )}
          <div className="settings-actions">
            <button type="button" className="settings-btn" onClick={sync} disabled={syncBusy || !memory.length}>
              <Icon name="refresh" size={12} />{syncBusy ? "同步中…" : "同步到本地 runtime"}
            </button>
          </div>
        </Card>

        <Card title={`Runtime 记忆 · ${remote?.count ?? 0}`} description="runtime 本地存储；不是云端同步。">
          {remote ? (
            <div className="memory-list">
              {remote.entries.slice(0, 8).map((entry) => (
                <div className="memory-row" key={entry.id}>
                  <span className="memory-kind" data-kind={entry.kind}>{entry.kind}</span>
                  <div>
                    <b>{entry.text}</b>
                    <small>{entry.scope} · {entry.source} · {shortTime(entry.created_at)}</small>
                  </div>
                  <button type="button" className="icon-button" onClick={() => removeRemote(entry.id)} aria-label="删除 runtime 记忆">
                    <Icon name="trash" size={12} />
                  </button>
                </div>
              ))}
              {!remote.entries.length && <p className="settings-empty">runtime 记忆为空；先同步本地记忆。</p>}
            </div>
          ) : (
            <div className="settings-boundary">
              <Icon name="shield" size={14} />
              <span>未连接本地 runtime（{runtimeBaseLabel()}）。本地记忆仍可用；启动 `python -m research_agent.runtime` 后可同步。{remoteError && <small> {remoteError}</small>}</span>
            </div>
          )}
        </Card>
      </div>

      <Card title="从任务固定记忆" description="只读取当前任务证据的文本与引用；固定后仍是记忆，不是证据。">
        <div className="memory-candidates">
          {candidates.map(({ task, item }) => {
            const exists = memory.some((entry) => entry.text === item.text);
            return (
              <div className="memory-candidate" key={`${task.id}-${item.id}`}>
                <span className="memory-kind" data-kind={item.kind}>{item.kind}</span>
                <div>
                  <b>{item.text}</b>
                  <small>{task.name} · {item.scope} · {item.refs.length} refs</small>
                </div>
                <button
                  type="button"
                  className="settings-btn"
                  disabled={exists}
                  onClick={() => actions.addMemory({
                    text: item.text,
                    kind: item.kind === "claim" ? "decision" : item.kind === "gap" ? "constraint" : "note",
                    scope: item.scope,
                    source: `task:${task.name}`
                  })}
                >
                  {exists ? "已记录" : "固定为记忆"}
                </button>
              </div>
            );
          })}
          {!candidates.length && <p className="settings-empty">当前任务还没有可固定的 claim / 候选 / gap。</p>}
        </div>
      </Card>
    </div>
  );
}

export function AgentsSettingsPage() {
  const { loading, result, error, reload } = useAgentsResource();
  const [query, setQuery] = useState("");
  const agents = result?.data.agents ?? [];
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return agents;
    return agents.filter((agent) =>
      `${agent.id} ${agent.name} ${agent.stage} ${agent.owner} ${agent.tools.join(" ")}`.toLowerCase().includes(needle)
    );
  }, [agents, query]);

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="AGENT / SUBAGENTS"
        title="子智能体"
        description="只读投影 modules/<id>/SPEC.md，并展示 S1 scout fan-out、文献过程记忆与停在 G1 前的协作拓扑。这里不执行 agent，也不修改状态。"
      />
      <OrchestrationOverview />
      <AgentManagement />
      <Card title="模块注册表" description={result ? `来源：${result.data.source}` : "等待 SPEC 注册表"}>
        <div className="settings-toolbar">
          <label className="settings-search">
            <Icon name="search" size={13} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索模块、阶段、owner 或工具" />
          </label>
          <SourceBadge source={result?.source ?? null} />
          <button type="button" className="settings-btn" onClick={reload}>重新读取</button>
        </div>
        {loading && <p className="settings-empty">读取 SPEC 注册表…</p>}
        {error && <p className="settings-empty">读取失败：{error}</p>}
        <div className="agent-list">
          {filtered.map((agent) => (
            <article className="agent-card" key={agent.id} data-status={agent.status}>
              <div className="agent-card-head">
                <div>
                  <b>{agent.name}</b>
                  <code>{agent.id}</code>
                </div>
                <span className="settings-state" data-state={agent.status}>{agent.status}</span>
              </div>
              <div className="agent-meta">
                <span>{agent.stage}</span>
                <span>v{agent.version}</span>
                <span>{agent.owner}</span>
                <span>{agent.tools.length} tools</span>
                <span>{agent.gates.length} gates</span>
                <span>{agent.invariants.length} invariants</span>
              </div>
              <p>{agent.outputs.slice(0, 3).join(" · ")}</p>
              <small>{agent.spec}</small>
            </article>
          ))}
        </div>
        {!loading && !error && !filtered.length && <p className="settings-empty">没有匹配的模块。</p>}
        {result?.source === "snapshot" && (
          <p className="settings-note">
            当前为 SPEC 快照。规格变化后运行 <code>python -m research_agent workspace export --output-dir apps/web/public</code> 更新。
          </p>
        )}
      </Card>
    </div>
  );
}

export function CommandsSettingsPage() {
  const { loading, result, error, reload } = useCommandsResource();
  const preferences = useWorkspaceStore((state) => state.preferences);
  const [query, setQuery] = useState("");
  const commands = result?.data.commands ?? [];
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((command) =>
      `${command.id} ${command.label} ${command.syntax} ${command.description} ${command.group}`.toLowerCase().includes(needle)
    );
  }, [commands, query]);
  const groups = useMemo(() => {
    const map = new Map<string, typeof filtered>();
    for (const command of filtered) {
      const list = map.get(command.group) ?? [];
      list.push(command);
      map.set(command.group, list);
    }
    return Array.from(map.entries());
  }, [filtered]);

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="AGENT / COMMANDS"
        title="命令"
        description="CLI 命令目录与当前键盘映射。命令只做说明；设置页不会执行 shell。"
      />
      <div className="settings-two-col">
        <Card title="键盘命令" description="来自 Preferences.shortcuts；在快捷键页录制。">
          <div className="command-list">
            {SHORTCUT_ACTIONS.map((action) => (
              <div className="command-row" key={action.id}>
                <div>
                  <b>{action.label}</b>
                  <small>{action.group} · {action.description}</small>
                </div>
                <kbd>{formatShortcutLabel(preferences.shortcuts[action.id])}</kbd>
              </div>
            ))}
          </div>
        </Card>
        <Card title="执行边界" description="目录不是执行器。">
          <div className="settings-boundary">
            <Icon name="shield" size={14} />
            <span>只读命令可直接运行；本地写入会改变文件；显式联网需要单独开关；`run claim` 与 `closure sign` 永远需要人签。设置页不提供签核按钮。</span>
          </div>
          <div className="settings-kv-list">
            <div><span>runtime</span><b>{runtimeBaseLabel()}</b></div>
            <div><span>命令来源</span><b>{result ? (result.source === "runtime" ? "runtime API" : "STATIC snapshot") : "—"}</b></div>
          </div>
        </Card>
      </div>
      <Card title="CLI 目录" description="与仓库 CLI 同步的描述性目录。">
        <div className="settings-toolbar">
          <label className="settings-search">
            <Icon name="search" size={13} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索命令、语法或安全级别" />
          </label>
          <SourceBadge source={result?.source ?? null} />
          <button type="button" className="settings-btn" onClick={reload}>重新读取</button>
        </div>
        {loading && <p className="settings-empty">读取命令目录…</p>}
        {error && <p className="settings-empty">读取失败：{error}</p>}
        {groups.map(([group, items]) => (
          <div className="command-group" key={group}>
            <div className="settings-group-label">{group}</div>
            {items.map((command) => (
              <div className="command-row" key={command.id}>
                <div>
                  <b>{command.label}</b>
                  <code>{command.syntax}</code>
                  <small>{command.description}</small>
                </div>
                <span className="settings-state" data-state={command.safety}>{SAFETY_LABEL[command.safety]}</span>
              </div>
            ))}
          </div>
        ))}
        {!loading && !error && !filtered.length && <p className="settings-empty">没有匹配的命令。</p>}
      </Card>
    </div>
  );
}

export function RuntimeSettingsPage() {
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [run, setRun] = useState<RunJob | null>(null);
  const [artifacts, setArtifacts] = useState<RunArtifact[]>([]);
  const [runBusy, setRunBusy] = useState(false);
  const [runError, setRunError] = useState("");
  const [recentRuns, setRecentRuns] = useState<RunJob[]>([]);
  const [recentError, setRecentError] = useState("");
  const [signers, setSigners] = useState<SignerSnapshot | null>(null);

  const refreshRecent = () => {
    loadRuns(8)
      .then((jobs) => {
        setRecentRuns(jobs);
        setRecentError("");
      })
      .catch((error: unknown) => {
        setRecentRuns([]);
        setRecentError(error instanceof Error ? error.message : String(error));
      });
  };

  useEffect(refreshRecent, []);
  useEffect(() => {
    if (run?.status === "completed" || run?.status === "failed") refreshRecent();
  }, [run?.status]);

  useEffect(() => {
    if (!run || run.status === "completed" || run.status === "failed") return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      getRun(run.job_id)
        .then((next) => {
          if (cancelled) return;
          setRun(next);
          if (next.status === "completed" || next.status === "failed") setRunBusy(false);
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          setRunError(error instanceof Error ? error.message : String(error));
          setRunBusy(false);
        });
    }, 1000);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [run]);

  useEffect(() => {
    if (!run || run.status !== "completed") return;
    let cancelled = false;
    loadRunArtifacts(run.job_id)
      .then((nextArtifacts) => {
        if (!cancelled) setArtifacts(nextArtifacts);
      })
      .catch((error: unknown) => {
        if (!cancelled) setRunError(error instanceof Error ? error.message : String(error));
      });
    return () => {
      cancelled = true;
    };
  }, [run?.job_id, run?.status]);

  const startRun = () => {
    setRunBusy(true);
    setRunError("");
    setArtifacts([]);
    createRun({
      topic: "ChemLab reaction conversion baseline",
      language: "en",
      venue_type: "en_conference",
      max_sources: 4,
      real_corpus: true,
      run_dataset: "chemlab",
      run_seeds: 3
    })
      .then(setRun)
      .catch((error: unknown) => {
        setRunError(error instanceof Error ? error.message : String(error));
        setRunBusy(false);
      });
  };

  const probe = () => {
    setLoading(true);
    probeRuntime()
      .then((snapshot) => {
        setHealth(snapshot);
      })
      .catch(() => {
        setHealth(null);
      })
      .finally(() => setLoading(false));
  };

  useEffect(probe, []);
  useEffect(() => {
    loadSigners()
      .then(setSigners)
      .catch(() => setSigners(null));
  }, []);

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="SYSTEM / RUNTIME"
        title="执行环境"
        description="本地 FastAPI runtime 的真实状态。它只执行 pipeline、SSE、产物与只读 RSI；没有 claim/sign 端点。"
      />
      <Card title="连接状态" description={`API base：${runtimeBaseLabel()}`}>
        <div className="settings-toolbar">
          <span className="settings-state" data-state={health ? "ok" : "offline"}>
            {loading ? "探测中…" : health ? "CONNECTED" : "OFFLINE"}
          </span>
          <button type="button" className="settings-btn" onClick={probe} disabled={loading}>重新探测</button>
          <a className="settings-btn" href={siteHref("live/")} target="_blank" rel="noopener noreferrer">
            运行控制台 <Icon name="external" size={11} />
          </a>
        </div>
        {health ? (
          <div className="settings-kv-list">
            <div><span>service</span><b>{health.service} · v{health.version}</b></div>
            <div><span>mode</span><b>{health.mode} · {health.research_mode ?? "test"}</b></div>
            <div><span>production ready</span><b>{health.production_ready ? "yes" : "no"}</b></div>
            <div><span>queue</span><b>{health.queue.pending} pending / {health.queue.max_pending} max</b></div>
            <div><span>model gateway</span><b>{health.model_gateway ? "enabled" : "disabled"}</b></div>
            <div><span>real corpus</span><b>{health.real_corpus ? "available" : "missing"}</b></div>
            <div><span>local corpus</span><b>{health.local_corpus ? "available" : "missing"}</b></div>
            <div><span>RSI</span><b>{health.rsi_read_only ? "read-only" : "unexpected"}</b></div>
            <div><span>human sign</span><b>{health.human_sign ? "exposed" : "not exposed"}</b></div>
            <div><span>model store</span><b>{health.model_store ?? "—"}</b></div>
          </div>
        ) : (
          <div className="settings-boundary">
            <Icon name="shield" size={14} />
            <span>{loading ? "正在连接本地 runtime…" : "未连接本地 runtime。启动：python -m research_agent.runtime --port 8787"}</span>
          </div>
        )}
      </Card>
      <Card title="Signer 身份" description="本地 HMAC signer；runtime 只读，创建与签核只在 CLI。">
        {signers?.count ? (
          <>
            <div className="settings-kv-list">
              {signers.signers.map((signer) => (
                <div key={signer.signer_id}>
                  <span>{signer.name}</span>
                  <b>{signer.signer_id} · {signer.key_id}</b>
                </div>
              ))}
            </div>
            <p className="settings-note">{signers.boundary}</p>
          </>
        ) : (
          <p className="settings-empty">
            还没有本地 signer。终端运行：<code>python -m research_agent signer create --name "PI"</code>
          </p>
        )}
      </Card>
      {health?.research_mode === "production" && !health.production_ready && (
        <Card title="生产模式被阻断" description="production 不允许规则模板静默兜底；必须先完成模型接线、绑定与 key 配置。">
          <div className="settings-boundary">
            <Icon name="alert" size={14} />
            <span>{(health.model_readiness?.blocking ?? []).join(" · ") || "模型 readiness 未就绪"}</span>
          </div>
        </Card>
      )}
      {!__STATIC_ONLY__ && <Card title="本地任务 API · 集成测试" description="固定 ChemLab 协议验证；当前任务的真实运行在右侧 RUN 面板。">
        <div className="settings-toolbar">
          <button type="button" className="settings-btn primary" onClick={startRun} disabled={runBusy}>
            <Icon name="play" size={12} />{runBusy ? "运行中…" : "运行 ChemLab 集成测试"}
          </button>
          <span className={`settings-source${run ? " is-live" : ""}`}>{run ? run.status : "idle"}</span>
          {run && <code className="settings-code">{run.job_id}</code>}
        </div>
        {runError && <p className="storage-warning">{runError}</p>}
        {run && (
          <div className="settings-kv-list">
            <div><span>job</span><b>{run.job_id}</b></div>
            <div><span>status</span><b>{run.status}</b></div>
            <div><span>fixture</span><b>{run.result?.fixture_mode ? "fixture" : run.result ? "real corpus / local run" : "—"}</b></div>
            <div><span>events</span><b>{run.events_count}</b></div>
            <div><span>run</span><b>{run.result?.run_id ?? "—"}</b></div>
          </div>
        )}
        {run?.result?.warnings?.length ? (
          <div className="settings-boundary">
            <Icon name="alert" size={14} />
            <span>{run.result.warnings.join(" · ")}</span>
          </div>
        ) : null}
        {artifacts.length > 0 && (
          <div className="settings-link-grid">
            {artifacts.map((artifact) => (
              <a key={artifact.path} href={runtimeUrl(artifact.url)} target="_blank" rel="noopener noreferrer">
                <Icon name="download" size={14} />
                <span><b>{artifact.path}</b><small>{artifact.kind} · {Math.round(artifact.size / 1024)} KB</small></span>
                <Icon name="external" size={11} />
              </a>
            ))}
          </div>
        )}
      </Card>}
      {!__STATIC_ONLY__ && (
        <Card title={`最近运行 · ${recentRuns.length}`} description="来自 /api/runs 的持久化记录；重启 runtime 后仍可读取状态与产物。">
          {recentError ? (
            <div className="settings-boundary">
              <Icon name="alert" size={14} />
              <span>runtime 未连接：{recentError}</span>
            </div>
          ) : recentRuns.length ? (
            <div className="settings-kv-list">
              {recentRuns.map((job) => (
                <div key={job.job_id}>
                  <span>{job.status}</span>
                  <b title={job.request.topic}>{job.request.topic.slice(0, 42)}</b>
                  <button
                    type="button"
                    className="settings-btn"
                    onClick={() => {
                      setRun(job);
                      setArtifacts([]);
                    }}
                  >
                    查看
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="settings-note">还没有持久化运行记录。</p>
          )}
        </Card>
      )}
      <div className="settings-two-col">
        <Card title="启动本地 runtime" description="默认只绑定 127.0.0.1。">
          <pre className="settings-code">python -m research_agent.runtime --port 8787</pre>
          <p className="settings-note">Vite 开发服务器会把 <code>/api</code> 代理到 8787；静态站点需要同源反代或显式 <code>VITE_RUNTIME_URL</code>。</p>
        </Card>
        <Card title="能力边界" description="不把 runtime 当成云后端。">
          <div className="settings-boundary">
            <Icon name="lock" size={14} />
            <span>没有 /approve、/claim、/sign；没有鉴权、租户、数据库或沙箱。不要暴露到公网。</span>
          </div>
          {health && <p className="settings-note">CORS：{health.cors_origins.join(" · ")}</p>}
        </Card>
      </div>
    </div>
  );
}

export function ArchiveSettingsPage() {
  const tasks = useWorkspaceStore((state) => state.tasks);
  const archivedTaskIds = useWorkspaceStore((state) => state.archivedTaskIds);
  const actions = useWorkspaceStore((state) => state.actions);
  const [remote, setRemote] = useState<RuntimeArchiveSnapshot | null>(null);
  const [remoteError, setRemoteError] = useState("");
  const [busy, setBusy] = useState("");

  const archived = tasks.filter((task) => archivedTaskIds.includes(task.id));
  const active = tasks
    .filter((task) => !archivedTaskIds.includes(task.id))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));

  const loadRemote = () => {
    loadRuntimeArchive()
      .then((snapshot) => {
        setRemote(snapshot);
        setRemoteError("");
      })
      .catch((error: unknown) => {
        setRemote(null);
        setRemoteError(String(error));
      });
  };

  useEffect(loadRemote, []);

  const download = (taskId: string) => {
    const task = tasks.find((item) => item.id === taskId);
    if (!task) return;
    const blob = new Blob([JSON.stringify(task, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `research-agent-${task.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const sync = async (taskId: string) => {
    const task = tasks.find((item) => item.id === taskId);
    if (!task) return;
    setBusy(taskId);
    try {
      await createRuntimeArchive({
        title: task.name,
        task_id: task.id,
        note: `archived from workspace · ${task.workspaceId}`,
        payload: task as unknown as Record<string, unknown>
      });
      loadRemote();
      actions.notify(`已归档到 runtime：${task.name}`);
    } catch {
      actions.notify("runtime 未连接；任务仍保留在本地归档");
    } finally {
      setBusy("");
    }
  };

  const removeRemote = async (id: string) => {
    try {
      await deleteRuntimeArchive(id);
      loadRemote();
    } catch {
      actions.notify("删除 runtime 归档失败；请检查连接");
    }
  };

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="DATA / ARCHIVE"
        title="归档管理"
        description="本地归档只隐藏任务并保留 JSON；runtime 归档保存任务快照。两者都不改 claim、EA、门禁或签署状态。"
      />
      <Card title="可归档任务" description="归档会从任务列表隐藏；可在下方本地归档中恢复。">
        <div className="archive-list">
          {active.map((task) => (
            <div className="archive-row" key={task.id}>
              <div>
                <b>{task.name}</b>
                <small>{task.workspaceId} · {task.completedStages.length}/9 stages · {task.status}</small>
              </div>
              <button type="button" className="settings-btn" onClick={() => actions.archiveTask(task.id)}>
                归档
              </button>
            </div>
          ))}
          {!active.length && <p className="settings-empty">没有可归档的任务。</p>}
        </div>
      </Card>
      <div className="settings-two-col">
        <Card title={`本地归档 · ${archived.length}`} description="从任务列表隐藏，可恢复或下载。">
          {archived.length ? (
            <div className="archive-list">
              {archived.map((task) => (
                <div className="archive-row" key={task.id}>
                  <div>
                    <b>{task.name}</b>
                    <small>{task.workspaceId} · {task.completedStages.length}/9 stages · {task.status}</small>
                  </div>
                  <div className="archive-actions">
                    <button type="button" className="settings-btn" onClick={() => actions.restoreTask(task.id)}>恢复</button>
                    <button type="button" className="settings-btn" onClick={() => download(task.id)}>下载</button>
                    <button type="button" className="settings-btn" onClick={() => sync(task.id)} disabled={busy === task.id}>
                      {busy === task.id ? "归档中…" : "归档到 runtime"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="settings-empty">还没有本地归档。上方列表可以归档一个任务。</p>
          )}
        </Card>
        <Card title={`Runtime 归档 · ${remote?.count ?? 0}`} description="任务 JSON 快照；拒绝 secret 字段。">
          {remote ? (
            remote.items.length ? (
              <div className="archive-list">
                {remote.items.map((item) => (
                  <div className="archive-row" key={item.id}>
                    <div>
                      <b>{item.title}</b>
                      <small>{item.task_id} · {item.bytes} bytes · {shortTime(item.created_at)}</small>
                      {item.note && <small>{item.note}</small>}
                    </div>
                    <button type="button" className="icon-button" onClick={() => removeRemote(item.id)} aria-label="删除 runtime 归档">
                      <Icon name="trash" size={12} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="settings-empty">runtime 归档为空。</p>
            )
          ) : (
            <div className="settings-boundary">
              <Icon name="shield" size={14} />
              <span>未连接本地 runtime。{remoteError && ` ${remoteError}`}</span>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
