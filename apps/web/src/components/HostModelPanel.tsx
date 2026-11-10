import { useCallback, useEffect, useMemo, useState } from "react";
import {
  loadCriticPanel,
  loadHostModelTurns,
  respondHostModelTurn,
  type CriticPanel,
  type HostModelQueue,
  type HostModelTurn
} from "../adapters/hostModelApi";

/**
 * Host-as-Model handoff: the generation stages this system deferred to the agent operating
 * it, instead of calling an external provider. Answers are capability output — signing,
 * approval, freezing and publication stay in the local CLI.
 */

function remaining(expiresAt: string): string {
  const target = Date.parse(expiresAt);
  if (Number.isNaN(target)) return "—";
  const minutes = Math.round((target - Date.now()) / 60000);
  if (minutes <= 0) return "已过期";
  if (minutes < 60) return `${minutes} 分钟后过期`;
  return `${Math.round(minutes / 60)} 小时后过期`;
}

function expectsLabel(turn: HostModelTurn): string {
  const parts: string[] = [];
  if (turn.expects?.json) parts.push("JSON");
  if (turn.expects?.object) parts.push("对象");
  if (turn.expects?.array_field) parts.push(`${turn.expects.array_field}[]`);
  if (turn.expects?.min_items) parts.push(`≥${turn.expects.min_items} 项`);
  if (turn.expects?.require_keys?.length) parts.push(turn.expects.require_keys.join("/"));
  return parts.join(" · ") || "自由文本";
}

function TurnCard({
  turn,
  onAnswered
}: {
  turn: HostModelTurn;
  onAnswered: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<{ kind: "idle" | "busy" | "error" | "done"; text: string }>({
    kind: "idle",
    text: ""
  });
  const prompt = useMemo(() => {
    const system = turn.request?.system ?? "";
    const user = (turn.request?.turns ?? []).map((item) => item.content).join("\n\n");
    return { system, user };
  }, [turn]);

  const submit = async () => {
    if (!draft.trim()) {
      setStatus({ kind: "error", text: "回答为空：空的交接不会推进流程。" });
      return;
    }
    setStatus({ kind: "busy", text: "提交中…" });
    try {
      const result = await respondHostModelTurn(turn.turn_id, draft, "Qoder Desktop");
      if (!result.accepted) {
        setStatus({
          kind: "error",
          text: `未被接受，交接仍待回答：${(result.errors ?? []).join("；")}`
        });
        return;
      }
      setStatus({
        kind: "done",
        text: `已绑定 ${result.receipt?.text_sha256?.slice(0, 12) ?? ""} · 重跑该步骤即复用此答案`
      });
      onAnswered();
    } catch (error: unknown) {
      setStatus({ kind: "error", text: String(error) });
    }
  };

  return (
    <section className="context-card host-turn">
      <div className="card-label">
        <span>{turn.module || "model"}</span>
        <em>{remaining(turn.expires_at)}</em>
      </div>
      <p className="host-purpose">{turn.purpose || "生成步骤"}</p>
      <div className="host-meta">
        <span title={turn.messages_sha256}>请求 {turn.messages_sha256.slice(0, 12)}</span>
        <span>需要：{expectsLabel(turn)}</span>
        {turn.reject_count > 0 && <span className="host-warn">已拒绝 {turn.reject_count} 次</span>}
      </div>
      <details className="host-prompt">
        <summary>查看运行交给你的提示词</summary>
        {prompt.system && <pre className="host-prompt-system">{prompt.system}</pre>}
        <pre>{prompt.user}</pre>
      </details>
      {turn.last_rejection && (
        <p className="host-rejection">
          上次拒绝：{turn.last_rejection.errors.join("；")}（交接保持待回答，未写入半成品）
        </p>
      )}
      <textarea
        className="host-answer"
        rows={6}
        value={draft}
        placeholder="用你自己的模型产出这一步的结果；提交后仍要过引用白名单与数值上限审计。"
        onChange={(event) => setDraft(event.target.value)}
        disabled={status.kind === "done"}
      />
      <div className="host-actions">
        <button
          type="button"
          className="host-submit"
          onClick={submit}
          disabled={status.kind === "busy" || status.kind === "done"}
        >
          {status.kind === "done" ? "已交接" : status.kind === "busy" ? "提交中" : "提交宿主回答"}
        </button>
        {status.text && (
          <span className={`host-status host-${status.kind}`}>{status.text}</span>
        )}
      </div>
    </section>
  );
}

export function HostModelPanel() {
  const [queue, setQueue] = useState<HostModelQueue | null>(null);
  const [panel, setPanel] = useState<CriticPanel | null>(null);
  const [error, setError] = useState("");

  const refresh = useCallback(() => {
    loadHostModelTurns("", 20)
      .then((result) => {
        setQueue(result);
        setError("");
      })
      .catch((value: unknown) => setError(String(value)));
    loadCriticPanel()
      .then(setPanel)
      .catch(() => setPanel(null));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (error) {
    return (
      <section className="context-card">
        <div className="card-label"><span>HOST MODEL</span><em>UNAVAILABLE</em></div>
        <p className="rsi-headline">
          读不到宿主模型队列。这是本地 runtime 的只读视图：未启动 runtime、或构建为静态模式时不可用。
        </p>
        <p className="host-error">{error}</p>
      </section>
    );
  }

  const pending = (queue?.turns ?? []).filter((item) => item.status === "pending");
  const responded = (queue?.turns ?? []).filter((item) => item.status === "responded");

  return (
    <div className="host-model">
      <section className="context-card">
        <div className="card-label">
          <span>HOST MODEL 交接</span>
          <em>{pending.length ? `${pending.length} 待回答` : "无待回答"}</em>
        </div>
        <p className="rsi-headline">
          绑定了无密钥 host_agent 配置后，生成步骤不再调用外部 API：运行时把它要什么写成一次可审计的
          交接，由正在操作本系统的 Agent 用自己的模型回答。
        </p>
        <div className="rsi-kpis">
          <span><b>{queue?.counts?.pending ?? 0}</b>待回答</span>
          <span><b>{queue?.counts?.responded ?? 0}</b>已回答</span>
          <span><b>{queue?.counts?.expired ?? 0}</b>已过期</span>
        </div>
        <p className="host-boundary">{queue?.boundary}</p>
      </section>

      {panel && (
        <section className="context-card">
          <div className="card-label">
            <span>评审面板 INDEPENDENCE</span>
            <em>{panel.panel_possible ? "可解除单作者" : `单作者 · 缺 ${panel.missing_supplies} 供给`}</em>
          </div>
          <p className="rsi-headline">
            novelty / evidence / feasibility 三个审稿角色只有在由不同 provider+model 回答、且提案模型不兼任审稿时，
            才算结构化独立评审。当前网关里有 <b>{panel.distinct_supplies}</b> 个可区分的模型供给
            （角色需要 {panel.roles.length} 个）。
          </p>
          <div className="host-meta">
            {panel.roles.map((role) => (
              <span key={role}>
                {role} → {panel.suggested[role] ?? "回落提案模型"}
              </span>
            ))}
            <span>提案：{panel.proposer_profile || "未绑定"}</span>
            <span>{panel.proposer_excluded ? "提案模型不在审稿席" : "提案模型仍在审稿席"}</span>
          </div>
          {panel.supplies.slice(0, 6).map((supply) => (
            <div className="host-done-row" key={supply.supply_key}>
              <b>{supply.provider_id}</b>
              <span>{supply.model}</span>
              <code>{supply.profile_id}</code>
              <em>{supply.keyless ? "宿主供给" : "外部 provider"}</em>
            </div>
          ))}
          <p className="host-boundary">
            <code>innovation review --independent</code> 会按这个面板排席；供给不足时直接失败并说明缺什么。
            {panel.boundary}
          </p>
        </section>
      )}

      {pending.map((turn) => (
        <TurnCard key={turn.turn_id} turn={turn} onAnswered={refresh} />
      ))}

      {responded.length > 0 && (
        <section className="context-section">
          <div className="section-title">
            <span>已完成的交接</span>
            <em>答案按请求哈希复用，重跑不重复提问</em>
          </div>
          {responded.map((turn) => (
            <div className="host-done-row" key={turn.turn_id}>
              <b>{turn.module}</b>
              <span>{turn.purpose}</span>
              <code title={turn.receipt?.text_sha256 ?? ""}>
                {(turn.receipt?.text_sha256 ?? "").slice(0, 12)}
              </code>
              <em>{turn.receipt?.host_label ?? "host"}</em>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
