import { useState } from "react";
import {
  clampModel,
  compressionNote,
  formatTokens,
  formatUsageTokens,
  modelProfile
} from "../domain/catalog";
import { siteHref } from "../domain/links";
import type { ModelProfile, ModelSettings } from "../domain/types";
import { useAllModelProfiles } from "../state/modelStore";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

export function ModelDialog() {
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const profiles = useAllModelProfiles();
  const [draft, setDraft] = useState<ModelSettings>(() => clampModel({ ...(task?.model ?? {
    profileId: "gpt-5",
    contextLimit: 128000,
    maxReply: 8192,
    thinkingStop: "medium",
    compression: "auto",
    threshold: 70,
    keepRecent: 6,
    summaryTokens: 512
  }) }));

  if (!task) return null;
  const profile = modelProfile(draft);
  const allowedStops = profile.kind === "budget"
    ? profile.stops.filter((stop) => Number(stop.value) < draft.maxReply)
    : profile.stops;
  const foundStopIndex = allowedStops.findIndex(
    (stop) => String(stop.value) === String(draft.thinkingStop)
  );
  const stopIndex = foundStopIndex >= 0 ? foundStopIndex : Math.max(allowedStops.length - 1, 0);
  const stop = allowedStops[stopIndex] ?? null;
  const thinkingDisabled = profile.kind === "unsupported" || allowedStops.length === 0;

  const selectProfile = (next: ModelProfile) => {
    setDraft((current) => {
      const maxReply = Math.min(current.maxReply, next.maxOutput);
      let thinkingStop = next.kind === "unsupported" ? null : next.defaultStop;
      if (next.kind === "budget" && typeof thinkingStop === "number" && thinkingStop >= maxReply) {
        const allowed = next.stops.filter((item) => Number(item.value) < maxReply);
        thinkingStop = allowed.length ? allowed[allowed.length - 1].value : null;
      }
      return {
        ...current,
        profileId: next.id,
        contextLimit: Math.min(current.contextLimit, next.contextWindow),
        maxReply,
        thinkingStop
      };
    });
  };

  const close = () => actions.setUI({ modelOpen: false });

  return (
    <div className="modal-layer" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) close();
    }}>
      <section className="modal model-modal" role="dialog" aria-modal="true" aria-label="模型设置">
        <header className="modal-head">
          <div>
            <span className="eyebrow">MODEL SETTINGS / STATIC</span>
            <h2>模型与预算</h2>
          </div>
          <button type="button" className="icon-button" onClick={close} aria-label="关闭模型设置">
            <Icon name="close" size={14} />
          </button>
        </header>
        <p className="modal-lede">能力来自模型配置；这里只决定本次用量与压缩策略。所有设置只保存在本地。</p>

        <div className="profile-grid">
          {profiles.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`profile-option${draft.profileId === item.id ? " is-on" : ""}`}
              onClick={() => selectProfile(item)}
            >
              <b>{item.short}</b>
              <span>{item.provider}</span>
              <em>{formatTokens(item.contextWindow)} ctx</em>
            </button>
          ))}
        </div>

        <div className="capability-line">
          <span className="capability-dot" />
          <span>{profile.name}</span>
          <b>{formatTokens(profile.contextWindow)} context · {formatTokens(profile.maxOutput)} output</b>
        </div>

        <div className="usage-panel">
          <div className="usage-head">
            <span>TOKEN USAGE</span>
            <em>演示数据 · 当前任务 · 各模型</em>
          </div>
          {profiles.map((item) => {
            const usage = task.usage[item.id] ?? { prompt: 0, completion: 0, requests: 0 };
            const rawPercent = (usage.prompt / item.contextWindow) * 100;
            const percent = Math.min(rawPercent, 100);
            return (
              <div className={`usage-row${draft.profileId === item.id ? " is-on" : ""}`} key={item.id}>
                <div className="usage-top">
                  <b>{item.short}</b>
                  <span>{formatUsageTokens(usage.prompt)} / {formatTokens(item.contextWindow)}</span>
                  <em>{percent < 10 ? percent.toFixed(1) : Math.round(percent)}%</em>
                </div>
                <div className="usage-track">
                  <i style={{ width: `${usage.prompt > 0 ? Math.max(percent, 1.5) : 0}%` }} />
                </div>
                <div className="usage-foot">
                  <span>in {formatUsageTokens(usage.prompt)}</span>
                  <span>out {formatUsageTokens(usage.completion)}</span>
                  <span>{usage.requests} req</span>
                </div>
              </div>
            );
          })}
          <p className="usage-note">按本任务新增消息与卡片长度本地估算并累加；切换到某模型后，新用量只记到该模型。不读取真实 API usage。</p>
        </div>

        <label className="range-field">
          <span>最大上下文 <b>{formatTokens(draft.contextLimit)}</b></span>
          <input
            type="range"
            min={8192}
            max={profile.contextWindow}
            step={8192}
            value={draft.contextLimit}
            onChange={(event) => setDraft((current) => ({ ...current, contextLimit: Number(event.target.value) }))}
          />
          <small>模型上限 {formatTokens(profile.contextWindow)} · 请求时不得超过</small>
        </label>

        <label className="range-field">
          <span>最大回复长度 <b>{formatTokens(draft.maxReply)}</b></span>
          <input
            type="range"
            min={512}
            max={profile.maxOutput}
            step={512}
            value={draft.maxReply}
            onChange={(event) => {
              const maxReply = Number(event.target.value);
              setDraft((current) => {
                if (profile.kind !== "budget") return { ...current, maxReply };
                const allowed = profile.stops.filter((item) => Number(item.value) < maxReply);
                const keep = allowed.some((item) => String(item.value) === String(current.thinkingStop))
                  ? current.thinkingStop
                  : allowed.length
                    ? allowed[allowed.length - 1].value
                    : null;
                return { ...current, maxReply, thinkingStop: keep };
              });
            }}
          />
          <small>模型上限 {formatTokens(profile.maxOutput)} · 实际发送时取更小值</small>
        </label>

        <div className="setting-block">
          <div className="setting-head">
            <span>思考强度</span>
            <b>{stop?.label ?? "off"}</b>
          </div>
          <input
            type="range"
            min={0}
            max={Math.max(allowedStops.length - 1, 0)}
            step={1}
            value={stopIndex}
            disabled={thinkingDisabled}
            onChange={(event) => {
              const next = allowedStops[Number(event.target.value)];
              setDraft((current) => ({ ...current, thinkingStop: next?.value ?? null }));
            }}
            aria-label="思考强度"
          />
          <div className="stop-labels">
            {allowedStops.length ? allowedStops.map((item) => (
              <span key={String(item.value)} className={String(item.value) === String(draft.thinkingStop) ? "is-on" : ""}>
                {item.label}
              </span>
            )) : <span className="is-on">off</span>}
          </div>
          <small className="setting-note">
            {profile.kind === "unsupported"
              ? profile.note
              : profile.kind === "budget"
                ? `${stop?.detail ?? "thinking off"} · budget 必须小于最大回复长度（Anthropic max_tokens > budget_tokens）。`
                : `${stop?.detail ?? "off"} · 档位由模型能力决定，不会超出模型声明的思考配置。`}
          </small>
        </div>

        <div className="setting-block">
          <div className="setting-head">
            <span>上下文压缩</span>
            <b>{draft.compression}</b>
          </div>
          <div className="segment">
            {(["off", "auto", "aggressive"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                className={draft.compression === mode ? "is-on" : ""}
                onClick={() => setDraft((current) => ({ ...current, compression: mode }))}
              >
                {mode}
              </button>
            ))}
          </div>
          <details className="advanced">
            <summary>
              <span className="chevron"><Icon name="chevron" size={10} /></span>
              压缩细节
            </summary>
            <label className="range-field compact">
              <span>触发阈值 <b>{draft.threshold}%</b></span>
              <input
                type="range"
                min={50}
                max={95}
                step={5}
                value={draft.threshold}
                onChange={(event) => setDraft((current) => ({ ...current, threshold: Number(event.target.value) }))}
              />
            </label>
            <div className="two-fields">
              <label><span>保留最近轮数</span>
                <input
                  type="number"
                  min={2}
                  max={20}
                  value={draft.keepRecent}
                  onChange={(event) => setDraft((current) => ({ ...current, keepRecent: Number(event.target.value) }))}
                />
              </label>
              <label><span>摘要 tokens</span>
                <input
                  type="number"
                  min={256}
                  max={4096}
                  step={128}
                  value={draft.summaryTokens}
                  onChange={(event) => setDraft((current) => ({ ...current, summaryTokens: Number(event.target.value) }))}
                />
              </label>
            </div>
          </details>
          <small className="setting-note">{compressionNote(draft)}</small>
        </div>

        <div className="model-preview">
          <span>REQUEST PREVIEW</span>
          <p>
            context ≤ <b>{formatTokens(draft.contextLimit)}</b> · reply ≤ <b>{formatTokens(draft.maxReply)}</b> ·
            thinking <b>{stop?.detail ?? "off"}</b>
          </p>
          <small>openai: reasoning_effort + max_completion_tokens · anthropic: thinking.budget_tokens（max_tokens 必须更大）</small>
        </div>

        <footer className="modal-foot">
          <a className="boundary-link" href={siteHref("models/")} target="_blank" rel="noopener noreferrer">
            Provider / Profile 高级配置 <Icon name="external" size={11} />
          </a>
          <button type="button" className="text-button" onClick={close}>取消</button>
          <button
            type="button"
            className="solid-button"
            onClick={() => {
              actions.saveModel(draft);
              close();
            }}
          >
            应用
          </button>
        </footer>
      </section>
    </div>
  );
}
