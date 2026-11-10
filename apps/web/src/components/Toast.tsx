import { useEffect } from "react";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

export function Toast() {
  const toast = useWorkspaceStore((state) => state.toast);
  const dismiss = useWorkspaceStore((state) => state.actions.dismissToast);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(dismiss, 2800);
    return () => window.clearTimeout(timer);
  }, [toast, dismiss]);

  if (!toast) return null;

  return (
    <div className="toast" role="status" aria-live="polite" key={toast.id}>
      <span className="toast-icon"><Icon name="check" size={12} /></span>
      <span>{toast.text}</span>
      <button type="button" onClick={dismiss} aria-label="关闭提示"><Icon name="close" size={11} /></button>
    </div>
  );
}
