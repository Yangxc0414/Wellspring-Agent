import {
  DEMO_BANNER,
  DEMO_FINISHED_NOTE,
  DEMO_STORYLINE_ORDER,
  DEMO_STORYLINES,
  demoGateHint,
  demoNarration,
  demoStagePlan,
  demoStageSpans,
  stageLabel
} from "../domain/demoPlayer";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

/**
 * Chrome for the one-click demo player (一键演示完整流程).
 *
 * Rendered inside the conversation while ui.demoPlayer is active. It drives a
 * REPLAY of a seeded transcript: storyline switch, stage rail, narration line,
 * and the claim-gate pause. The persistent honesty banner is part of the
 * component on purpose — progressive reveal shows an incomplete transcript
 * while the right-hand panels show final state, and that difference must be
 * stated on screen, not left for a viewer to discover (design/137).
 */
export function DemoPlayerBar() {
  const player = useWorkspaceStore((state) => state.ui.demoPlayer);
  const demoTask = useWorkspaceStore((state) =>
    state.ui.demoPlayer
      ? state.tasks.find((item) => item.id === state.ui.demoPlayer?.taskId)
      : undefined
  );
  const actions = useWorkspaceStore((state) => state.actions);
  if (!player) return null;
  const meta = DEMO_STORYLINES[player.storyline];
  if (!demoTask) return null;

  const stages = demoStagePlan(demoTask.messages);
  const spans = demoStageSpans(demoTask.messages);
  const total = demoTask.messages.length;
  const atGate =
    !player.finished &&
    !player.playing &&
    player.revealCount > 0 &&
    player.stageId === meta.gateStage &&
    spans.find((span) => span.stage === meta.gateStage)?.last === player.revealCount - 1;

  return (
    <section className={`demo-bar${atGate ? " is-gate" : ""}${player.finished ? " is-done" : ""}`} aria-label="演示播放器">
      <div className="demo-bar-main">
        <div className="demo-bar-story" role="tablist" aria-label="演示主线">
          {DEMO_STORYLINE_ORDER.map((id) => {
            const item = DEMO_STORYLINES[id];
            return (
              <button
                key={id}
                type="button"
                className={`demo-story-btn${player.storyline === id ? " is-on" : ""}`}
                onClick={() => actions.demoSwitch(id)}
                title={`${item.label}：${item.sub}（${item.basisNote}）`}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        <div className="demo-bar-stage">
          {player.finished ? (
            <span className="demo-stage-chip is-done">
              <Icon name="check" size={12} /> 演示完成 · {stages.length} 阶段
            </span>
          ) : player.stageId ? (
            <span className={`demo-stage-chip${atGate ? " is-gate" : ""}`}>
              {stageLabel(player.stageId)}
              <b>{player.stageId}</b>
            </span>
          ) : (
            <span className="demo-stage-chip">开始回放</span>
          )}
          <p className="demo-narration">
            {atGate
              ? demoGateHint(player.storyline)
              : player.finished
                ? DEMO_FINISHED_NOTE
                : demoNarration(player.storyline, player.stageId)}
          </p>
        </div>

        <div className="demo-bar-actions">
          {player.finished ? (
            <>
              <button
                type="button"
                className="demo-ctrl primary"
                onClick={() => actions.startDemoPlayer(player.storyline)}
              >
                <Icon name="refresh" size={13} /> 重播
              </button>
              <button type="button" className="demo-ctrl" onClick={() => actions.demoExit()}>
                <Icon name="close" size={13} /> 退出演示
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="demo-ctrl"
                onClick={() => actions.demoStep(-1)}
                title="回到上一阶段（含其全部消息）"
              >
                <Icon name="arrow" size={13} />
              </button>
              <button
                type="button"
                className="demo-ctrl primary"
                onClick={() => actions.demoTogglePlay()}
                title={player.playing ? "暂停回放" : "继续回放"}
              >
                <Icon name={player.playing ? "pause" : "play"} size={13} />
                {player.playing ? "暂停" : atGate ? "继续 →" : "播放"}
              </button>
              <button
                type="button"
                className="demo-ctrl"
                onClick={() => actions.demoStep(1)}
                title="整段揭示下一阶段"
              >
                <Icon name="step" size={13} />
              </button>
              {atGate && meta.allowDemoSign && (
                <button
                  type="button"
                  className="demo-ctrl sign"
                  onClick={() => actions.demoSignGate()}
                  title="演示人签后的状态；只存在于页面内存，刷新即回待签"
                >
                  模拟人签（演示）
                </button>
              )}
              <button type="button" className="demo-ctrl" onClick={() => actions.demoExit()} title="退出演示模式（转录恢复完整）">
                <Icon name="close" size={13} />
                退出
              </button>
            </>
          )}
        </div>
      </div>

      <div className="demo-bar-sub">
        <ol className="demo-rail" aria-label="阶段进度">
          {stages.map((stageId) => {
            const span = spans.find((item) => item.stage === stageId);
            const revealed = Boolean(span && player.revealCount > span.first);
            const active = player.stageId === stageId;
            return (
              <li key={stageId}>
                <button
                  type="button"
                  className={`demo-rail-dot${revealed ? " is-revealed" : ""}${active ? " is-active" : ""}`}
                  onClick={() => actions.demoSeekStage(stageId)}
                  title={`${stageId} ${stageLabel(stageId)} · 跳到该阶段`}
                >
                  <i />
                  <span>{stageId}</span>
                </button>
              </li>
            );
          })}
          <li className="demo-rail-count" title={`已揭示 ${player.revealCount}/${total} 条消息`}>
            {player.revealCount}/{total}
          </li>
        </ol>
        <p className="demo-banner">
          {DEMO_BANNER}
          <b>{meta.basisNote}</b>
        </p>
      </div>
    </section>
  );
}
