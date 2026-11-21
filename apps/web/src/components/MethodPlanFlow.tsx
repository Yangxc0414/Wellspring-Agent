import { useState } from "react";
import type { HumanTurn } from "../domain/humanTurns";
import { iterationLabel } from "../domain/methodModel";
import {
  contractKeyFor,
  normalizeStageId,
  slotCommand,
  type MethodFlow,
  type MethodFlowStep
} from "../domain/stagePlan";
import { StageContract } from "./StageContract";

/**
 * RESEARCH FLOW 的「方法编排」视图（design/169）。
 *
 * 面板原来只有一条轴：会话里的 stage 标签。问题是十个方法共用同一张图，
 * 于是「执行流程」看起来跟研究方法无关。这里按三条轨道把关系说清：
 *
 *  ① 方法声明编排——顺序由组合接线决定（验证式：假设先于方案；探索式：
 *     方案先于证据、假设事后归纳），每步带本方法在该阶段的任务卡与接线理由；
 *  ② 治理固定——闭包与经验不属于任何方法的 fit_stages，所有会话都走；
 *  ③ 计划外——会话实际走过但本方法没声明的阶段。执行器当前仍全阶段执行
 *     （design/165），把这条差异藏起来才是误导。
 *
 * 三条轨道都是只读投影：点击节点只做定位，不改流程、不产生 Claim。
 */

interface Props {
  flow: MethodFlow;
  turns: HumanTurn[];
  playerStageId: string | null;
  onFocusStage: (stageId: string) => void;
  onFocusMessage: (messageId: string) => void;
}

function turnsFor(step: MethodFlowStep, turns: HumanTurn[]): HumanTurn[] {
  return turns.filter((turn) => turn.stage !== null && step.sessionStageIds.includes(turn.stage));
}

export function MethodPlanFlow({ flow, turns, playerStageId, onFocusStage, onFocusMessage }: Props) {
  const [open, setOpen] = useState<string | null>(flow.steps[0]?.slot ?? null);
  const [extrasOpen, setExtrasOpen] = useState(false);
  const isCurrent = (step: MethodFlowStep) =>
    Boolean(playerStageId && step.sessionStageIds.includes(playerStageId));
  // The demo player can sit on a stage the method does not declare (that is the
  // whole point of track ③). Keep that row visible instead of letting the
  // highlight vanish for one beat.
  const currentExtra = playerStageId
    ? flow.extras.find((extra) => normalizeStageId(extra.id) === normalizeStageId(playerStageId))
    : undefined;
  const showExtras = extrasOpen || Boolean(currentExtra);

  const renderStep = (step: MethodFlowStep, kind: "plan" | "governance") => {
    const current = isCurrent(step);
    const expanded = open === step.slot || current;
    const stepTurns = turnsFor(step, turns);
    const cmd = slotCommand(step.slot);
    const contractKey = contractKeyFor(step.slot);
    const absent = kind === "plan" && step.messageCount === 0;
    return (
      <li
        key={`${kind}-${step.slot}`}
        className={[
          "flow-stage",
          step.messageCount > 0 ? "is-done" : "",
          absent ? "is-absent" : "",
          expanded ? "is-open" : "",
          step.gate ? "is-human" : "",
          current ? "is-current" : ""
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <button
          type="button"
          className="flow-stage-head"
          onClick={() => {
            setOpen(expanded && !current ? null : step.slot);
            if (step.sessionStageIds[0]) onFocusStage(step.sessionStageIds[0]);
          }}
          aria-expanded={expanded}
          title={
            step.sessionStageIds.length
              ? "展开方法任务卡，并定位到会话中该阶段的消息"
              : "本会话没有该阶段的消息；只能展开阅读方法任务"
          }
        >
          <span className="flow-stage-mark">{step.messageCount > 0 ? "✓" : "·"}</span>
          <span className="flow-stage-id">{step.slot}</span>
          <span className="flow-stage-label">{step.name}</span>
          {kind === "governance" ? (
            <span className="flow-plan-fixed">治理固定</span>
          ) : (
            <span className={`flow-plan-count ${absent ? "is-absent" : ""}`}>
              {absent ? "本会话未出现" : `${step.messageCount} 条`}
            </span>
          )}
          {step.gate ? <span className="flow-stage-gate">{step.gate}</span> : null}
          {step.sessionStageIds.length ? (
            <span
              className="flow-stage-jump"
              role="button"
              tabIndex={0}
              title="跳到会话中对应消息"
              aria-label={`跳到会话中 ${step.slot} ${step.name} 对应的消息`}
              onClick={(event) => {
                event.stopPropagation();
                onFocusStage(step.sessionStageIds[0]);
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  event.stopPropagation();
                  onFocusStage(step.sessionStageIds[0]);
                }
              }}
            >
              ↗
            </span>
          ) : null}
        </button>
        {expanded ? (
          <div className="flow-stage-body">
            {stepTurns.length > 0 && (
              <div className="flow-human-turns">
                <span>人的表述</span>
                {stepTurns.map((turn) => (
                  <button
                    type="button"
                    key={turn.id}
                    className="flow-human-turn"
                    onClick={() => onFocusMessage(turn.id)}
                    title="定位到会话中这条发言"
                  >
                    <i>{turn.at}</i>
                    {turn.text.length > 80 ? `${turn.text.slice(0, 80)}…` : turn.text}
                  </button>
                ))}
              </div>
            )}
            {step.task ? (
              <p className="flow-plan-task">
                <span>本方法在这一阶段</span>
                {step.task}
              </p>
            ) : null}
            {step.rationale ? (
              <p className="flow-plan-rationale">
                <span>{step.element} · 接线理由</span>
                {step.rationale}
              </p>
            ) : null}
            {step.uncovered ? (
              <p className="flow-plan-rationale is-warn">
                <span>未覆盖</span>
                该方法声明了此阶段，但组合接线没有走到它——计划里保留位置，执行层尚未接上。
              </p>
            ) : null}
            {cmd ? (
              <div className="flow-kv">
                <span>命令</span>
                <code>{cmd}</code>
              </div>
            ) : null}
            {contractKey ? <StageContract stageId={contractKey} /> : null}
          </div>
        ) : null}
      </li>
    );
  };

  const plannedCount = flow.steps.length;
  const governanceCount = flow.governance.length;

  return (
    <div className="flow-plan-flow">
      <div className="flow-plan-head">
        <div className="flow-plan-name">
          <span>研究方法</span>
          <b>{flow.methodName}</b>
          <em>{flow.methodNameEn}</em>
        </div>
        <div className="flow-plan-chips">
          <span className="flow-plan-chip is-composition">{flow.compositionLabel}</span>
          {flow.iterationKind ? (
            <span className="flow-plan-chip" title={flow.iterationDetail}>
              停止规则 · {iterationLabel(flow.iterationKind)}
            </span>
          ) : null}
        </div>
        {flow.compositionSub ? <p className="flow-plan-sub">{flow.compositionSub}</p> : null}
      </div>

      {flow.orderMismatch ? (
        <div className="flow-plan-divergence" role="status">
          <b>顺序与计划不一致</b>
          <p>
            计划 <code>{flow.orderMismatch.planned.join(" → ") || "—"}</code>；会话{" "}
            <code>{flow.orderMismatch.actual.join(" → ") || "—"}</code>。
            组合接线决定的是这条方法应走的顺序；当前执行器仍按固定阶段跑，所以这条会话没有按计划剪裁。
          </p>
        </div>
      ) : (
        <div className="flow-plan-aligned" role="status">
          ✓ 在会话已走的阶段上，顺序与计划一致
        </div>
      )}

      <section className="context-card">
        <div className="card-label">
          <span>RESEARCH FLOW</span>
          <em>
            METHOD PLAN · {plannedCount}
            {governanceCount ? ` + ${governanceCount} 治理` : ""}
          </em>
        </div>

        <div className="flow-plan-track">
          <span>①</span>
          <b>方法声明编排</b>
          <em>顺序来自组合接线，不是通用模板</em>
        </div>
        <ol className="flow-stages">{flow.steps.map((step) => renderStep(step, "plan"))}</ol>
        {flow.missing.length > 0 && (
          <p className="flow-plan-note">
            计划内、但本会话没有走到的阶段：<code>{flow.missing.join(" · ")}</code>
            ——面板不替它补记录。
          </p>
        )}

        {flow.governance.length > 0 && (
          <>
            <div className="flow-plan-track is-fixed">
              <span>②</span>
              <b>治理固定</b>
              <em>不随方法变：闭包与经验回流对所有方法一致</em>
            </div>
            <ol className="flow-stages">{flow.governance.map((step) => renderStep(step, "governance"))}</ol>
          </>
        )}

        {flow.extras.length > 0 && (
          <div className="flow-plan-extra">
            <button
              type="button"
              className="flow-plan-extra-head"
              aria-expanded={showExtras}
              onClick={() => setExtrasOpen((value) => !value)}
            >
              <span>{showExtras ? "▾" : "▸"}</span>
              会话还走了 {flow.extras.length} 个计划外阶段
              <em>执行器当前全阶段执行</em>
            </button>
            {showExtras && (
              <ul className="flow-plan-extra-list">
                {flow.extras.map((extra) => (
                  <li key={extra.id}>
                    <button
                      type="button"
                      className={`flow-plan-extra-row${
                        currentExtra && normalizeStageId(currentExtra.id) === normalizeStageId(extra.id)
                          ? " is-current"
                          : ""
                      }`}
                      onClick={() => onFocusStage(extra.id)}
                      title={
                        extra.reason === "unmapped"
                          ? `${extra.id} 不在方法注册表的阶段目录里：无法判断它属于哪种方法编排`
                          : `本方法的 fit_stages 不含 ${extra.id}：计划里没有它的任务卡。计划外 ≠ 无效，但不算本方法声明的编排。`
                      }
                      disabled={extra.messageCount === 0}
                    >
                      <code>{extra.id}</code>
                      <span>{extra.label}</span>
                      <i>{extra.reason === "unmapped" ? "注册表未映射" : "本方法未声明"}</i>
                      <b>{extra.messageCount} 条</b>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="flow-plan-note">
              计划外 ≠ 无效：这些阶段真实发生过，但不属于本方法声明的编排。要不要按方法跳过它们，是执行层
              尚未完成的改造（design/165）。
            </p>
          </div>
        )}
      </section>
    </div>
  );
}
