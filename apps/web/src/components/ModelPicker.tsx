import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import {
  activeThinkingStop,
  modelProfile,
  modelSettingsForProfile,
  thinkingLabel
} from "../domain/catalog";
import type { ModelSettings, ModelStop } from "../domain/types";
import {
  loadRuntimeModelSnapshot,
  type RuntimeModelSnapshot
} from "../adapters/modelRuntime";
import { useAllModelProfiles } from "../state/modelStore";
import { Icon } from "./Icon";

const THINKING_LABELS: Record<string, string> = {
  minimal: "最低",
  low: "低",
  medium: "中",
  high: "高",
  max: "最高"
};

function displayStopLabel(stop: ModelStop): string {
  return THINKING_LABELS[String(stop.value)] ?? stop.label;
}

export function ModelPicker({
  value,
  settings,
  onChange,
  onThinkingChange,
  onAdvanced
}: {
  value: string;
  settings?: ModelSettings;
  onChange: (profileId: string) => void;
  onThinkingChange?: (stop: string | number | null) => void;
  onAdvanced?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [runtime, setRuntime] = useState<RuntimeModelSnapshot | null>(null);
  const profiles = useAllModelProfiles();
  const rootRef = useRef<HTMLDivElement>(null);
  const current = settings ?? modelSettingsForProfile(value);
  const profile = modelProfile(current);
  const thinking = thinkingLabel(current);
  const activeStop = activeThinkingStop(current);
  const allowedStops = profile.kind === "budget"
    ? profile.stops.filter((stop) => Number(stop.value) < current.maxReply)
    : profile.stops;
  const stopIndex = Math.max(
    allowedStops.findIndex((stop) => String(stop.value) === String(current.thinkingStop)),
    0
  );
  const thinkingDisabled =
    profile.kind === "unsupported" ||
    allowedStops.length === 0 ||
    current.thinkingStop === null ||
    !onThinkingChange;
  const progress = allowedStops.length > 1
    ? (stopIndex / (allowedStops.length - 1)) * 100
    : 0;

  useEffect(() => {
    if (!open || runtime) return;
    let cancelled = false;
    loadRuntimeModelSnapshot()
      .then((snapshot) => {
        if (!cancelled) setRuntime(snapshot);
      })
      .catch(() => {
        /* runtime offline: keep the local model catalog */
      });
    return () => {
      cancelled = true;
    };
  }, [open, runtime]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="model-picker" ref={rootRef}>
      <button
        type="button"
        className={`model-trigger${open ? " is-open" : ""}`}
        onClick={() => setOpen((currentOpen) => !currentOpen)}
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={__STATIC_ONLY__}
        title={__STATIC_ONLY__ ? "静态演示模式：模型不可运行，选择器已禁用" : `${profile.name} · ${thinking}`}
      >
        <span className="model-trigger-dot" />
        <span className="model-trigger-name">{profile.short}</span>
        <em>{__STATIC_ONLY__ ? "演示态" : thinking}</em>
        <span className={`model-trigger-chevron${open ? " is-open" : ""}`}>
          <Icon name="chevron" size={9} />
        </span>
      </button>

      {open && (
        <div className="model-menu" role="menu" aria-label="选择模型与思考强度">
          <div className="model-menu-head">
            <span>MODEL</span>
            <em>能力来自 Profile</em>
          </div>
          <p className="model-menu-note">
            <Icon name="info" size={11} />
            此处仅影响本地模拟；真实 runtime 绑定与 key 在“设置 → 模型设置”。
          </p>
          {runtime && (
            <div className="model-runtime-note">
              <span>RUNTIME BINDINGS</span>
              <b>
                {runtime.readiness?.production_ready
                  ? "production ready"
                  : "test / fallback"}
              </b>
              <em>
                {Object.entries(runtime.readiness?.modules ?? {})
                  .slice(0, 5)
                  .map(([id, item]) => `${id}:${item.bound_profile || "fallback"}`)
                  .join(" · ")}
              </em>
              <small>选择上面的模型不会改变这些绑定。</small>
            </div>
          )}
          {profiles.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitemradio"
              aria-checked={item.id === profile.id}
              className={`model-option${item.id === profile.id ? " is-on" : ""}`}
              onClick={() => onChange(item.id)}
            >
              <span className="model-option-mark"><Icon name="cpu" size={13} /></span>
              <span className="model-option-copy">
                <span className="model-option-line">
                  <b>{item.name}</b>
                  <small>{item.provider}</small>
                </span>
                <em>
                  {Math.round(item.contextWindow / 1000)}k ctx · {Math.round(item.maxOutput / 1000)}k out ·{" "}
                  {item.kind === "unsupported" ? "thinking off" : `thinking ${item.defaultStop}`}
                </em>
              </span>
              {item.id === profile.id && <span className="model-option-check"><Icon name="check" size={12} /></span>}
            </button>
          ))}
          <div className="model-thinking">
            <div className="model-thinking-head">
              <span>思考强度</span>
              <b>{activeStop ? displayStopLabel(activeStop) : "关闭"}</b>
            </div>
            <input
              type="range"
              className="model-thinking-range"
              min={0}
              max={Math.max(allowedStops.length - 1, 0)}
              step={1}
              value={stopIndex}
              disabled={thinkingDisabled}
              onChange={(event) => {
                const next = allowedStops[Number(event.target.value)];
                onThinkingChange?.(next?.value ?? null);
              }}
              style={{ "--thinking-progress": `${progress}%` } as CSSProperties}
              aria-label="思考强度"
              title={thinkingDisabled ? (profile.kind === "unsupported" ? profile.note : "当前模型/回复长度不可调思考强度") : "拖动调节思考强度"}
            />
            <div className="model-thinking-ticks">
              {allowedStops.length ? allowedStops.map((stop) => (
                <span key={String(stop.value)} className={String(stop.value) === String(current.thinkingStop) ? "is-on" : ""}>
                  {displayStopLabel(stop)}
                </span>
              )) : <span className="is-on">关闭</span>}
            </div>
            <small>
              {thinkingDisabled
                ? profile.kind === "unsupported"
                  ? profile.note
                  : "当前模型或回复长度下不可调；可在高级设置中检查。"
                : activeStop?.detail ?? "思考关闭"}
            </small>
          </div>
          {onAdvanced ? (
            <button
              type="button"
              className="model-advanced"
              onClick={() => {
                setOpen(false);
                onAdvanced();
              }}
            >
              <Icon name="sliders" size={11} />
              上下文、回复长度与压缩设置
              <Icon name="arrow" size={11} />
            </button>
          ) : (
            <p className="model-menu-note">
              <Icon name="info" size={11} />
              思考强度会随新会话保存；上下文、回复长度与压缩在会话内细调。
            </p>
          )}
        </div>
      )}
    </div>
  );
}
