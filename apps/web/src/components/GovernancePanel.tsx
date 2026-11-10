import { useEffect, useState } from "react";
import { loadGovernancePreflight } from "../adapters/runtimeApi";
import type { GovernancePreflight } from "../adapters/runtimeApi";

function toneOf(state: string): "ok" | "warn" {
  return state === "fresh" ? "ok" : "warn";
}

function Row({ label, value, state }: { label: string; value: string; state?: string }) {
  return (
    <div className="rsi-gate">
      {state ? <span className={`rsi-state ${toneOf(state)}`}>{state}</span> : <span className="rsi-state idle">·</span>}
      <b>{label}</b>
      <span>{value}</span>
    </div>
  );
}

export function GovernancePanel() {
  const [data, setData] = useState<GovernancePreflight | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    loadGovernancePreflight()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError("");
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setData(null);
          setError(String(reason));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!data) {
    return (
      <section className="context-card">
        <div className="card-label"><span>GOVERNANCE</span><em>UNAVAILABLE</em></div>
        <p className="rsi-headline">
          没有连上本地 runtime，无法读取治理链状态。启动 `python -m research_agent runtime serve` 后重试。
          {error ? ` （${error}）` : ""}
        </p>
      </section>
    );
  }

  const stale = data.checks.spec_self_consistency.stale || [];
  const changed = data.checks.registry.changed || [];
  return (
    <section className="context-card">
      <div className="card-label">
        <span>GOVERNANCE CHAIN</span>
        <em>{data.status}</em>
      </div>
      <Row
        label="SPEC ↔ CHANGELOG"
        value={`${data.checks.spec_self_consistency.checked} 份规格，${stale.length} 份缺本版 changelog`}
        state={stale.length ? "stale" : "fresh"}
      />
      <Row
        label="SPEC ↔ 导出注册表"
        value={`导出 ${data.checks.registry.agents_exported ?? "—"} · 实时 ${data.checks.registry.agents_live ?? "—"} · 差异 ${changed.length}`}
        state={data.checks.registry.status}
      />
      <Row
        label="工具面三方一致"
        value={`MCP ${data.faces.mcp_tools} · HTTP ${data.faces.http_tools} · CLI 命令 ${data.faces.cli_commands}`}
        state={data.checks.tool_surfaces.status}
      />
      {data.blockers.map((item) => (
        <p key={item} className="rsi-headline">阻塞：{item}</p>
      ))}
      {stale.slice(0, 3).map((item) => (
        <p key={item.spec} className="rsi-headline">{item.spec}：{item.problem}</p>
      ))}
      <p className="rsi-headline">{data.boundary}</p>
    </section>
  );
}
