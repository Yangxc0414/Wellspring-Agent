import { useEffect, useRef, useState } from "react";
import { MODE_META, MODE_ORDER } from "../domain/catalog";
import type { Mode } from "../domain/types";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import type { IconName } from "./Icon";
import { Icon } from "./Icon";

const MODE_ICON: Record<Mode, IconName> = {
  research: "search",
  experiment: "play",
  writing: "book",
  auto: "spark"
};

export function ModePicker() {
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

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

  if (!task) return null;
  const current: Mode = task.auto.running ? "auto" : task.mode;
  const locked = task.auto.running;
  const meta = MODE_META[current];

  return (
    <div className="mode-picker" ref={rootRef}>
      <button
        type="button"
        className={`mode-trigger${open ? " is-open" : ""}${locked ? " is-locked" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        title="切换调研 / 实验 / 写作 / 全自动"
      >
        <span className="mode-trigger-icon">
          <Icon name={MODE_ICON[current]} size={12} />
        </span>
        <span className="mode-trigger-copy">
          <b>{meta.label}</b>
          <small>{meta.kicker.split(" / ")[0]}</small>
        </span>
        <span className={`mode-trigger-chevron${open ? " is-open" : ""}`}>
          <Icon name="chevron" size={10} />
        </span>
      </button>

      {open && (
        <div className="mode-menu" role="menu" aria-label="选择工作模式">
          <div className="mode-menu-head">
            <span>MODE</span>
            <em>影响建议与产物边界</em>
          </div>
          {MODE_ORDER.map((mode) => {
            const disabled = locked && mode !== "auto";
            return (
              <button
                key={mode}
                type="button"
                role="menuitemradio"
                aria-checked={mode === current}
                className={`mode-option${mode === current ? " is-on" : ""}`}
                disabled={disabled}
                onClick={() => {
                  setOpen(false);
                  actions.setMode(mode);
                }}
              >
                <span className="mode-option-icon">
                  <Icon name={MODE_ICON[mode]} size={13} />
                </span>
                <span className="mode-option-copy">
                  <span className="mode-option-line">
                    <b>{MODE_META[mode].label}</b>
                    <small>{MODE_META[mode].kicker}</small>
                  </span>
                  <em>{MODE_META[mode].hint}</em>
                </span>
                {mode === current && (
                  <span className="mode-option-check">
                    <Icon name="check" size={12} />
                  </span>
                )}
              </button>
            );
          })}
          {locked && (
            <p className="mode-menu-note">
              <Icon name="lock" size={11} />
              {task.auto.paused ? "全自动已暂停：先停止，再切换模式" : "全自动运行中：先停止，再切换模式"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
