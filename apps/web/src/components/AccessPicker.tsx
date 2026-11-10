import { useEffect, useRef, useState } from "react";
import { ACCESS_META, ACCESS_ORDER } from "../domain/catalog";
import type { AccessMode } from "../domain/types";
import { Icon } from "./Icon";

export function AccessPicker({
  value,
  onChange,
  disabled = false,
  placement = "up"
}: {
  value: AccessMode;
  onChange: (mode: AccessMode) => void;
  disabled?: boolean;
  placement?: "up" | "down";
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const meta = ACCESS_META[value];

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
    <div className="access-picker" ref={rootRef}>
      <button
        type="button"
        className={`access-trigger is-${meta.tone}${open ? " is-open" : ""}`}
        onClick={() => {
          if (disabled) return;
          setOpen((current) => !current);
        }}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-disabled={disabled}
        disabled={disabled}
        title={disabled ? "全自动运行中：先停止再调整访问级别" : `${meta.label} · ${meta.hint}`}
      >
        <Icon name="shield" size={12} />
        <span>{meta.label}</span>
        <span className={`access-trigger-chevron${open ? " is-open" : ""}`}>
          <Icon name="chevron" size={9} />
        </span>
      </button>

      {open && (
        <div className={`access-menu is-${placement}`} role="menu" aria-label="选择访问级别">
          <div className="access-menu-head">
            <span>ACCESS</span>
            <em>会话级权限</em>
          </div>
          {ACCESS_ORDER.map((mode) => {
            const item = ACCESS_META[mode];
            return (
              <button
                key={mode}
                type="button"
                role="menuitemradio"
                aria-checked={mode === value}
                className={`access-option is-${item.tone}${mode === value ? " is-on" : ""}`}
                onClick={() => {
                  setOpen(false);
                  onChange(mode);
                }}
              >
                <span className="access-option-icon"><Icon name="shield" size={13} /></span>
                <span className="access-option-copy">
                  <span className="access-option-line">
                    <b>{item.label}</b>
                    <small>{item.short}</small>
                  </span>
                  <em>{item.description}</em>
                </span>
                {mode === value && <span className="access-option-check"><Icon name="check" size={12} /></span>}
              </button>
            );
          })}
          <p className="access-menu-note">
            <Icon name="info" size={11} />
            claim / EA / closure / signature 的人工门不受此设置影响；只读模式仍会阻止设计、冻结与签署。
          </p>
        </div>
      )}
    </div>
  );
}
