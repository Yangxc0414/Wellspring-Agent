import { useEffect, useRef, useState } from "react";
import { formatBytes } from "../domain/utils";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

export function WorkspacePicker({
  value,
  onChange,
  placement = "up"
}: {
  value: string;
  onChange: (workspaceId: string) => void;
  placement?: "up" | "down";
}) {
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const current = workspaces.find((workspace) => workspace.id === value) ?? workspaces[0];

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

  if (!current) return null;

  return (
    <div className="workspace-picker" ref={rootRef}>
      <button
        type="button"
        className={`workspace-trigger${open ? " is-open" : ""}`}
        onClick={() => setOpen((state) => !state)}
        aria-haspopup="menu"
        aria-expanded={open}
        title="选择工作区"
      >
        <Icon name="folder" size={12} />
        <span>{current.name}</span>
        <span className={`workspace-trigger-chevron${open ? " is-open" : ""}`}>
          <Icon name="chevron" size={9} />
        </span>
      </button>

      {open && (
        <div className={`workspace-menu is-${placement}`} role="menu" aria-label="选择工作区">
          <div className="workspace-menu-head">
            <span>WORKSPACE</span>
            <em>新会话将挂到此处</em>
          </div>
          {workspaces.map((workspace) => (
            <button
              key={workspace.id}
              type="button"
              role="menuitemradio"
              aria-checked={workspace.id === current.id}
              className={`workspace-option${workspace.id === current.id ? " is-on" : ""}`}
              onClick={() => {
                setOpen(false);
                onChange(workspace.id);
              }}
            >
              <span className="workspace-option-icon"><Icon name="folder" size={13} /></span>
              <span className="workspace-option-copy">
                <span className="workspace-option-line">
                  <b>{workspace.name}</b>
                  {workspace.folder && <small>FS</small>}
                </span>
                <em>
                  {workspace.folder
                    ? `${workspace.folder.files} files · ${formatBytes(workspace.folder.bytes)} · metadata only`
                    : workspace.note}
                </em>
              </span>
              {workspace.id === current.id && <span className="workspace-option-check"><Icon name="check" size={12} /></span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
