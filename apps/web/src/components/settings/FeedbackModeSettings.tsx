import { useState } from "react";
import { Card } from "./SettingsSections";

/**
 * 反馈测量模式选择（73- 号设计文档 §2.2）。
 *
 * 自包含组件：模式持久化在独立 localStorage 键，不进 workspaceStore——
 * 测量命令仍走 CLI/MCP，前端只做声明层（真实执行留在本地 runtime/CLI 边界内）。
 * 单会话 = 传统 A/B（同 session 答两臂，不能证明记忆增益）；
 * 多会话 = 每臂独立宿主会话（host_label 分离在 compare 时强制校验）。
 */

const STORAGE_KEY = "feedback-measurement-mode";

export type FeedbackMeasurementMode = "single" | "multi";

export function readFeedbackMeasurementMode(): FeedbackMeasurementMode {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "multi" ? "multi" : "single";
  } catch {
    return "single";
  }
}

const MODES: Array<{
  id: FeedbackMeasurementMode;
  label: string;
  proves: string;
  caveat: string;
}> = [
  {
    id: "single",
    label: "单会话（传统 A/B）",
    proves: "同一个宿主会话依次作答两臂：能证明度量与流程可跑通，产出成对读数。",
    caveat: "不能证明记忆增益——同源偏差：作答风格与上下文污染同时影响两臂。"
  },
  {
    id: "multi",
    label: "多会话（每臂独立会话）",
    proves: "两臂由不同宿主会话作答（host_label 分离强制校验，相同即 blocked）：剔除同源偏差后的成对差异。",
    caveat: "仍非独立人工金标准；host_label 自报未验证。"
  }
];

export function FeedbackModeSettings() {
  const [mode, setMode] = useState<FeedbackMeasurementMode>(readFeedbackMeasurementMode);

  const select = (next: FeedbackMeasurementMode) => {
    setMode(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable: the choice stays session-local */
    }
  };

  return (
    <Card
      title="反馈测量模式"
      description="M1/M2 反馈实验的作答会话模式；选择是声明层，测量命令仍由本地 CLI/MCP 执行。"
    >
      <div className="feedback-mode-options" role="radiogroup" aria-label="反馈测量模式">
        {MODES.map((item) => (
          <label
            key={item.id}
            className={`feedback-mode-option${mode === item.id ? " is-active" : ""}`}
          >
            <input
              type="radio"
              name="feedback-measurement-mode"
              value={item.id}
              checked={mode === item.id}
              onChange={() => select(item.id)}
            />
            <span>
              <b>{item.label}</b>
              <small>{item.proves}</small>
              <small className="feedback-mode-caveat">{item.caveat}</small>
            </span>
          </label>
        ))}
      </div>
      <p className="feedback-mode-note">
        当前选择：<b>{mode === "multi" ? "多会话（每臂独立会话）" : "单会话（传统 A/B）"}</b>。宿主执行
        <code>memory ab compare --sessions {mode}</code> 时按此模式校验。
      </p>
    </Card>
  );
}
