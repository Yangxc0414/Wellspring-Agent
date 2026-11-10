import { useEffect, useRef, useState } from "react";
import { clampModel, modelSettingsForProfile } from "../domain/catalog";
import { currentGreeting } from "../domain/greeting";
import type { ContextAttachment } from "../domain/types";
import { formatBytes } from "../domain/utils";
import { useWorkspaceStore } from "../state/workspaceStore";
import { AccessPicker } from "./AccessPicker";
import { ContextPlus } from "./ContextPlus";
import type { IconName } from "./Icon";
import { Icon } from "./Icon";
import { ModelPicker } from "./ModelPicker";
import { WorkspacePicker } from "./WorkspacePicker";

const PROMPTS: Array<{ icon: IconName; title: string; hint: string; text: string }> = [
  {
    icon: "search",
    title: "文献调研",
    hint: "来源 → span → gap",
    text: "帮我做一轮文献调研，先盘点来源、可定位 span 与证据缺口："
  },
  {
    icon: "shield",
    title: "实验设计",
    hint: "baseline / 指标 / seeds",
    text: "把一个研究问题转成可复现实验，先给出 baseline、主指标、对照与 seeds："
  },
  {
    icon: "book",
    title: "写作槽位",
    hint: "先槽位，后正文",
    text: "帮我规划论文写作：哪些 claim 可以写、哪些槽位必须先锁住？主题是："
  },
  {
    icon: "evolution",
    title: "自进化检查",
    hint: "候选 / 租约 / 不可写面",
    text: "检查当前自进化候选是否只改策略层，并给出准入前检查清单。"
  },
  {
    icon: "spark",
    title: "创建技能",
    hint: "对话生成 SKILL 草稿",
    text: "帮我创建一个技能，名称：引用完整性检查，描述：检查 claim 引用是否都能回到可定位 span，指令：逐条核对 refs、source 与 claim scope，工具：evidence.inspect。"
  }
];

export function WelcomeHome() {
  const activeWorkspaceId = useWorkspaceStore((state) => state.activeWorkspaceId);
  const workspaces = useWorkspaceStore((state) => state.workspaces);
  const draftAccess = useWorkspaceStore((state) => state.ui.draftAccess);
  const draftProfileId = useWorkspaceStore((state) => state.ui.draftProfileId);
  const [draftThinkingStop, setDraftThinkingStop] = useState<string | number | null>(
    () => modelSettingsForProfile(draftProfileId).thinkingStop
  );
  const [attachments, setAttachments] = useState<ContextAttachment[]>([]);
  const [greeting, setGreeting] = useState(() => currentGreeting());
  const draftModel = clampModel({
    ...modelSettingsForProfile(draftProfileId),
    thinkingStop: draftThinkingStop
  });
  const focusTick = useWorkspaceStore((state) => state.ui.focusComposerTick);
  const skills = useWorkspaceStore((state) => state.skills);
  const actions = useWorkspaceStore((state) => state.actions);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const availableSkills = skills.filter((skill) => skill.activation !== "off").length;
  const activeWorkspace = workspaces.find((workspace) => workspace.id === activeWorkspaceId);

  useEffect(() => {
    if (focusTick > 0) inputRef.current?.focus();
  }, [focusTick]);

  useEffect(() => {
    const timer = window.setInterval(() => setGreeting(currentGreeting()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const submit = () => {
    const text = value.trim();
    if (!text) return;
    actions.startSession({
      text,
      workspaceId: activeWorkspaceId,
      access: draftAccess,
      thinkingStop: draftThinkingStop,
      attachments
    });
    setValue("");
    setAttachments([]);
  };

  const addAttachments = (items: ContextAttachment[]) => {
    setAttachments((current) => {
      const seen = new Set(current.map((item) => `${item.kind}:${item.name}:${item.bytes}`));
      const fresh = items.filter((item) => !seen.has(`${item.kind}:${item.name}:${item.bytes}`));
      return [...current, ...fresh].slice(0, 12);
    });
  };

  const removeAttachment = (id: string) => {
    setAttachments((current) => current.filter((item) => item.id !== id));
  };

  const fillPrompt = (text: string) => {
    setValue(text);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  return (
    <main className="welcome">
      <div className="welcome-watermark" aria-hidden="true">
        <span>WELLSRING</span>
        <em>AGENT</em>
      </div>
      <div className="welcome-inner">
        <div className="welcome-art" aria-hidden="true">
          <svg className="welcome-art-lines" viewBox="0 0 460 230" fill="none">
            <path d="M38 190 154 40 386 40 270 190Z" stroke="currentColor" strokeWidth="1" />
            <path d="M82 190 198 40 426 40 310 190Z" stroke="currentColor" strokeWidth="0.8" opacity="0.65" />
            <path d="M154 40 270 190M198 40 310 190" stroke="currentColor" strokeWidth="0.7" opacity="0.4" />
            <circle cx="282" cy="36" r="3" fill="currentColor" opacity="0.55" />
          </svg>
          <span className="welcome-art-monogram">WA</span>
          <span className="welcome-art-word">WELLSRING</span>
          <span className="welcome-art-sub">AGENT · RESEARCH WORKSPACE</span>
        </div>

        <div className="welcome-head">
          <h1>{greeting}</h1>
          <p>从文献、实验到写作，在同一个证据边界里推进。全自动也会停在 claim 人工门，不会替作者签署结论。</p>
        </div>

        <div className="welcome-composer">
          <div className="welcome-context-row">
            <WorkspacePicker value={activeWorkspaceId} onChange={actions.activateWorkspace} placement="down" />
            <ContextPlus
              workspaceFolder={activeWorkspace?.folder}
              onAdd={addAttachments}
              onMore={() => actions.openOverlay("newTaskOpen")}
            />
          </div>

          {attachments.length > 0 && (
            <div className="welcome-attachments" aria-label="已附加上下文">
              {attachments.map((attachment) => (
                <span className="welcome-attachment" key={attachment.id}>
                  <Icon name={attachment.kind === "folder" ? "folder" : "tasks"} size={11} />
                  <span className="welcome-attachment-copy">
                    <b>{attachment.name}</b>
                    <small>
                      {attachment.files > 1 ? `${attachment.files} files · ` : ""}
                      {formatBytes(attachment.bytes)}
                      {attachment.source === "workspace" ? " · 工作区" : ""}
                    </small>
                  </span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(attachment.id)}
                    aria-label={`移除 ${attachment.name}`}
                    title="移除"
                  >
                    <Icon name="close" size={9} />
                  </button>
                </span>
              ))}
            </div>
          )}

          <textarea
            ref={inputRef}
            rows={3}
            value={value}
            maxLength={4000}
            placeholder="向 Research Agent 提问，使用 / 调用 Skill……"
            aria-label="新会话输入"
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submit();
              }
            }}
          />

          <div className="welcome-toolbar">
            <div className="welcome-tools-left">
              <AccessPicker
                value={draftAccess}
                onChange={(mode) => actions.setUI({ draftAccess: mode })}
                placement="down"
              />
              <button
                type="button"
                className="welcome-skill-btn"
                onClick={() => actions.openOverlay("skillsOpen")}
                title="Skills：目录常驻；会话中按需加载"
              >
                <Icon name="spark" size={12} />
                <span>Skills</span>
                <b>{availableSkills}</b>
              </button>
            </div>
            <div className="welcome-tools-right">
              <ModelPicker
                value={draftProfileId}
                settings={draftModel}
                onChange={(profileId) => {
                  const next = modelSettingsForProfile(profileId);
                  actions.setUI({ draftProfileId: profileId });
                  setDraftThinkingStop(next.thinkingStop);
                }}
                onThinkingChange={setDraftThinkingStop}
              />
              <button
                type="button"
                className="welcome-send"
                onClick={submit}
                disabled={!value.trim()}
                aria-label="开始新会话"
                title="开始新会话"
              >
                <Icon name="arrow" size={15} />
              </button>
            </div>
          </div>
        </div>

        <div className="welcome-prompts" aria-label="起始建议">
          {PROMPTS.map((prompt) => (
            <button
              type="button"
              key={prompt.title}
              onClick={() => fillPrompt(prompt.text)}
              title={prompt.hint}
            >
              <Icon name={prompt.icon} size={13} />
              <span>{prompt.title}</span>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
