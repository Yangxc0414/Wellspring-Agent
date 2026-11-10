import { useEffect, useMemo, useState } from "react";
import {
  createCustomAgent,
  deleteCustomAgent,
  loadCustomAgents,
  loadEvolutionPolicy,
  updateCustomAgent,
  updateEvolutionPolicy
} from "../../adapters/runtimeApi";
import type {
  CustomAgentRecord,
  CustomAgentSnapshot,
  EvolutionPolicySnapshot
} from "../../adapters/runtimeApi";
import { Card } from "./SettingsSections";
import { AGENT_TEMPLATES, type AgentPreset, type AgentTemplate } from "../../domain/agentTemplates";
import { SourcePill, type SourceKind } from "../SourcePill";

type CheckMeta = CustomAgentSnapshot["checks"][number];
type RoleMeta = CustomAgentSnapshot["roles"][number];

interface PendingAgent extends AgentPreset {
  key: string;
  templateId: string;
}

const LOCAL_AGENTS_KEY = "researchAgent.customAgentsDraft.v1";
const LOCAL_POLICY_KEY = "researchAgent.evolutionPolicyDraft.v1";
const FALLBACK_POLICY: EvolutionPolicySnapshot = {
  schema_version: "evolution-policy-0.1",
  generated_at: "",
  enabled: true,
  scopes: [
    { id: "literature.memory_order", label: "文献记忆调序", kind: "process", description: "按历史覆盖/缺口重排下一轮面向顺序与预算；关闭后使用均衡分组。", enabled: true, effective: true, allowed_by_master: true },
    { id: "literature.query_planner", label: "检索模板候选", kind: "skill", description: "从 facet 级重复缺口生成 query-planner 候选；仍需 dry-run 与人工准入。", enabled: true, effective: true, allowed_by_master: true },
    { id: "orchestrator.facet_budget", label: "面向预算候选", kind: "process", description: "从预算/全文约束生成预算或全文获取流程候选；不改变 full-text-only 规则。", enabled: true, effective: true, allowed_by_master: true }
  ],
  locked: [
    { id: "claim.statement", label: "Claim 陈述", reason: "必须由作者/PI 签署" },
    { id: "evidence.artifact", label: "EvidenceArtifact", reason: "只能由运行与人签产生" },
    { id: "gate.decision", label: "门禁判定", reason: "G1/G2/S5b/G5 只能人工放行" },
    { id: "rubric", label: "评价规则", reason: "规则冻结，候选不得改写" },
    { id: "heldout", label: "Held-out 集合", reason: "不得用于提案或调参" },
    { id: "closure", label: "闭包报告", reason: "只能由闭包检查产生" },
    { id: "signature", label: "签名", reason: "浏览器与编排器都不提供签核" },
    { id: "export", label: "导出清单", reason: "未闭包/已过期时锁定" }
  ],
  updated_at: "",
  boundary: "局部可见性开关；不会解锁 Claim/EA/gate/rubric/held-out/closure/signature/export"
};

function readLocal<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeLocal(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // localStorage can be unavailable; the runtime path remains authoritative.
  }
}

function deriveAgentFields(checks: string[], meta: CheckMeta[]) {
  const entries = meta.filter((item) => checks.includes(item.id));
  const stages = Array.from(new Set(entries.map((item) => item.stage)));
  return {
    checks: entries.map((item) => item.id),
    check_labels: entries.map((item) => item.label),
    stages,
    stage: stages.join(" / "),
    tools: Array.from(new Set(entries.map((item) => item.tool))),
    outputs: Array.from(new Set(entries.map((item) => item.output)))
  };
}

function localAgent(
  input: {
    name: string;
    role: string;
    purpose: string;
    checks: string[];
    enabled: boolean;
  },
  checksMeta: CheckMeta[],
  rolesMeta: RoleMeta[]
): CustomAgentRecord {
  const stamp = new Date().toISOString();
  return {
    id: "LOCAL-CAG-" + Math.random().toString(36).slice(2, 8),
    name: input.name.trim(),
    role: input.role,
    role_label: rolesMeta.find((item) => item.id === input.role)?.label ?? input.role,
    purpose: input.purpose.trim(),
    enabled: input.enabled,
    advisory_only: true,
    writes: [],
    ...deriveAgentFields(input.checks, checksMeta),
    created_at: stamp,
    updated_at: stamp
  };
}

function Switch({
  checked,
  onChange,
  label,
  disabled = false
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`settings-toggle${checked ? " is-on" : ""}`}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <i />
    </button>
  );
}

export function AgentManagement() {
  const [agentState, setAgentState] = useState<{
    loading: boolean;
    source: SourceKind;
    agents: CustomAgentRecord[];
    checks: CheckMeta[];
    roles: RoleMeta[];
    error: string;
  }>({ loading: true, source: "snapshot", agents: [], checks: [], roles: [], error: "" });
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState("reviewer");
  const [purpose, setPurpose] = useState("");
  const [checks, setChecks] = useState<string[]>(["coverage"]);
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [batchOpen, setBatchOpen] = useState(false);
  const [pending, setPending] = useState<PendingAgent[]>([]);
  const [batchError, setBatchError] = useState("");
  const [batchSaving, setBatchSaving] = useState(false);

  const [policy, setPolicy] = useState<EvolutionPolicySnapshot>(FALLBACK_POLICY);
  const [policySource, setPolicySource] = useState<SourceKind>("snapshot");
  const [policyDraft, setPolicyDraft] = useState<{
    enabled: boolean;
    scopes: Record<string, boolean>;
  }>({ enabled: true, scopes: Object.fromEntries(FALLBACK_POLICY.scopes.map((item) => [item.id, item.enabled])) });
  const [policyError, setPolicyError] = useState("");
  const [policySaved, setPolicySaved] = useState("");
  const [policySaving, setPolicySaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadCustomAgents()
      .then((result) => {
        if (cancelled) return;
        const local = readLocal<CustomAgentRecord[]>(LOCAL_AGENTS_KEY);
        if (result.source === "runtime") {
          setAgentState({
            loading: false,
            source: "runtime",
            agents: result.data.agents,
            checks: result.data.checks,
            roles: result.data.roles,
            error: ""
          });
        } else if (local) {
          setAgentState({
            loading: false,
            source: "local",
            agents: local,
            checks: result.data.checks,
            roles: result.data.roles,
            error: ""
          });
        } else {
          setAgentState({
            loading: false,
            source: "snapshot",
            agents: result.data.agents,
            checks: result.data.checks,
            roles: result.data.roles,
            error: ""
          });
        }
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const local = readLocal<CustomAgentRecord[]>(LOCAL_AGENTS_KEY);
        setAgentState({
          loading: false,
          source: local ? "local" : "snapshot",
          agents: local ?? [],
          checks: [],
          roles: [],
          error: local ? "" : String(error)
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    loadEvolutionPolicy()
      .then((result) => {
        if (cancelled) return;
        const local = readLocal<EvolutionPolicySnapshot>(LOCAL_POLICY_KEY);
        if (result.source === "runtime") {
          setPolicy(result.data);
          setPolicySource("runtime");
        } else if (local) {
          setPolicy(local);
          setPolicySource("local");
        } else {
          setPolicy(result.data);
          setPolicySource("snapshot");
        }
      })
      .catch(() => {
        if (cancelled) return;
        const local = readLocal<EvolutionPolicySnapshot>(LOCAL_POLICY_KEY);
        if (local) {
          setPolicy(local);
          setPolicySource("local");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setPolicyDraft({
      enabled: policy.enabled,
      scopes: Object.fromEntries(policy.scopes.map((item) => [item.id, item.enabled]))
    });
  }, [policy]);

  const enabledAgents = useMemo(
    () => agentState.agents.filter((agent) => agent.enabled),
    [agentState.agents]
  );

  const toggleCheck = (id: string) => {
    setChecks((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  };

  const roleLabel = (id: string) => agentState.roles.find((item) => item.id === id)?.label ?? id;
  const checkLabel = (id: string) => agentState.checks.find((item) => item.id === id)?.label ?? id;

  const addTemplate = (template: AgentTemplate) => {
    if (pending.some((item) => item.templateId === template.id)) return;
    if (agentState.agents.length + pending.length + template.agents.length > 30) {
      setBatchError("最多 30 个子智能体；请先删除不再使用的配置");
      return;
    }
    const taken = new Set([
      ...agentState.agents.map((item) => item.name.toLowerCase()),
      ...pending.map((item) => item.name.toLowerCase())
    ]);
    const stamp = Date.now();
    const fresh = template.agents.map((agent, index) => {
      let name = agent.name;
      if (taken.has(name.toLowerCase())) {
        let suffix = 2;
        while (taken.has(`${agent.name} ${suffix}`.toLowerCase())) suffix += 1;
        name = `${agent.name} ${suffix}`;
      }
      taken.add(name.toLowerCase());
      return {
        ...agent,
        name,
        key: `${template.id}-${stamp}-${index}`,
        templateId: template.id
      };
    });
    setPending((current) => [...current, ...fresh]);
    setBatchError("");
  };

  const removePending = (key: string) => {
    setPending((current) => current.filter((item) => item.key !== key));
  };

  const removeTemplate = (templateId: string) => {
    setPending((current) => current.filter((item) => item.templateId !== templateId));
  };

  const renamePending = (key: string, name: string) => {
    setPending((current) =>
      current.map((item) => (item.key === key ? { ...item, name } : item))
    );
  };

  const onBatchCreate = async () => {
    if (!pending.length) {
      setBatchError("先选择模板或加入待创建配置");
      return;
    }
    if (!agentState.checks.length || !agentState.roles.length) {
      setBatchError("检查项/角色 schema 尚未加载");
      return;
    }
    const names = pending.map((item) => item.name.trim().toLowerCase());
    if (names.some((name) => !name)) {
      setBatchError("每个子智能体都需要名称");
      return;
    }
    if (new Set(names).size !== names.length) {
      setBatchError("待创建清单里有重名；请先改名或移除");
      return;
    }
    const existing = new Set(agentState.agents.map((item) => item.name.trim().toLowerCase()));
    if (pending.some((item) => existing.has(item.name.trim().toLowerCase()))) {
      setBatchError("待创建名称与已有子智能体重名；请先改名");
      return;
    }
    if (agentState.agents.length + pending.length > 30) {
      setBatchError("最多 30 个子智能体");
      return;
    }
    setBatchSaving(true);
    setBatchError("");
    try {
      if (agentState.source === "runtime") {
        const created: CustomAgentRecord[] = [];
        const failed: PendingAgent[] = [];
        const errors: string[] = [];
        for (const item of pending) {
          try {
            const record = await createCustomAgent({
              name: item.name.trim(),
              role: item.role,
              purpose: item.purpose,
              checks: item.checks,
              enabled: true
            });
            created.push(record);
          } catch (error: unknown) {
            failed.push(item);
            errors.push(`${item.name}: ${String(error)}`);
          }
        }
        if (created.length) {
          setAgentState((current) => ({ ...current, agents: [...created, ...current.agents] }));
        }
        if (failed.length) {
          setPending(failed);
          setBatchError(errors.join("；"));
        } else {
          setPending([]);
          setBatchOpen(false);
        }
      } else {
        const created = pending.map((item) =>
          localAgent(
            {
              name: item.name.trim(),
              role: item.role,
              purpose: item.purpose,
              checks: item.checks,
              enabled: true
            },
            agentState.checks,
            agentState.roles
          )
        );
        const next = [...created, ...agentState.agents];
        writeLocal(LOCAL_AGENTS_KEY, next);
        setAgentState((current) => ({ ...current, source: "local", agents: next }));
        setPending([]);
        setBatchOpen(false);
      }
    } finally {
      setBatchSaving(false);
    }
  };

  const resetForm = () => {
    setName("");
    setRole("reviewer");
    setPurpose("");
    setChecks(["coverage"]);
    setFormError("");
    setEditingId(null);
  };

  const startEdit = (agent: CustomAgentRecord) => {
    setEditingId(agent.id);
    setName(agent.name);
    setRole(agent.role);
    setPurpose(agent.purpose);
    setChecks(agent.checks);
    setFormError("");
    setFormOpen(true);
  };

  const onSave = async () => {
    const cleanName = name.trim();
    const cleanPurpose = purpose.trim();
    if (cleanName.length < 2) {
      setFormError("名称至少 2 个字符");
      return;
    }
    if (cleanPurpose.length < 4) {
      setFormError("用途至少 4 个字符");
      return;
    }
    if (!checks.length) {
      setFormError("至少选择一个检查项");
      return;
    }
    if (!agentState.checks.length) {
      setFormError("检查项 schema 尚未加载");
      return;
    }
    if (
      agentState.agents.some(
        (item) =>
          item.id !== editingId &&
          item.name.trim().toLowerCase() === cleanName.toLowerCase()
      )
    ) {
      setFormError("已有同名子智能体；换一个名称");
      return;
    }
    setFormError("");
    setSaving(true);
    try {
      if (editingId) {
        if (agentState.source === "runtime") {
          const updated = await updateCustomAgent(editingId, {
            name: cleanName,
            purpose: cleanPurpose,
            checks
          });
          setAgentState((current) => ({
            ...current,
            agents: current.agents.map((item) => (item.id === editingId ? updated : item))
          }));
        } else {
          const derived = deriveAgentFields(checks, agentState.checks);
          const next = agentState.agents.map((item) =>
            item.id === editingId
              ? {
                  ...item,
                  name: cleanName,
                  purpose: cleanPurpose,
                  ...derived,
                  updated_at: new Date().toISOString()
                }
              : item
          );
          writeLocal(LOCAL_AGENTS_KEY, next);
          setAgentState((current) => ({ ...current, source: "local", agents: next }));
        }
      } else {
        const input = { name: cleanName, role, purpose: cleanPurpose, checks, enabled: true };
        if (agentState.source === "runtime") {
          const created = await createCustomAgent(input);
          setAgentState((current) => ({ ...current, agents: [created, ...current.agents] }));
        } else {
          const created = localAgent(input, agentState.checks, agentState.roles);
          const next = [created, ...agentState.agents];
          writeLocal(LOCAL_AGENTS_KEY, next);
          setAgentState((current) => ({ ...current, source: "local", agents: next }));
        }
      }
      resetForm();
      setFormOpen(false);
    } catch (error: unknown) {
      setFormError(String(error));
    } finally {
      setSaving(false);
    }
  };

  const onToggleAgent = async (agent: CustomAgentRecord) => {
    try {
      if (agentState.source === "runtime") {
        const updated = await updateCustomAgent(agent.id, { enabled: !agent.enabled });
        setAgentState((current) => ({
          ...current,
          agents: current.agents.map((item) => (item.id === agent.id ? updated : item))
        }));
      } else {
        const next = agentState.agents.map((item) =>
          item.id === agent.id ? { ...item, enabled: !item.enabled } : item
        );
        writeLocal(LOCAL_AGENTS_KEY, next);
        setAgentState((current) => ({ ...current, source: "local", agents: next }));
      }
    } catch (error: unknown) {
      setAgentState((current) => ({ ...current, error: String(error) }));
    }
  };

  const onDeleteAgent = async (agent: CustomAgentRecord) => {
    if (!window.confirm(`删除自定义子智能体「${agent.name}」？`)) return;
    try {
      if (agentState.source === "runtime") {
        await deleteCustomAgent(agent.id);
      }
      const next = agentState.agents.filter((item) => item.id !== agent.id);
      if (agentState.source !== "runtime") writeLocal(LOCAL_AGENTS_KEY, next);
      setAgentState((current) => ({
        ...current,
        source: agentState.source === "runtime" ? "runtime" : "local",
        agents: next
      }));
    } catch (error: unknown) {
      setAgentState((current) => ({ ...current, error: String(error) }));
    }
  };

  const onSavePolicy = async () => {
    setPolicyError("");
    setPolicySaved("");
    setPolicySaving(true);
    try {
      if (policySource === "runtime") {
        const updated = await updateEvolutionPolicy({
          enabled: policyDraft.enabled,
          scopes: policyDraft.scopes
        });
        setPolicy(updated);
        setPolicySource("runtime");
      } else {
        const updated: EvolutionPolicySnapshot = {
          ...policy,
          generated_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          enabled: policyDraft.enabled,
          scopes: policy.scopes.map((item) => ({
            ...item,
            enabled: policyDraft.scopes[item.id] ?? item.enabled,
            effective: policyDraft.enabled && (policyDraft.scopes[item.id] ?? item.enabled),
            allowed_by_master: policyDraft.enabled
          }))
        };
        writeLocal(LOCAL_POLICY_KEY, updated);
        setPolicy(updated);
        setPolicySource("local");
      }
      setPolicySaved(policySource === "runtime" ? "已写入 runtime" : "已保存本地草稿");
    } catch (error: unknown) {
      setPolicyError(String(error));
    } finally {
      setPolicySaving(false);
    }
  };

  return (
    <div className="agent-management">
      <Card
        title="手动子智能体"
        description="人工注册的 advisory role：只能选择白名单检查项，工具与输出由检查项派生；不写 Claim/EA，不通过门禁。"
      >
        <div className="settings-toolbar">
          <SourcePill source={agentState.source} />
          <span className="settings-source">{enabledAgents.length}/{agentState.agents.length} ENABLED</span>
          <button
            type="button"
            className="settings-btn"
            onClick={() => {
              if (formOpen) {
                setFormOpen(false);
                resetForm();
              } else {
                resetForm();
                setFormOpen(true);
              }
            }}
          >
            {formOpen ? "收起单个表单" : "添加单个"}
          </button>
          <button
            type="button"
            className="settings-btn"
            onClick={() => {
              setBatchOpen((value) => !value);
              setBatchError("");
            }}
          >
            {batchOpen ? "收起模板" : pending.length ? `批量新建 · 待创建 ${pending.length}` : "批量新建"}
          </button>
        </div>
        {batchOpen && (
          <div className="agent-batch">
            <p className="agent-batch-intro">
              选择一个或多个模板；每个模板会展开成多个只读 advisory 角色。创建前可改名或移除，仍然只使用白名单 checks。
            </p>
            <div className="agent-template-grid">
              {AGENT_TEMPLATES.map((template) => {
                const addedCount = pending.filter((item) => item.templateId === template.id).length;
                return (
                  <article className={`agent-template${addedCount ? " is-added" : ""}`} key={template.id}>
                    <div className="agent-template-head">
                      <b>{template.title}</b>
                      <span>{template.agents.length} 个角色</span>
                    </div>
                    <p>{template.description}</p>
                    <div className="check-pill-row">
                      {Array.from(new Set(template.agents.flatMap((agent) => agent.checks))).map((check) => (
                        <span className="check-pill" key={check}>{checkLabel(check)}</span>
                      ))}
                    </div>
                    <div className="agent-template-actions">
                      <button
                        type="button"
                        className="settings-mini-btn"
                        disabled={addedCount > 0}
                        onClick={() => addTemplate(template)}
                      >
                        {addedCount ? `已加入 ${addedCount}/${template.agents.length}` : "加入待创建"}
                      </button>
                      {addedCount > 0 && (
                        <button
                          type="button"
                          className="settings-mini-btn"
                          onClick={() => removeTemplate(template.id)}
                        >
                          移除本组
                        </button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
            {pending.length > 0 ? (
              <div className="agent-batch-pending">
                <div className="agent-batch-head">
                  <b>待创建 {pending.length} 个</b>
                  <span>名称可改；角色与检查项由模板固定</span>
                </div>
                {pending.map((item) => (
                  <div className="agent-batch-row" key={item.key}>
                    <input
                      value={item.name}
                      aria-label={`名称 ${item.name}`}
                      onChange={(event) => renamePending(item.key, event.target.value)}
                    />
                    <span>{roleLabel(item.role)} · {item.checks.map(checkLabel).join(" / ")}</span>
                    <button type="button" className="settings-mini-btn" onClick={() => removePending(item.key)}>
                      移除
                    </button>
                  </div>
                ))}
                <div className="settings-toolbar">
                  <button
                    type="button"
                    className="settings-btn primary"
                    disabled={batchSaving}
                    onClick={() => void onBatchCreate()}
                  >
                    {batchSaving ? "创建中…" : `创建 ${pending.length} 个`}
                  </button>
                  <button
                    type="button"
                    className="settings-btn"
                    onClick={() => {
                      setPending([]);
                      setBatchOpen(false);
                      setBatchError("");
                    }}
                  >
                    取消
                  </button>
                </div>
              </div>
            ) : (
              <p className="settings-note">先选择模板；也可以使用下方“添加单个”做完全自定义的单个角色。</p>
            )}
            {batchError && <p className="settings-empty">{batchError}</p>}
          </div>
        )}
        {formOpen && (
          <div className="custom-agent-form">
            <div className="custom-agent-form-head">
              <b>{editingId ? "编辑子智能体" : "新建单个子智能体"}</b>
              <span>{editingId ? "角色不可改；名称、用途与 checks 可更新" : "只读 advisory；工具与输出由 checks 派生"}</span>
            </div>
            <div className="custom-agent-form-grid">
              <label className="settings-field">
                <span>名称</span>
                <input value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：覆盖与引用审稿人" />
              </label>
              <label className="settings-field">
                <span>角色</span>
                <select
                  value={role}
                  disabled={Boolean(editingId)}
                  title={editingId ? "编辑时不能修改角色；如需换角色请新建一个" : undefined}
                  onChange={(event) => setRole(event.target.value)}
                >
                  {agentState.roles.map((item) => (
                    <option key={item.id} value={item.id}>{item.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <label className="settings-field">
              <span>用途</span>
              <textarea value={purpose} onChange={(event) => setPurpose(event.target.value)} placeholder="说明它检查什么、在哪个阶段提醒你" />
            </label>
            <div className="settings-field">
              <span>检查项（决定可执行阶段与只读工具）</span>
              <div className="check-pill-row">
                {agentState.checks.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`check-pill${checks.includes(item.id) ? " is-on" : ""}`}
                    title={item.description}
                    onClick={() => toggleCheck(item.id)}
                  >
                    {item.label} · {item.stage}
                  </button>
                ))}
              </div>
            </div>
            {formError && <p className="settings-empty">{formError}</p>}
            <div className="settings-toolbar">
              <button type="button" className="settings-btn primary" disabled={saving} onClick={() => void onSave()}>
                {saving ? "保存中…" : editingId ? "保存修改" : "注册单个"}
              </button>
              <button type="button" className="settings-btn" onClick={() => { setFormOpen(false); resetForm(); }}>
                取消
              </button>
            </div>
          </div>
        )}
        {agentState.loading && <p className="settings-empty">读取自定义子智能体…</p>}
        {agentState.error && <p className="settings-empty">读取失败：{agentState.error}</p>}
        <div className="custom-agent-list">
          {agentState.agents.map((agent) => (
            <article className={`custom-agent-card${agent.enabled ? "" : " is-off"}`} key={agent.id}>
              <div className="custom-agent-head">
                <div>
                  <b>{agent.name}</b>
                  <span>{agent.role_label} · {agent.stages.join(" / ")}</span>
                </div>
                <div className="custom-agent-actions">
                  <Switch checked={agent.enabled} onChange={() => void onToggleAgent(agent)} label={`启用 ${agent.name}`} />
                  <button type="button" className="settings-mini-btn" onClick={() => startEdit(agent)}>编辑</button>
                  <button type="button" className="settings-mini-btn" onClick={() => void onDeleteAgent(agent)}>删除</button>
                </div>
              </div>
              <p>{agent.purpose}</p>
              <div className="check-pill-row">
                {agent.checks.map((check) => (
                  <span className="check-pill is-on" key={check}>{agent.check_labels[agent.checks.indexOf(check)] ?? check}</span>
                ))}
              </div>
              <small>{agent.tools.join(" · ")} → {agent.outputs.join(" / ")}</small>
            </article>
          ))}
        </div>
        {!agentState.loading && !agentState.agents.length && (
          <p className="settings-empty">还没有手动子智能体。可以先用上方模板批量创建，或用“添加单个”选择检查项注册一个；它们只会在对应阶段产出 advisory note。</p>
        )}
        <p className="settings-note">
          自定义子智能体只接收白名单 checks；不接收任意 prompt、不执行代码、不调用外部工具。{agentState.source === "local" ? "当前是本地草稿；需在 runtime 在线时重新保存，才会进入 CLI/编排执行。" : ""}
        </p>
      </Card>

      <Card
        title="自进化开关"
        description="先决定系统是否可以自适应过程；再按层选择。Claim、证据、门禁、评价规则、held-out、闭包与签名永远不进入可切换集合。"
      >
        <div className="policy-master">
          <div>
            <b>允许自动自进化</b>
            <span>关闭后：忽略文献记忆调序，不再生成新的 skill/process 候选；历史 lease/confirmation 不追溯撤销。</span>
          </div>
          <Switch
            checked={policyDraft.enabled}
            onChange={(value) => setPolicyDraft((current) => ({ ...current, enabled: value }))}
            label="允许自动自进化"
          />
        </div>
        <div className={`policy-scope-list${policyDraft.enabled ? "" : " is-paused"}`}>
          {policy.scopes.map((scope) => {
            const enabled = policyDraft.scopes[scope.id] ?? scope.enabled;
            return (
              <div className="policy-scope-row" key={scope.id}>
                <div>
                  <b>{scope.label} <code>{scope.id}</code></b>
                  <span>{scope.description}</span>
                </div>
                <div className="policy-scope-control">
                  <span className="settings-state" data-state={scope.kind === "skill" ? "pilot" : "active"}>{scope.kind}</span>
                  <Switch
                    checked={enabled}
                    onChange={(value) =>
                      setPolicyDraft((current) => ({
                        ...current,
                        scopes: { ...current.scopes, [scope.id]: value }
                      }))
                    }
                    label={scope.label}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <div className="policy-locked">
          <b>LOCKED · 不可切换</b>
          <div className="check-pill-row">
            {policy.locked.map((item) => (
              <span className="check-pill" key={item.id} title={item.reason}>{item.label}</span>
            ))}
          </div>
        </div>
        {policyError && <p className="settings-empty">{policyError}</p>}
        <div className="settings-toolbar">
          <button type="button" className="settings-btn primary" disabled={policySaving} onClick={() => void onSavePolicy()}>
            {policySaving ? "保存中…" : "应用策略"}
          </button>
          <SourcePill source={policySource} />
          {policySaved && <span className="settings-note">{policySaved}</span>}
        </div>
        <p className="settings-note">
          关闭是“停止新的自动改进”，不是撤销已有证据或租约；Claim/EA/gate 仍需人工。{policySource === "local" ? "本地草稿不会改变 CLI 读取的 runtime policy 文件。" : ""}
        </p>
      </Card>
    </div>
  );
}
