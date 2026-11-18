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

type EseHistoryEntry = {
  id: string;
  date?: string;
  stage?: string;
  title?: string;
  question?: string;
  method?: string;
  data?: string;
  finding?: string;
  caveat?: string;
  artifact?: string;
  link?: string;
};

type HistorySnapshot = {
  schema?: string;
  count?: number;
  entries?: EseHistoryEntry[];
  boundary?: string;
};

type LoadState = { source: "runtime" | "static" | "none"; runs: EseRun[]; error?: string };
type HistoryState = { source: "static" | "none"; entries: EseHistoryEntry[]; boundary?: string };

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

async function loadHistory(): Promise<HistoryState> {
  try {
    const response = await fetch("/ese-history.json", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const payload = (await response.json()) as HistorySnapshot;
      return { source: "static", entries: payload.entries ?? [], boundary: payload.boundary };
    }
  } catch {
    /* nothing bundled */
  }
  return { source: "none", entries: [] };
}

function number(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

export function EseRunsPanel() {
  const [state, setState] = useState<LoadState>({ source: "none", runs: [] });
  const [history, setHistory] = useState<HistoryState>({ source: "none", entries: [] });

  useEffect(() => {
    let cancelled = false;
    load().then((next) => {
      if (!cancelled) setState(next);
    });
    loadHistory().then((next) => {
      if (!cancelled) setHistory(next);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="context-stack">
      <section className="context-section">
        <div className="context-section-head">
          <span>ESE 工作历史</span>
          <span>{history.entries.length > 0 ? `${history.entries.length} 条` : "NO DATA"}</span>
        </div>
        {history.entries.length === 0 ? (
          <p className="context-note">
            没有找到 <code>ese-history.json</code>。历史是策展视图，数字需与
            <code>runtime_data</code> 原产物一致，由 <code>scripts/build_web_ese_history.py</code> 守护。
          </p>
        ) : (
          <ol className="ese-history">
            {history.entries.map((entry) => (
              <li key={entry.id} className="ese-history-entry">
                <div className="ese-history-meta">
                  <span>{entry.date ?? "—"}</span>
                  <span>{entry.stage ?? "—"}</span>
                  <code>{entry.id}</code>
                </div>
                <div className="ese-history-title">{entry.title ?? entry.id}</div>
                {entry.question ? <p className="ese-history-question">{entry.question}</p> : null}
                {entry.finding ? <p className="ese-history-finding">{entry.finding}</p> : null}
                {entry.caveat ? <p className="ese-history-caveat">边界：{entry.caveat}</p> : null}
                <div className="ese-history-foot">
                  <span>{entry.method ?? ""}{entry.data ? ` · ${entry.data}` : ""}</span>
                  {entry.link ? <a href={entry.link}>来龙去脉 →</a> : null}
                </div>
              </li>
            ))}
          </ol>
        )}
        <p className="context-note">
          策展历史：数字与原产物逐条核对；只读，不创建 Claim/EA/签名，不改变 gate 判定。
        </p>
      </section>

      <section className="context-section">
        <div className="context-section-head">
          <span>ESE RUNTIME SNAPSHOT</span>
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
