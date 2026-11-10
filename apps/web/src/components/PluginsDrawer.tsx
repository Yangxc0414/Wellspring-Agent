import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { PLUGIN_PRESETS } from "../domain/catalog";
import type { Plugin } from "../domain/types";
import { useDialogFocus } from "../hooks/ui";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

type PresetId = Plugin["preset"];

function presetForm(preset: PresetId) {
  const base = PLUGIN_PRESETS[preset];
  return {
    preset,
    name: base.name,
    url: base.url,
    auth: base.auth,
    toolsets: base.toolsets.join(","),
    readonly: base.readonly
  };
}

export function PluginsDrawer() {
  const selectedTask = useWorkspaceStore(selectCurrentTask);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);
  const task = welcomeOpen ? undefined : selectedTask;
  const plugins = useWorkspaceStore((state) => state.plugins);
  const actions = useWorkspaceStore((state) => state.actions);
  const [form, setForm] = useState(() => presetForm("github"));
  const dialogRef = useRef<HTMLElement>(null);
  useDialogFocus(dialogRef, true);

  const calls = task?.toolCalls ?? [];
  const close = () => actions.setUI({ pluginsOpen: false });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const preset = PLUGIN_PRESETS[form.preset];
    if (!form.name.trim()) {
      actions.notify("请输入连接器名称");
      return;
    }
    if (preset.transport === "streamable-http" && !form.url.trim()) {
      actions.notify("Streamable HTTP 需要 Endpoint URL");
      return;
    }
    actions.registerPlugin({
      name: form.name.trim(),
      preset: form.preset,
      transport: preset.transport,
      url: form.url.trim(),
      auth: form.auth,
      readonly: form.readonly,
      toolsets: form.toolsets.split(",").map((item) => item.trim()).filter(Boolean),
      note: `${preset.note} 静态配置；未发起真实连接。`
    });
  };

  return (
    <div className="drawer-layer" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) close();
    }}>
      <aside className="plugin-drawer" role="dialog" aria-modal="true" aria-label="插件与 MCP" ref={dialogRef}>
        <header className="drawer-head">
          <div>
            <span className="eyebrow">PLUGINS / MCP</span>
            <h2>插件与连接器</h2>
          </div>
          <button type="button" className="icon-button" onClick={close} aria-label="关闭插件面板">
            <Icon name="close" size={14} />
          </button>
        </header>
        <div className="drawer-body">
          <p className="drawer-note">
            MCP server 只暴露工具；工具结果进入会话前必须逐次批准。密钥与 OAuth 留在 runtime，不进入浏览器。当前为静态预览，不发起真实连接。
          </p>
          {!task && (
            <p className="drawer-note no-margin">
              当前没有活动会话：可以登记连接器，但启用与工具调用需要任务上下文；先创建会话再回来。
            </p>
          )}

          <div className="plugin-list">
            {plugins.map((plugin) => {
              const enabled = Boolean(task?.plugins.includes(plugin.id));
              return (
                <article className={`plugin-card${enabled ? " is-on" : ""}`} key={plugin.id}>
                  <div className="plugin-head">
                    <span className="plugin-mark"><Icon name="terminal" size={13} /></span>
                    <div className="plugin-title">
                      <b>{plugin.name}</b>
                      <small>{plugin.transport} · {plugin.auth} · {plugin.readonly ? "read-only" : "writable"}</small>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={enabled}
                      className={`switch${enabled ? " is-on" : ""}`}
                      onClick={() => actions.togglePlugin(plugin.id)}
                      disabled={!task}
                      aria-label={`${enabled ? "停用" : "启用"} ${plugin.name}`}
                      title={task ? undefined : "先创建会话再启用连接器"}
                    >
                      <i />
                    </button>
                  </div>
                  <div className="plugin-endpoint">{plugin.url || "local registration only"}</div>
                  <div className="plugin-toolsets">
                    {plugin.toolsets.map((tool) => <span key={tool}>{tool}</span>)}
                  </div>
                  <div className="plugin-foot">
                    <small>{plugin.note}</small>
                    {enabled && plugin.preset === "github" && (
                      <button type="button" className="mini-button" onClick={actions.proposeToolCall}>
                        提议只读调用
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>

          <section className="drawer-section">
            <div className="section-title">
              <span>RECENT TOOL CALLS</span>
              <em>{calls.length} CALLS</em>
            </div>
            {!task ? (
              <p className="drawer-note no-margin">没有活动会话；工具调用需要任务上下文。</p>
            ) : calls.length ? (
              <div className="call-list">
                {calls.map((call) => (
                  <div className={`call-card ${call.status}`} key={call.id}>
                    <div className="call-head">
                      <span className="call-tool">{call.tool}</span>
                      <span className={`badge ${call.status === "approved" ? "ok" : call.status === "denied" ? "bad" : "warn"}`}>
                        {call.status}
                      </span>
                    </div>
                    <code>{call.args}</code>
                    <span className="call-server">{call.server} · {call.at}</span>
                    {call.result && <p className="call-result">{call.result}</p>}
                    {call.status === "proposed" && (
                      <div className="call-actions">
                        <button type="button" className="action-button primary" onClick={() => actions.approveToolCall(call.id)}>
                          批准结果
                        </button>
                        <button type="button" className="action-button danger" onClick={() => actions.denyToolCall(call.id)}>
                          拒绝
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <p className="drawer-note no-margin">还没有工具调用。启用 GitHub MCP 后可生成一个只读搜索提案。</p>
            )}
          </section>

          <details className="plugin-add" open>
            <summary>
              <span className="chevron"><Icon name="chevron" size={10} /></span>
              接入 MCP Server
            </summary>
            <form className="plugin-form" onSubmit={submit}>
              <label className="field">
                <span>预设</span>
                <select
                  value={form.preset}
                  onChange={(event) => setForm(presetForm(event.target.value as PresetId))}
                >
                  <option value="github">GitHub MCP · Streamable HTTP / OAuth</option>
                  <option value="custom">Custom Streamable HTTP</option>
                  <option value="local">Local MCP（仅登记，不执行）</option>
                </select>
              </label>
              <div className="two-fields">
                <label className="field"><span>名称</span>
                  <input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
                </label>
                <label className="field"><span>认证</span>
                  <select
                    value={form.auth}
                    onChange={(event) => setForm({ ...form, auth: event.target.value as Plugin["auth"] })}
                  >
                    <option value="oauth">OAuth（runtime）</option>
                    <option value="env">Environment / PAT</option>
                    <option value="none">None</option>
                  </select>
                </label>
              </div>
              <label className="field"><span>Endpoint URL</span>
                <input
                  value={form.url}
                  spellCheck={false}
                  placeholder="https://…/mcp/"
                  onChange={(event) => setForm({ ...form, url: event.target.value })}
                />
              </label>
              <label className="field"><span>工具集</span>
                <input
                  value={form.toolsets}
                  onChange={(event) => setForm({ ...form, toolsets: event.target.value })}
                />
              </label>
              <label className="switch-row">
                <span><b>只读模式</b><small>优先禁止写操作；GitHub 使用只读端点/头</small></span>
                <input
                  type="checkbox"
                  checked={form.readonly}
                  onChange={(event) => setForm({ ...form, readonly: event.target.checked })}
                />
              </label>
              <div className="form-actions">
                <button
                  type="button"
                  className="text-button"
                  onClick={() => actions.notify("连接测试为静态模拟：未发送网络请求")}
                >
                  测试连接（静态）
                </button>
                <button type="submit" className="solid-button">{task ? "保存并启用" : "保存（会话内启用）"}</button>
              </div>
            </form>
          </details>

          <div className="security-note">
            <Icon name="shield" size={12} />
            <span>UNTRUSTED：工具结果不进入 span/claim，除非经过人工审阅并绑定证据。</span>
          </div>
        </div>
      </aside>
    </div>
  );
}
