import { useEffect, useState } from "react";

type EseRun = {
  study_id: string;
  commits?: number | null;
  rate?: number | null;
  adjusted_difference?: number | null;
  status?: string;
  capsule?: string;
};

type Snapshot = {
  schema?: string;
  count?: number;
  runs?: EseRun[];
  boundary?: string;
};

type LoadState = { source: "runtime" | "static" | "none"; runs: EseRun[]; error?: string };

async function load(): Promise<LoadState> {
  try {
    const response = await fetch("/api/ese/runs", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const payload = (await response.json()) as Snapshot;
      return { source: "runtime", runs: payload.runs ?? [] };
    }
  } catch {
    /* fall through to the bundled snapshot */
  }
  try {
    const response = await fetch("/ese-runs.json", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const payload = (await response.json()) as Snapshot;
      return { source: "static", runs: payload.runs ?? [] };
    }
  } catch {
    /* nothing bundled */
  }
  return { source: "none", runs: [], error: "no /api/ese/runs and no /ese-runs.json" };
}

function number(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export function EseRunsPanel() {
  const [state, setState] = useState<LoadState>({ source: "none", runs: [] });

  useEffect(() => {
    let cancelled = false;
    load().then((next) => {
      if (!cancelled) setState(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="context-stack">
      <section className="context-section">
        <div className="context-section-head">
          <span>ESE RUNS</span>
          <span>{state.source === "runtime" ? "LOCAL RUNTIME" : state.source === "static" ? "STATIC SNAPSHOT" : "NO DATA"}</span>
        </div>
        {state.runs.length === 0 ? (
          <p className="context-note">
            本地 runtime 未运行且没有静态快照。运行 <code>python -m research_agent runtime serve</code> 后，
            这里会列出 runtime_data 里的 ESE 研究。
          </p>
        ) : (
          <table className="ese-runs-table">
            <thead>
              <tr>
                <th>study</th>
                <th>commits</th>
                <th>rate</th>
                <th>adj. Δ</th>
                <th>capsule</th>
              </tr>
            </thead>
            <tbody>
              {state.runs.map((run) => (
                <tr key={run.study_id}>
                  <td title={run.capsule ?? ""}>{run.study_id}</td>
                  <td>{run.commits ?? "—"}</td>
                  <td>{number(run.rate)}</td>
                  <td>{number(run.adjusted_difference, 4)}</td>
                  <td>{run.status ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="context-note">
          只读视图：探索性结果，不创建 Claim/EA，不改变 gate；签名仍在 CLI。
        </p>
      </section>
    </div>
  );
}
