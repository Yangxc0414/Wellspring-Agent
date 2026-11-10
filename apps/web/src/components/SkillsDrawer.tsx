import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { importRuntimeSkills, loadRuntimeSkills, loadSkillUsage, loadSkillVersions } from "../adapters/runtimeApi";
import { parseSkillFiles, scanSkillDirectory } from "../domain/skillImport";
import { skillActivationLabel } from "../domain/skillRouting";
import type { Skill } from "../domain/types";
import { useWorkspaceStore } from "../state/workspaceStore";
import { Icon } from "./Icon";

interface SkillForm {
  name: string;
  description: string;
  instructions: string;
  tools: string;
}

const EMPTY_FORM: SkillForm = { name: "", description: "", instructions: "", tools: "" };

export function SkillsDrawer() {
  const skills = useWorkspaceStore((state) => state.skills);
  const welcomeOpen = useWorkspaceStore((state) => state.ui.welcomeOpen);
  const skillDraft = useWorkspaceStore((state) => state.ui.skillDraft);
  const task = useWorkspaceStore((state) => {
    const current = state.tasks.find((item) => item.id === state.selectedTaskId) ?? state.tasks[0];
    return current;
  });
  const actions = useWorkspaceStore((state) => state.actions);
  const [query, setQuery] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<SkillForm>(EMPTY_FORM);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importMessage, setImportMessage] = useState("");
  const [runtimeCatalog, setRuntimeCatalog] = useState<{ count: number; enabled: number } | null>(null);
  const [runtimeCatalogError, setRuntimeCatalogError] = useState("");
  const [usage, setUsage] = useState<{ total: number; failed: number } | null>(null);
  const [versions, setVersions] = useState<Record<string, string> | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadRuntimeSkills()
      .then((snapshot) => {
        setRuntimeCatalog({
          count: snapshot.count,
          enabled: snapshot.skills.filter((skill) => skill.enabled).length
        });
        setRuntimeCatalogError("");
      })
      .catch(() => {
        setRuntimeCatalog(null);
        setRuntimeCatalogError("runtime 未连接；仅显示浏览器本地目录");
      });
    loadSkillUsage()
      .then((snapshot) => {
        const failed = Object.values(snapshot.skills).reduce(
          (sum, item) => sum + item.fail + item.blocked,
          0
        );
        setUsage({ total: snapshot.count, failed });
      })
      .catch(() => setUsage(null));
    loadSkillVersions()
      .then((snapshot) => setVersions(snapshot.active))
      .catch(() => setVersions(null));
  }, []);

  useEffect(() => {
    if (!skillDraft) return;
    setForm({
      name: skillDraft.name,
      description: skillDraft.description,
      instructions: skillDraft.instructions,
      tools: skillDraft.tools.join(", ")
    });
    setCreating(true);
  }, [skillDraft]);

  const close = () => actions.setUI({ skillsOpen: false });
  const autoBusy = Boolean(task?.auto.running);
  const canInvoke = welcomeOpen || (Boolean(task) && !autoBusy);
  const blockedByAuto = !welcomeOpen && autoBusy;
  const filtered = skills.filter((skill) =>
    `${skill.id} ${skill.name} ${skill.description} ${skill.tools.join(" ")}`
      .toLowerCase()
      .includes(query.trim().toLowerCase())
  );
  const autoCount = skills.filter((skill) => skill.activation === "auto").length;
  const manualCount = skills.filter((skill) => skill.activation === "manual").length;
  const offCount = skills.filter((skill) => skill.activation === "off").length;

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const name = form.name.trim();
    if (!name) {
      actions.notify("请输入 Skill 名称");
      return;
    }
    if (skills.some((skill) => skill.name === name)) {
      actions.notify("已有同名 Skill；换一个名称");
      return;
    }
    const created = actions.createSkill({
      name,
      description: form.description,
      instructions: form.instructions,
      tools: form.tools.split(",").map((tool) => tool.trim()).filter(Boolean)
    });
    if (created) void syncRuntime([created], "保存");
    actions.setUI({ skillDraft: null });
    setForm(EMPTY_FORM);
    setCreating(false);
  };

  const syncRuntime = async (items: Skill[], context: string) => {
    const syncable = items.filter((skill) => skill.source !== "builtin").slice(0, 50);
    if (!syncable.length) return;
    try {
      const result = await importRuntimeSkills(
        syncable.map((skill) => ({
          name: skill.name,
          description: skill.description,
          instructions: skill.instructions,
          tools: skill.tools,
          version: skill.version,
          license: skill.license ?? "",
          origin: skill.origin ?? "",
          source: skill.source === "imported" ? "imported" : "custom"
        }))
      );
      setImportMessage(
        (current) =>
          `${current ? `${current} · ` : ""}${context}：runtime 技能目录接收 ${result.accepted} 个（默认停用，不执行 scripts）`
      );
    } catch {
      setImportMessage(
        (current) => `${current ? `${current} · ` : ""}${context}：runtime 未连接，已保存在浏览器本地`
      );
    }
  };

  const cancelDraft = () => {
    actions.setUI({ skillDraft: null });
    setForm(EMPTY_FORM);
    setCreating(false);
  };

  const applyImport = (result: Awaited<ReturnType<typeof parseSkillFiles>>) => {
    if (result.skills.length) actions.importSkills(result.skills);
    const skipped = result.skipped.length + result.errors.length;
    setImportMessage(
      `导入 ${result.skills.length} 个 Skill${skipped ? `，跳过/错误 ${skipped} 个` : ""}。` +
        (result.skipped[0] ? ` 首个跳过：${result.skipped[0].name} · ${result.skipped[0].reason}` : "")
    );
    if (result.skills.length) void syncRuntime(result.skills, "导入");
  };

  const importFolder = async () => {
    if (!window.showDirectoryPicker) {
      folderInputRef.current?.click();
      return;
    }
    setImporting(true);
    setImportMessage("");
    try {
      const handle = await window.showDirectoryPicker({
        id: "research-agent-skills",
        mode: "read",
        startIn: "documents"
      });
      applyImport(await scanSkillDirectory(handle));
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        setImportMessage(caught instanceof Error ? caught.message : "技能文件夹导入失败");
      }
    } finally {
      setImporting(false);
    }
  };

  const onFolderInput = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setImporting(true);
    setImportMessage("");
    try {
      applyImport(await parseSkillFiles(files));
    } catch (caught) {
      setImportMessage(caught instanceof Error ? caught.message : "技能文件导入失败");
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  };

  const onFileInput = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setImporting(true);
    setImportMessage("");
    try {
      applyImport(await parseSkillFiles(files));
    } catch (caught) {
      setImportMessage(caught instanceof Error ? caught.message : "技能文件导入失败");
    } finally {
      setImporting(false);
      event.target.value = "";
    }
  };

  return (
    <div className="drawer-layer" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) close();
    }}>
      <aside className="plugin-drawer skills-drawer" role="dialog" aria-modal="true" aria-label="Skills 技能面板">
        <header className="drawer-head">
          <div>
            <span className="eyebrow">SKILLS / LOCAL</span>
            <h2>技能与调用</h2>
          </div>
          <button type="button" className="icon-button" onClick={close} aria-label="关闭 Skills 面板">
            <Icon name="close" size={14} />
          </button>
        </header>

        <div className="drawer-body">
          <p className="drawer-note">
            Skill 是只读的检查与编排单元：可以读取当前任务状态、生成计划与边界检查，但不会调用外部工具、写 claim 或绕过人工门。
            调用方式：在输入框输入 <code>/{`<skill-id>`}</code>，或点击下方“调用”。也可以在对话里说“帮我创建一个技能……”或输入 <code>/skill-creator</code>，先生成草稿再确认保存。
          </p>

          <div className="skill-toolbar">
            <label className="skill-search">
              <Icon name="search" size={12} />
              <input
                type="search"
                value={query}
                placeholder="搜索 skill / 工具…"
                onChange={(event) => setQuery(event.target.value)}
                aria-label="搜索 Skill"
              />
            </label>
            <button
              type="button"
              className="mini-button"
              onClick={() => setCreating((value) => !value)}
            >
              <Icon name={creating ? "close" : "plus"} size={11} />
              {creating ? "收起" : "新建 Skill"}
            </button>
          </div>

          <div className="skill-meta-row">
            <span>按需 {autoCount} · 手动 {manualCount} · 停用 {offCount}</span>
            {blockedByAuto ? (
              <em>全自动运行中不可调用</em>
            ) : welcomeOpen ? (
              <em>将从当前工作区新建会话</em>
            ) : null}
          </div>
          <p className="skill-routing-note">
            Skill 不预加载。会话中只按当前问题或阶段加载 0–1 个内置 Skill；导入与自定义项仅可手动调用。
          </p>

          <div className="skill-import-row">
            <button type="button" className="mini-button" onClick={() => void importFolder()} disabled={importing}>
              <Icon name="folder" size={11} />
              {importing ? "导入中…" : "导入技能文件夹"}
            </button>
            <button type="button" className="mini-button" onClick={() => fileInputRef.current?.click()} disabled={importing}>
              导入 .md
            </button>
            <span>支持 SKILL.md / .claude/skills / .agents/skills</span>
          </div>
          {importMessage && <p className="skill-import-message">{importMessage}</p>}
          <p className="skill-import-note">
            导入项来自本地文件，默认停用；只登记 name / description / instructions 与工具声明，不执行 scripts，也不进入 Claim/EA。runtime 在线时会同步技能目录，但仍不授予执行权限。
          </p>
          <p className="skill-import-note">
            Runtime 目录：{runtimeCatalog ? `${runtimeCatalog.count} 个 · ${runtimeCatalog.enabled} 个已启用` : runtimeCatalogError || "读取中…"}。
            本地浏览器目录：{skills.length} 个。两套目录不会互相授予执行权限。
            {usage ? ` 使用证据：${usage.total} 条 · 失败/阻断 ${usage.failed} 条（仅记录，不自动改 Skill）。` : ""}
            {versions
              ? ` 内置版本：${Object.entries(versions).map(([id, version]) => `${id}@${version}`).join(" · ")}（激活/回滚只走 CLI 人签）。`
              : ""}
          </p>

          {creating && (
            <form className="skill-form" onSubmit={submit}>
              <div className="skill-form-head">
                <span>NEW SKILL</span>
                <em>{skillDraft ? "来自对话草稿 · 确认后保存" : "只读 · 会话内"}</em>
              </div>
              <label>
                <span>名称</span>
                <input
                  autoFocus
                  value={form.name}
                  maxLength={40}
                  placeholder="例如：引用完整性检查"
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
              </label>
              <label>
                <span>说明</span>
                <input
                  value={form.description}
                  maxLength={120}
                  placeholder="这个 skill 负责检查什么？"
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </label>
              <label>
                <span>指令</span>
                <textarea
                  rows={3}
                  value={form.instructions}
                  maxLength={800}
                  placeholder="只读检查步骤；不会调用外部工具。"
                  onChange={(event) => setForm({ ...form, instructions: event.target.value })}
                />
              </label>
              <label>
                <span>工具（逗号分隔）</span>
                <input
                  value={form.tools}
                  maxLength={160}
                  placeholder="evidence.inspect, gate.check"
                  onChange={(event) => setForm({ ...form, tools: event.target.value })}
                />
              </label>
              <footer className="skill-form-actions">
                <span>创建后版本为 v0.1.0，可随时停用。</span>
                <button type="button" className="text-button" onClick={cancelDraft}>取消</button>
                <button type="submit" className="solid-button">保存 Skill</button>
              </footer>
            </form>
          )}

          <div className="skill-list">
            {filtered.map((skill) => (
              <article className={`skill-list-card${skill.activation === "auto" ? " is-on" : skill.activation === "manual" ? " is-manual" : ""}`} key={skill.id}>
                <div className="skill-list-head">
                  <span className="skill-list-mark"><Icon name="spark" size={13} /></span>
                  <div className="skill-list-title">
                    <b>{skill.name}</b>
                    <small>
                      /{skill.id} · v{skill.version} · {skill.source === "builtin" ? "BUILTIN" : skill.source === "imported" ? "IMPORTED" : "CUSTOM"}
                    </small>
                  </div>
                  <div className="skill-activation" role="group" aria-label={`${skill.name} 调用方式`}>
                    {(["auto", "manual", "off"] as const).map((activation) => {
                      const disabled = activation === "auto" && skill.source !== "builtin";
                      return (
                        <button
                          key={activation}
                          type="button"
                          className={skill.activation === activation ? "is-active" : ""}
                          aria-pressed={skill.activation === activation}
                          disabled={disabled}
                          title={disabled ? "导入或自定义 Skill 只能手动调用" : `设为${skillActivationLabel(activation)}`}
                          onClick={() => actions.setSkillActivation(skill.id, activation)}
                        >
                          {skillActivationLabel(activation)}
                        </button>
                      );
                    })}
                  </div>
                </div>
                <p>{skill.description}</p>
                <div className="skill-tools">
                  {skill.tools.map((tool) => <span key={tool}>{tool}</span>)}
                </div>
                <details className="skill-detail">
                  <summary>查看指令</summary>
                  <p>{skill.instructions}</p>
                </details>
                <div className="skill-list-foot">
                  <small>
                    {skill.activation === "auto"
                      ? "匹配当前问题或阶段时自动加载"
                      : skill.activation === "manual"
                        ? "仅 /命令 或手动调用"
                        : "当前停用"}
                  </small>
                  <div className="skill-list-actions">
                    {confirmDelete === skill.id ? (
                      <>
                        <button type="button" className="mini-button danger" onClick={() => {
                          actions.deleteSkill(skill.id);
                          setConfirmDelete(null);
                        }}>
                          确认删除
                        </button>
                        <button type="button" className="mini-button" onClick={() => setConfirmDelete(null)}>取消</button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          className="mini-button primary"
                          disabled={!canInvoke || skill.activation === "off"}
                          title={blockedByAuto ? "全自动运行中不可调用" : skill.activation === "off" ? "该 Skill 已停用" : welcomeOpen ? "从当前工作区新建会话并调用" : skill.activation === "auto" ? "立即加载一次" : "调用 Skill"}
                          onClick={() => actions.invokeSkill(skill.id)}
                        >
                          {skill.activation === "auto" ? "立即试运行" : "调用"}
                        </button>
                        {skill.source !== "builtin" && (
                          <button type="button" className="skill-delete" onClick={() => setConfirmDelete(skill.id)} aria-label={`删除 ${skill.name}`}>
                            <Icon name="trash" size={11} />
                          </button>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </article>
            ))}
            {!filtered.length && <p className="context-empty">没有匹配的 Skill。</p>}
          </div>
        </div>
        <input
          ref={folderInputRef}
          type="file"
          multiple
          style={{ display: "none" }}
          onChange={(event) => void onFolderInput(event)}
          {...({ webkitdirectory: "", directory: "" } as Record<string, string>)}
        />
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".md,text/markdown"
          style={{ display: "none" }}
          onChange={(event) => void onFileInput(event)}
        />
      </aside>
    </div>
  );
}
