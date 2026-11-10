import { useEffect, useRef } from "react";
import { ACCESS_META } from "../domain/catalog";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

/**
 * PermissionDialog gates high-privilege actions, so keyboard focus must live inside
 * it while it is open: aria-modal alone does not move real focus, and an Enter on a
 * background button would otherwise fire a privileged action. Safe default = the
 * cancel button; on close focus returns to the element that opened the dialog.
 */
export function PermissionDialog() {
  const request = useWorkspaceStore((state) => state.ui.permissionRequest);
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const dialogRef = useRef<HTMLElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!request) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    const dialog = dialogRef.current;
    if (!dialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const focusables = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", onKeyDown);
    return () => {
      dialog.removeEventListener("keydown", onKeyDown);
      restoreRef.current?.focus?.();
    };
  }, [request]);

  if (!request) return null;
  const access = ACCESS_META[task?.access ?? "ask"];

  return (
    <div
      className="modal-layer permission-layer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) actions.cancelPermission();
      }}
    >
      <section className="modal permission-modal" role="alertdialog" aria-modal="true" aria-labelledby="permission-title" ref={dialogRef}>
        <div className="permission-mark">
          <Icon name="shield" size={19} />
        </div>
        <span className="eyebrow">ACCESS / {access.short}</span>
        <h2 id="permission-title">{request.title}</h2>
        <p className="permission-detail">{request.detail}</p>
        <div className="permission-current">
          <span>当前访问级别</span>
          <b>{access.label}</b>
        </div>
        <p className="permission-note">
          只允许这一次动作，不会改变后续权限；claim、EA、closure 与签名的人工门仍然保留。
        </p>
        <footer className="permission-actions">
          <button type="button" className="text-button" onClick={actions.cancelPermission} ref={cancelRef}>取消</button>
          <button type="button" className="solid-button" onClick={actions.confirmPermission}>允许本次</button>
        </footer>
      </section>
    </div>
  );
}
