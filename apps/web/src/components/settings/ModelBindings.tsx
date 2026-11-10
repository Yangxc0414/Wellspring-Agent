import { useEffect, useState } from "react";
import {
  bindRuntimeModule,
  clearRuntimeProviderKey,
  loadRuntimeModelSnapshot,
  setRuntimeProviderKey
} from "../../adapters/modelRuntime";
import type { RuntimeModelProvider, RuntimeModelSnapshot } from "../../adapters/modelRuntime";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";

const MODULES: Array<{ id: string; label: string; stage: string; hint: string }> = [
  {
    id: "literature",
    label: "文献检索规划",
    stage: "S1",
    hint: "把研究问题拆成检索子查询；不生成 Span / 证据"
  },
  {
    id: "idea",
    label: "候选假设生成",
    stage: "S2–S3",
    hint: "只基于输入 Span 提候选；引用越界会被拒收，仍需 G1"
  },
  {
    id: "experiment",
    label: "实验设计草稿",
    stage: "S4",
    hint: "只补缺失字段；模型补全后仍为 needs_human，不执行、不冻结"
  },
  {
    id: "paper",
    label: "论文非结果章节",
    stage: "S8–S12",
    hint: "写摘要/引言/相关工作/讨论；不写 Results，不引未给出的来源"
  },
  {
    id: "judge",
    label: "引用支持审稿",
    stage: "S5b–S13",
    hint: "判断句子是否被证据支持；只产 advisory report，不改 claim/gate"
  }
];

export function ModelBindings() {
  const notify = useWorkspaceStore((state) => state.actions.notify);
  const [snapshot, setSnapshot] = useState<RuntimeModelSnapshot | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [keyDraft, setKeyDraft] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [keyBusy, setKeyBusy] = useState("");
  const [error, setError] = useState("");

  const applySnapshot = (value: RuntimeModelSnapshot) => {
    setSnapshot(value);
    setDraft({ ...value.bindings });
    setError("");
  };

  const load = async () => {
    setBusy("load");
    try {
      applySnapshot(await loadRuntimeModelSnapshot());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "runtime 未连接");
      setSnapshot(null);
    } finally {
      setBusy("");
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const save = async (module: string) => {
    setBusy(module);
    try {
      const value = await bindRuntimeModule(module, draft[module] ?? "");
      applySnapshot(value);
      notify(`${module} 模型绑定已保存到 runtime`);
    } catch (exc) {
      notify(exc instanceof Error ? `绑定失败：${exc.message}` : "绑定失败");
    } finally {
      setBusy("");
    }
  };

  const readiness = snapshot?.readiness;
  const profiles = snapshot?.profiles ?? [];
  const keyProviders: RuntimeModelProvider[] = snapshot
    ? Array.from(new Set(profiles.map((profile) => profile.provider_id)))
        .map((providerId) => snapshot.providers.find((item) => item.provider_id === providerId))
        .filter((item): item is RuntimeModelProvider => Boolean(item))
    : [];

  const saveKey = async (provider: RuntimeModelProvider) => {
    const apiKey = (keyDraft[provider.provider_id] ?? "").trim();
    if (!apiKey) return;
    setKeyBusy(provider.provider_id);
    try {
      applySnapshot(await setRuntimeProviderKey(provider.provider_id, apiKey));
      setKeyDraft((current) => {
        const next = { ...current };
        delete next[provider.provider_id];
        return next;
      });
      notify(`${provider.label || provider.provider_id} 的 key 已写入 runtime 会话内存`);
    } catch (exc) {
      notify(exc instanceof Error ? `key 保存失败：${exc.message}` : "key 保存失败");
    } finally {
      setKeyBusy("");
    }
  };

  const clearKey = async (provider: RuntimeModelProvider) => {
    setKeyBusy(provider.provider_id);
    try {
      applySnapshot(await clearRuntimeProviderKey(provider.provider_id));
      notify(`${provider.label || provider.provider_id} 的会话 key 已清除`);
    } catch (exc) {
      notify(exc instanceof Error ? `清除失败：${exc.message}` : "清除失败");
    } finally {
      setKeyBusy("");
    }
  };

  return (
    <section className="settings-card model-binding-card">
      <div className="settings-card-head">
        <div>
          <h2>模块模型绑定</h2>
          <p>
            每个研究阶段绑定一个 runtime profile。留空表示使用确定性规则/模板；生产模式要求
            literature / idea / experiment / paper / judge 全部绑定并配置 key。
          </p>
        </div>
        <button type="button" className="settings-btn" onClick={() => void load()} disabled={busy === "load"}>
          <Icon name="refresh" size={12} />
          {busy === "load" ? "读取中…" : "重新读取"}
        </button>
      </div>

      {error && <p className="settings-empty">读取失败：{error}</p>}
      {!snapshot && !error && <p className="settings-empty">读取 runtime 模型配置…</p>}

      {snapshot && (
        <>
          <div className="model-binding-list">
            {MODULES.map((module) => {
              const bound = draft[module.id] ?? "";
              const profile = profiles.find((item) => item.profile_id === bound);
              const provider = profile
                ? snapshot.providers.find((item) => item.provider_id === profile.provider_id)
                : undefined;
              const wired = snapshot.wired[module.id]?.wired;
              return (
                <div className="model-binding-row" key={module.id}>
                  <div className="model-binding-label">
                    <span className="settings-state" data-state={wired ? "active" : "draft"}>
                      {module.stage}
                    </span>
                    <b>{module.label}</b>
                    <small>{module.hint}</small>
                  </div>
                  <label className="field">
                    <span>Runtime profile</span>
                    <select
                      value={bound}
                      onChange={(event) =>
                        setDraft((current) => ({ ...current, [module.id]: event.target.value }))
                      }
                    >
                      <option value="">规则模板 / 未绑定</option>
                      {profiles.map((item) => (
                        <option key={item.profile_id} value={item.profile_id}>
                          {item.label || item.model} · {item.provider_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <div className="model-binding-meta">
                    <span data-ok={Boolean(provider?.configured)}>
                      {profile
                        ? provider?.configured
                          ? `key: ${provider.key_source}`
                          : `缺 key: ${provider?.api_key_env ?? profile.provider_id}`
                        : "无模型调用"}
                    </span>
                    <button
                      type="button"
                      className="settings-btn primary"
                      onClick={() => void save(module.id)}
                      disabled={busy === module.id || bound === (snapshot.bindings?.[module.id] ?? "")}
                    >
                      {busy === module.id ? "保存中…" : "保存"}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="runtime-key-panel">
            <div className="runtime-key-head">
              <div>
                <b>运行时供应商密钥</b>
                <small>
                  只写入当前 runtime 进程内存，不进入 localStorage 或任务产物；重启 runtime 后失效。
                </small>
              </div>
            </div>
            {keyProviders.length === 0 && (
              <p className="settings-empty">暂无可用的 runtime profile；请先在供应商卡片保存一个 profile。</p>
            )}
            {keyProviders.map((provider) => {
              const sessionKey = provider.configured && provider.key_source === "session";
              return (
                <div className="runtime-key-row" key={provider.provider_id}>
                  <div className="runtime-key-label">
                    <b>{provider.label || provider.provider_id}</b>
                    <small>
                      {provider.provider_id}
                      {provider.api_key_env ? ` · ${provider.api_key_env}` : ""}
                    </small>
                  </div>
                  <span className="runtime-key-status" data-ok={provider.configured}>
                    {provider.configured ? `已配置 · ${provider.key_source}` : "未配置 key"}
                  </span>
                  <div className="runtime-key-actions">
                    <input
                      type="password"
                      aria-label={`${provider.label || provider.provider_id} API key`}
                      placeholder={provider.configured ? "替换 key" : "粘贴 API key"}
                      value={keyDraft[provider.provider_id] ?? ""}
                      autoComplete="new-password"
                      spellCheck={false}
                      onChange={(event) =>
                        setKeyDraft((current) => ({
                          ...current,
                          [provider.provider_id]: event.target.value
                        }))
                      }
                    />
                    <button
                      type="button"
                      className="settings-btn primary"
                      onClick={() => void saveKey(provider)}
                      disabled={keyBusy === provider.provider_id || !(keyDraft[provider.provider_id] ?? "").trim()}
                    >
                      {keyBusy === provider.provider_id ? "写入中…" : "写入"}
                    </button>
                    {sessionKey && (
                      <button
                        type="button"
                        className="settings-btn"
                        onClick={() => void clearKey(provider)}
                        disabled={keyBusy === provider.provider_id}
                      >
                        清除
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className={`model-readiness${readiness?.production_ready ? " is-ready" : ""}`}>
            <Icon name={readiness?.production_ready ? "check" : "shield"} size={13} />
            <div>
              <b>
                {readiness?.production_ready
                  ? "生产模式模型已就绪"
                  : "生产模式仍被阻断"}
              </b>
              <small>
                {readiness?.blocking?.length
                  ? readiness.blocking.join(" · ")
                  : "所有 required 模块已 wired + bound + key"}
              </small>
            </div>
          </div>
          {!!readiness?.warnings?.length && (
            <div className="model-independence">
              <Icon name="shield" size={13} />
              <div>
                <b>独立性提醒</b>
                {readiness.warnings.map((item) => (
                  <small key={item}>{item}</small>
                ))}
              </div>
            </div>
          )}
          <p className="settings-note">
            绑定只写 provider/profile 标识；密钥可在上方运行时面板直接写入，仅进入本地 runtime
            会话内存，不写入 localStorage 或工作区导出。
          </p>
        </>
      )}
    </section>
  );
}
