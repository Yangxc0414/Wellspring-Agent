import { ACCESS_META } from "../domain/catalog";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

export function PermissionDialog() {
  const request = useWorkspaceStore((state) => state.ui.permissionRequest);
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
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
      <section className="modal permission-modal" role="alertdialog" aria-modal="true" aria-labelledby="permission-title">
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
          <button type="button" className="text-button" onClick={actions.cancelPermission}>取消</button>
          <button type="button" className="solid-button" onClick={actions.confirmPermission}>允许本次</button>
        </footer>
      </section>
    </div>
  );
}
