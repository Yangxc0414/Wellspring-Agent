import { memo, useEffect, useRef } from "react";
import { ACCESS_META, MODE_META, modelProfile, thinkingLabel } from "../domain/catalog";
import type { Card, Message } from "../domain/types";
import { runtimeRunState } from "../domain/runtimeSnapshot";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { ArtifactCard } from "./ArtifactCard";
import { Composer } from "./Composer";
import { Icon } from "./Icon";
import { RichText } from "./RichText";

function TaskHeader() {
  const task = useWorkspaceStore(selectCurrentTask);
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const actions = useWorkspaceStore((state) => state.actions);
  if (!task) return null;
  const workspace = workspaces.find((item) => item.id === task.workspaceId);
  const meta = MODE_META[task.mode];
  const profile = modelProfile(task.model);
  const access = ACCESS_META[task.access];
  const pendingTool = task.toolCalls.filter((call) => call.status === "proposed").length;
  const runtimeCard = [...task.messages]
    .reverse()
    .find((entry) => entry.card?.type === "runtime-run")?.card as Extract<Card, { type: "runtime-run" }> | undefined;
  const runtimeLabel = runtimeCard ? runtimeRunState(runtimeCard) : "";
  const completedCount = runtimeCard
    ? Math.max(
        task.completedStages.length,
        new Set(
          (runtimeCard.eventLog ?? [])
            .filter((event) => event.type === "step_end" && event.stage)
            .map((event) => event.stage)
        ).size
      )
    : task.completedStages.length;
  const statusLabel = runtimeCard
    ? runtimeLabel
    : task.auto.running
      ? task.auto.paused
        ? "PAUSED"
        : "RUNNING"
      : task.status === "blocked"
        ? "HUMAN GATE"
        : "READY";
  const taskChip: { label: string; tone: string } = runtimeCard
    ? {
        label: runtimeLabel.toLowerCase(),
        tone: runtimeLabel === "RUNNING" || runtimeLabel === "QUEUED"
          ? "teal"
          : runtimeLabel === "FAILED" || runtimeLabel === "NEEDS HUMAN"
            ? "red"
            : ""
      }
    : task.auto.running
      ? task.auto.paused
        ? { label: task.auto.gate === "claim" ? "gate pending" : "paused", tone: task.auto.gate === "claim" ? "red" : "amber" }
        : { label: "running", tone: "teal" }
      : task.status === "blocked"
        ? { label: "gate pending", tone: "red" }
        : { label: "active", tone: "" };

  return (
    <header className="task-head">
      <div className="task-head-main">
        <div className="task-kicker">
          <span>{workspace?.name ?? "WORKSPACE"}</span>
          <i>/</i>
          <span>{meta.kicker}</span>
          <span className={`run-led ${task.auto.running && !task.auto.paused ? "is-live" : ""}`} />
          <span>{statusLabel}</span>
        </div>
        <div className="task-title-line">
          <span className="task-tag">TASK</span>
          <h1>{task.name}</h1>
        </div>
        <p className="task-goal">{task.goal}</p>
      </div>

      <div className="task-head-side">
        <div className="task-chips">
          <span className="chip blue">{meta.label}</span>
          <span className="chip">{completedCount}/9 stages</span>
          <span className={`chip${taskChip.tone ? ` ${taskChip.tone}` : ""}`}>
            {taskChip.label}
          </span>
          <span className={`chip access-chip is-${access.tone}`} title={`${access.label} · ${access.hint}`}>
            {access.short}
          </span>
          <span className="chip">
            {runtimeCard
              ? `runtime · ${runtimeCard.route ?? runtimeCard.taskType ?? "auto"}`
              : `${profile.short} · ${thinkingLabel(task.model)}`}
          </span>
        </div>
        <div className="task-brief">
          <span className="brief-label">EVIDENCE</span>
          <span>
            <b>{task.coverage.spans}</b> spans · <b>{task.coverage.gaps}</b> gaps
          </span>
          <button type="button" onClick={() => actions.setContextTab("evidence")}>
            查看
            <Icon name="arrow" size={12} />
          </button>
        </div>
        {pendingTool > 0 && (
          <button
            type="button"
            className="task-alert"
            onClick={() => actions.openOverlay("pluginsOpen")}
          >
            <Icon name="terminal" size={12} />
            {pendingTool} 个工具调用待批准
          </button>
        )}
      </div>
    </header>
  );
}

// Message content is immutable once appended; memo keeps the runtime poll (which
// rewrites only the last message's card) from re-rendering the whole transcript.
const MessageView = memo(function MessageView({ item }: { item: Message }) {
  if (item.role === "system") {
    return (
      <div className="system-line">
        <span className="system-dot" />
        <span>{item.text}</span>
      </div>
    );
  }

  const isUser = item.role === "user";
  return (
    <div className={`message${isUser ? " is-user" : ""}`}>
      <div className="avatar" aria-hidden="true">
        {isUser ? "YOU" : <Icon name="logo" size={14} />}
      </div>
      <div className="message-body">
        <div className="message-head">
          <b>{isUser ? "你" : "Research Agent"}</b>
          <span>{item.at}</span>
        </div>
        <div className={`bubble${isUser ? " is-user-bubble" : " is-agent-bubble"}`}>
          {isUser ? <p>{item.text}</p> : <RichText text={item.text} />}
        </div>
        {item.card && <ArtifactCard card={item.card} />}
      </div>
    </div>
  );
});

function RunIndicator() {
  const task = useWorkspaceStore(selectCurrentTask);
  if (!task?.auto.running) return null;
  const stage = task.autoStages[task.auto.index];
  const paused = task.auto.paused;
  return (
    <div className={`run-indicator${paused ? " is-paused" : ""}`}>
      <span className="indicator-dots" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span>
        {paused
          ? task.auto.gate === "claim"
            ? "停在 claim 人工门 · 需要作者签署"
            : "运行已暂停 · 点击继续或单步"
          : `正在执行 ${stage?.id ?? "META"} ${stage?.label ?? ""}`}
      </span>
      <em>{task.auto.cycle ? `CYCLE ${task.auto.cycle}` : "演示数据"}</em>
    </div>
  );
}

export function Conversation() {
  const task = useWorkspaceStore(selectCurrentTask);
  const autoScroll = useWorkspaceStore((state) => state.preferences.autoScroll);
  const reduceMotion = useWorkspaceStore((state) => state.preferences.reduceMotion);
  const threadRef = useRef<HTMLDivElement>(null);
  const messageCount = task?.messages.length ?? 0;
  const autoIndex = task?.auto.index ?? 0;

  useEffect(() => {
    if (!autoScroll || !threadRef.current) return;
    threadRef.current.scrollTo({
      top: threadRef.current.scrollHeight,
      behavior: reduceMotion ? "auto" : "smooth"
    });
  }, [messageCount, autoIndex, autoScroll, reduceMotion]);

  return (
    <main className="conversation">
      <TaskHeader />
      <div className="thread" id="thread" ref={threadRef} role="log" aria-live="polite" aria-label="Agent 会话">
        <div className="thread-inner">
          {task?.messages.map((item) => (
            <MessageView key={item.id} item={item} />
          ))}
          <RunIndicator />
        </div>
      </div>
      <Composer />
    </main>
  );
}
