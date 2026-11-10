import { useEffect, useState } from "react";
import {
  DEFAULT_SHORTCUTS,
  SHORTCUT_ACTIONS,
  formatShortcutLabel,
  shortcutConflict,
  shortcutFromEvent,
  validateShortcut
} from "../../domain/shortcuts";
import type { ShortcutAction } from "../../domain/types";
import { useWorkspaceStore } from "../../state/workspaceStore";
import { Icon } from "../Icon";
import { Card, PageHead } from "./SettingsSections";

const GROUPS: Array<"全局" | "视图" | "工具"> = ["全局", "视图", "工具"];

export function ShortcutSettingsPage() {
  const shortcuts = useWorkspaceStore((state) => state.preferences.shortcuts);
  const actions = useWorkspaceStore((state) => state.actions);
  const [recording, setRecording] = useState<ShortcutAction | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    if (!recording) return;
    const onKeyDown = (event: KeyboardEvent) => {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();
      if (event.repeat) return;

      if (event.key === "Escape") {
        setRecording(null);
        setError(null);
        return;
      }
      if (event.key === "Backspace" || event.key === "Delete") {
        actions.setShortcut(recording, DEFAULT_SHORTCUTS[recording]);
        setRecording(null);
        setError(null);
        setSaved(`已恢复「${SHORTCUT_ACTIONS.find((item) => item.id === recording)?.label}」的默认快捷键`);
        return;
      }

      const candidate = shortcutFromEvent(event);
      if (!candidate) return;
      const validation = validateShortcut(candidate);
      if (validation) {
        setError(validation);
        return;
      }
      const conflict = shortcutConflict(shortcuts, recording, candidate);
      if (conflict) {
        setError(`与「${conflict.label}」冲突，请换一个组合`);
        return;
      }

      actions.setShortcut(recording, candidate);
      setSaved(
        `已更新「${SHORTCUT_ACTIONS.find((item) => item.id === recording)?.label}」：${formatShortcutLabel(candidate)}`
      );
      setError(null);
      setRecording(null);
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [recording, shortcuts, actions]);

  const startRecording = (action: ShortcutAction) => {
    setRecording((current) => (current === action ? null : action));
    setError(null);
    setSaved(null);
  };

  const resetAll = () => {
    actions.setPreference("shortcuts", { ...DEFAULT_SHORTCUTS });
    setRecording(null);
    setError(null);
    setSaved("已恢复全部默认快捷键");
  };

  return (
    <div className="settings-section-body">
      <PageHead
        eyebrow="BASIC / SHORTCUTS"
        title="快捷键"
        description="录制自己的组合键。输入框聚焦时只保留 Ctrl/⌘ 组合；Esc 固定用于关闭浮层。"
        tag="LOCAL"
      />

      <Card
        title="键盘绑定"
        description="点击右侧键帽开始录制；按下新的组合键保存。Esc 取消，Backspace 恢复该项默认。"
      >
        <div className="shortcut-list">
          {GROUPS.map((group) => (
            <div className="shortcut-group" key={group}>
              <div className="shortcut-group-label">{group}</div>
              {SHORTCUT_ACTIONS.filter((item) => item.group === group).map((item) => {
                const isRecording = recording === item.id;
                const isCustom = shortcuts[item.id] !== DEFAULT_SHORTCUTS[item.id];
                return (
                  <div className={`shortcut-row${isRecording ? " is-recording" : ""}`} key={item.id}>
                    <span className="shortcut-copy">
                      <b>
                        {item.label}
                        {isCustom && <em>自定义</em>}
                      </b>
                      <small>{item.description}</small>
                    </span>
                    <button
                      type="button"
                      className={`shortcut-key-button${isRecording ? " is-recording" : ""}`}
                      onClick={() => startRecording(item.id)}
                      aria-pressed={isRecording}
                      aria-label={`修改${item.label}快捷键`}
                    >
                      {isRecording ? (
                        <>
                          <span className="shortcut-pulse" />
                          <span>按下组合键…</span>
                          <small>Esc 取消</small>
                        </>
                      ) : (
                        <>
                          <kbd>{formatShortcutLabel(shortcuts[item.id])}</kbd>
                          <span>修改</span>
                        </>
                      )}
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        <div className="shortcut-feedback" aria-live="polite">
          {error ? (
            <span className="is-error"><Icon name="alert" size={12} />{error}</span>
          ) : saved ? (
            <span className="is-saved"><Icon name="check" size={12} />{saved}</span>
          ) : (
            <span>Esc / Enter / Tab / Backspace / Delete 为固定键，不能绑定。</span>
          )}
        </div>

        <div className="shortcut-foot">
          <span>
            <Icon name="info" size={12} />
            快捷键保存在当前浏览器；输入框聚焦时，单字符快捷键不会触发。
          </span>
          <button type="button" className="settings-btn" onClick={resetAll}>
            恢复默认快捷键
          </button>
        </div>
      </Card>

      <Card title="固定按键" description="这些按键与输入/门禁语义绑定，不参与自定义。">
        <div className="shortcut-fixed">
          <span><kbd>Enter</kbd> 发送消息</span>
          <span><kbd>Shift + Enter</kbd> 换行</span>
          <span><kbd>Esc</kbd> 关闭浮层 / 取消权限 / 停止录制</span>
          <span><kbd>Backspace</kbd> 录制时恢复当前项默认</span>
        </div>
      </Card>
    </div>
  );
}
