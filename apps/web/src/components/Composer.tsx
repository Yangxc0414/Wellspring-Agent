import { Fragment, useEffect, useRef, useState } from "react";
import { useShallow } from "zustand/react/shallow";
import { MODE_META, modelSettingsForProfile } from "../domain/catalog";
import { COMMAND_GROUP_LABELS, matchSlashCommands, type SlashCommand } from "../domain/commandCatalog";
import type { ResearchTask, Skill } from "../domain/types";
import {
  selectCurrentTask,
  selectPendingGuidance,
  useWorkspaceStore
} from "../state/workspaceStore";
import { AccessPicker } from "./AccessPicker";
import { Icon, type IconName } from "./Icon";
import { ModePicker } from "./ModePicker";
import { ModelPicker } from "./ModelPicker";

const COMMAND_GROUP_ICON: Record<SlashCommand["group"], IconName> = {
  run: "play",
  work: "branch",
  view: "evidence",
  tools: "sliders"
};

type SlashItem =
  | { kind: "command"; command: SlashCommand }
  | { kind: "skill"; skill: Skill };

function suggestionsFor(task: ResearchTask): string[] {
  if (task.auto.running) {
    if (task.auto.paused && task.auto.gate === "claim") return ["签署 claim", "停止", "查看证据链"];
    if (task.auto.paused) return ["继续", "单步", "停止"];
    return ["暂停", "单步", "停止"];
  }
  if (task.mode === "auto") {
    if (task.evaluation.hiddenAccessCount > 0) return ["查看评估隔离", "查看证据链"];
    return ["启动全自动", "单步", "查看证据链"];
  }
  if (task.mode === "writing") {
    const signed = task.evidence.some((item) => item.kind === "claim" && item.status === "signed");
    return signed
      ? ["运行审阅包", "生成写作槽位", "查看证据链"]
      : ["运行审阅包", "去补证据", "查看证据链"];
  }
  if (task.mode === "experiment") {
    const signed = task.evidence.some((item) => item.kind === "claim" && item.status === "signed");
    if (task.evaluation.hiddenAccessCount > 0) return ["运行审阅包", "查看评估隔离", "查看证据链"];
    if (task.run && signed) return ["运行审阅包", "生成写作槽位", "查看证据链"];
    if (task.run) return ["运行审阅包", "签署 claim · 人工门", "查看证据链"];
    if (task.protocolFrozen) return ["运行 3 seeds", "查看 EA", "查看证据链"];
    if (task.protocol) return ["G2 冻结命令", "查看证据链"];
    return ["送入实验设计", "查看证据链"];
  }
  if (task.coverage.spans > 0) return ["运行真实 pipeline", "运行审阅包", "查看证据链"];
  return ["运行真实 pipeline", "开始检索", "查看证据链"];
}

export function Composer() {
  const [value, setValue] = useState("");
  const [slashIndex, setSlashIndex] = useState(0);
  const [slashDismissed, setSlashDismissed] = useState(false);
  const task = useWorkspaceStore(selectCurrentTask);
  const focusTick = useWorkspaceStore((state) => state.ui.focusComposerTick);
  const pendingGuidance = useWorkspaceStore(useShallow(selectPendingGuidance));
  const skills = useWorkspaceStore((state) => state.skills);
  const actions = useWorkspaceStore((state) => state.actions);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (focusTick > 0) inputRef.current?.focus();
  }, [focusTick]);

  if (!task) return null;
  const displayMode = task.auto.running ? "auto" : task.mode;
  const meta = MODE_META[displayMode];
  const suggestions = suggestionsFor(task);
  const availableSkills = skills.filter((skill) => skill.activation !== "off");
  const slashQuery = value.startsWith("/") && !/\s/.test(value) ? value.slice(1).toLowerCase() : null;
  const commandMatches = slashQuery !== null ? matchSlashCommands(slashQuery, 6, task) : [];
  const skillMatches = slashQuery !== null
    ? availableSkills
        .filter((skill) =>
          `${skill.id} ${skill.name} ${skill.description}`.toLowerCase().includes(slashQuery)
        )
        .slice(0, 4)
    : [];
  const slashItems: SlashItem[] = [
    ...commandMatches.map((command): SlashItem => ({ kind: "command", command })),
    ...skillMatches.map((skill): SlashItem => ({ kind: "skill", skill }))
  ];
  const commandOrder = new Map(commandMatches.map((command, index) => [command.id, index]));
  const commandSections = (["run", "work", "view", "tools"] as const)
    .map((group) => ({
      group,
      commands: commandMatches.filter((command) => command.group === group)
    }))
    .filter((section) => section.commands.length > 0);
  const showSlash = Boolean(slashQuery !== null && !slashDismissed && slashItems.length);

  const insertSkill = (skill: Skill) => {
    setValue(`/${skill.id} `);
    setSlashDismissed(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const runCommand = (command: SlashCommand) => {
    setValue("");
    setSlashDismissed(true);
    actions.sendMessage(`/${command.id}`);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const chooseSlashItem = (item: SlashItem) => {
    if (item.kind === "command") runCommand(item.command);
    else insertSkill(item.skill);
  };

  const submit = () => {
    const text = value.trim();
    if (!text) return;
    actions.sendMessage(text);
    setValue("");
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const handleSuggestion = (suggestion: string) => {
    switch (suggestion) {
      case "运行真实 pipeline":
        void actions.startLiveRun();
        break;
      case "开始检索":
      case "扩展检索":
        actions.runResearch();
        break;
      case "运行审阅包":
        void actions.runReviewPack();
        break;
      case "把 gap 变成假设":
      case "送入实验设计":
        actions.designExperiment();
        break;
      case "查看证据链":
      case "查看 EA":
        actions.setContextTab("evidence");
        break;
      case "查看评估隔离":
        actions.setContextTab("eval");
        break;
      case "G2 冻结命令":
        actions.freezeProtocol();
        break;
      case "运行 3 seeds":
        actions.runExperiment();
        break;
      case "启动全自动":
        actions.startAuto();
        break;
      case "签署 claim":
      case "签署 claim · 人工门":
      case "claim 人签命令":
        actions.signClaim();
        break;
      case "生成写作槽位":
        actions.prepareWriting();
        break;
      case "检查证据边界":
        actions.setContextTab("evidence");
        break;
      case "去补证据":
        actions.setMode("research");
        break;
      case "继续":
        actions.resumeAuto();
        break;
      case "停止":
        actions.stopAuto();
        break;
      case "单步":
        actions.stepAuto();
        break;
      case "暂停":
        actions.pauseAuto();
        break;
      default:
        actions.sendMessage(suggestion);
    }
  };

  return (
    <div className="composer">
      <div className="composer-top">
        <div className="composer-meta">
          {task.auto.running && (
            <span className={`guidance-live${task.auto.paused ? " is-paused" : ""}`}>
              <span />
              {task.auto.paused ? "已暂停 · 输入指导会排队" : "运行中 · 输入指导"}
            </span>
          )}
        </div>
        <div className="suggestions" aria-label="快捷动作">
          {suggestions.map((suggestion) => (
            <button type="button" key={suggestion} onClick={() => handleSuggestion(suggestion)}>
              {suggestion}
            </button>
          ))}
        </div>
      </div>

      {pendingGuidance.length > 0 && (
        <button
          type="button"
          className="guidance-queue"
          onClick={() => actions.setContextTab("run")}
          title="查看运行上下文中的指导队列"
        >
          <Icon name="branch" size={12} />
          <span>{pendingGuidance.length} 条指导等待下一个检查点</span>
          <em>{pendingGuidance[pendingGuidance.length - 1]?.text}</em>
        </button>
      )}

      <div className="composer-input-area">
        {showSlash && (
          <div className="slash-menu" role="listbox" aria-label="命令与 Skill">
            <div className="slash-head">
              <span>COMMANDS + SKILLS</span>
              <em>↑↓ 选择 · Enter 执行/插入 · Esc 关闭</em>
            </div>
            {commandSections.map((section) => (
              <Fragment key={section.group}>
                <div className="slash-group-label">{COMMAND_GROUP_LABELS[section.group]}</div>
                {section.commands.map((command) => {
                  const itemIndex = commandOrder.get(command.id) ?? 0;
                  return (
                    <button
                      key={`command-${command.id}`}
                      type="button"
                      role="option"
                      aria-selected={itemIndex === slashIndex}
                      className={itemIndex === slashIndex ? "is-on" : ""}
                      onMouseEnter={() => setSlashIndex(itemIndex)}
                      onClick={() => chooseSlashItem({ kind: "command", command })}
                    >
                      <span className="slash-icon"><Icon name={COMMAND_GROUP_ICON[command.group]} size={12} /></span>
                      <span className="slash-copy">
                        <b>/{command.id}</b>
                        <small>{command.name}</small>
                      </span>
                      <em>{command.description}</em>
                    </button>
                  );
                })}
              </Fragment>
            ))}
            {skillMatches.length > 0 && (
              <>
                <div className="slash-group-label">SKILLS</div>
                {skillMatches.map((skill, index) => {
                  const itemIndex = commandMatches.length + index;
                  return (
                    <button
                      key={`skill-${skill.id}`}
                      type="button"
                      role="option"
                      aria-selected={itemIndex === slashIndex}
                      className={itemIndex === slashIndex ? "is-on" : ""}
                      onMouseEnter={() => setSlashIndex(itemIndex)}
                      onClick={() => chooseSlashItem({ kind: "skill", skill })}
                    >
                      <span className="slash-icon"><Icon name="spark" size={12} /></span>
                      <span className="slash-copy">
                        <b>/{skill.id}</b>
                        <small>{skill.name}</small>
                      </span>
                      <em>{skill.description}</em>
                    </button>
                  );
                })}
              </>
            )}
            <div className="slash-foot">命令直接执行；Skill 会插入 ID，可补一句检查重点，再由 store 生成只读结果。</div>
          </div>
        )}
        <div className="input-wrap">
          <textarea
            ref={inputRef}
            rows={2}
            value={value}
            maxLength={4000}
            placeholder={meta.placeholder}
            aria-label="给 Research Agent 发消息"
            onChange={(event) => {
              setValue(event.target.value);
              setSlashIndex(0);
              setSlashDismissed(false);
            }}
            onKeyDown={(event) => {
              // IME composition (e.g. Chinese input confirming candidates) sends Enter
              // keydowns too; without this guard an open slash menu hijacks them.
              if (event.nativeEvent.isComposing) return;
              if (showSlash) {
                if (event.key === "ArrowDown") {
                  event.preventDefault();
                  setSlashIndex((current) => Math.min(current + 1, slashItems.length - 1));
                  return;
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault();
                  setSlashIndex((current) => Math.max(current - 1, 0));
                  return;
                }
                if (event.key === "Enter" || event.key === "Tab") {
                  event.preventDefault();
                  const item = slashItems[slashIndex];
                  if (item) chooseSlashItem(item);
                  return;
                }
                if (event.key === "Escape") {
                  event.preventDefault();
                  setSlashDismissed(true);
                  return;
                }
              }
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
          />
          <button type="button" className="send-button" onClick={submit} disabled={!value.trim()} aria-label="发送">
            发送
            <Icon name="send" size={13} />
          </button>
        </div>
      </div>

      <div className="composer-foot">
        <div className="composer-foot-left">
          <ModePicker />
          <AccessPicker
            value={task.access}
            onChange={actions.setAccess}
            disabled={task.auto.running}
          />
          <button
            type="button"
            className="composer-skill"
            onClick={() => actions.openOverlay("skillsOpen")}
            title="Skills：目录常驻；会话中按需加载"
            aria-label="打开 Skills"
          >
            <Icon name="spark" size={12} />
            <span>Skills</span>
            <b>{availableSkills.length}</b>
          </button>
        </div>
        <div className="composer-foot-right">
          <ModelPicker
            value={task.model.profileId}
            settings={task.model}
            onChange={(profileId) => actions.saveModel(modelSettingsForProfile(profileId))}
            onThinkingChange={(stop) =>
              actions.saveModel({ ...task.model, thinkingStop: stop }, { silent: true })
            }
            onAdvanced={() => actions.openOverlay("modelOpen")}
          />
        </div>
      </div>
    </div>
  );
}
