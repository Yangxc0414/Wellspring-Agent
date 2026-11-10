import { useState } from "react";
import type { FormEvent } from "react";
import { DOMAINS, ACCESS_META, ACCESS_ORDER, MODE_META, MODE_ORDER } from "../domain/catalog";
import type { AccessMode, Mode } from "../domain/types";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

export function NewTaskDialog() {
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);
  const actions = useWorkspaceStore((state) => state.actions);
  const newTaskMode = useWorkspaceStore((state) => state.ui.newTaskMode);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const [workspaceId, setWorkspaceId] = useState(activeWorkspaceId);
  const [domain, setDomain] = useState(DOMAINS[0]);
  const [mode, setMode] = useState<Mode>(newTaskMode);
  const [access, setAccess] = useState<AccessMode>("ask");
  const close = () => actions.setUI({ newTaskOpen: false });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim() || !goal.trim()) {
      actions.notify("任务名称与研究目标都不能为空");
      return;
    }
    actions.createNewTask({ name, goal, domain, mode, workspaceId, access });
  };

  return (
    <div className="modal-layer" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) close();
    }}>
      <section className="modal new-task-modal" role="dialog" aria-modal="true" aria-label="新建任务">
        <header className="modal-head">
          <div>
            <span className="eyebrow">NEW TASK / LOCAL</span>
            <h2>新建一个任务</h2>
          </div>
          <button type="button" className="icon-button" onClick={close} aria-label="关闭新建任务">
            <Icon name="close" size={14} />
          </button>
        </header>
        <p className="modal-lede">任务会挂到当前工作区；不调用 API，也不上传任何内容。</p>

        <form onSubmit={submit}>
          <label className="field">
            <span>任务名称</span>
            <input
              autoFocus
              value={name}
              maxLength={60}
              placeholder="例如：钙钛矿界面钝化"
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label className="field">
            <span>研究目标</span>
            <textarea
              rows={3}
              value={goal}
              maxLength={300}
              placeholder="用一句话说明要验证什么、产出什么。"
              onChange={(event) => setGoal(event.target.value)}
            />
          </label>
          <div className="two-fields">
            <label className="field">
              <span>工作区</span>
              <select value={workspaceId} onChange={(event) => setWorkspaceId(event.target.value)}>
                {workspaces.map((workspace) => (
                  <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>领域</span>
              <select value={domain} onChange={(event) => setDomain(event.target.value)}>
                {DOMAINS.map((item) => <option key={item}>{item}</option>)}
              </select>
            </label>
          </div>
          <label className="field">
            <span>起始模式</span>
            <select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
              {MODE_ORDER.map((item) => (
                <option key={item} value={item}>{MODE_META[item].label} · {MODE_META[item].hint}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>访问级别</span>
            <select value={access} onChange={(event) => setAccess(event.target.value as AccessMode)}>
              {ACCESS_ORDER.map((item) => (
                <option key={item} value={item}>{ACCESS_META[item].label} · {ACCESS_META[item].hint}</option>
              ))}
            </select>
          </label>
          <footer className="modal-foot">
            <span className="form-note">初始消息会按模式自动生成；所有门禁仍按同一套状态推进。</span>
            <button type="button" className="text-button" onClick={close}>取消</button>
            <button type="submit" className="solid-button">创建任务</button>
          </footer>
        </form>
      </section>
    </div>
  );
}
