import { useEffect, useState } from "react";
import { runtimeAvailable } from "../domain/capabilities";

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

type EseRepo = {
  repo?: string;
  head?: string;
  commits?: number;
  test_cochange?: number;
  rate?: number;
  ci?: number[];
};

type EseStratum = {
  factor?: string;
  value?: string;
  bug?: { rate?: number };
  other?: { rate?: number };
  difference?: number;
  degenerate?: boolean;
};

type EseChainStep = {
  name: string;
  ok: boolean;
  detail: string;
  path: string;
};

type EseStudy = {
  study_id: string;
  directory: string;
  method?: string;
  questions?: string[];
  protocol_sha256?: string;
  repos?: EseRepo[];
  pooled?: {
    commits?: number;
    test_cochange?: number;
    rate?: number;
    ci?: number[];
    bugfix?: { hits?: number; total?: number; rate?: number };
    non_bugfix?: { hits?: number; total?: number; rate?: number };
    difference?: number;
    permutation?: { n?: number; p_value_two_sided?: number };
  };
  strata?: EseStratum[];
  time_split?: {
    early?: { rate?: number; ci?: number[] };
    late?: { rate?: number; ci?: number[] };
    difference?: number;
    permutation?: { p_value_two_sided?: number };
  };
  boundary?: string;
  chain?: EseChainStep[];
  state?: string;
};

type StudiesSnapshot = {
  schema?: string;
  count?: number;
  studies?: EseStudy[];
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
    // The version query keeps GitHub Pages from serving the 404 it cached when this file
    // first appeared. Bump it when the curated history changes shape.
    const response = await fetch("/ese-history.json?v=1", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const payload = (await response.json()) as HistorySnapshot;
      return { source: "static", entries: payload.entries ?? [], boundary: payload.boundary };
    }
  } catch {
    /* nothing bundled */
  }
  return { source: "none", entries: [] };
}

async function loadStudies(): Promise<EseStudy[]> {
  try {
    const response = await fetch("/ese-studies.json?v=1", { headers: { Accept: "application/json" } });
    if (response.ok) {
      const payload = (await response.json()) as StudiesSnapshot;
      return payload.studies ?? [];
    }
  } catch {
    /* nothing bundled */
  }
  return [];
}

function number(value: number | null | undefined, digits = 3): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

function ci(value: number[] | undefined): string {
  if (!Array.isArray(value) || value.length !== 2) return "—";
  return `[${number(value[0])}, ${number(value[1])}]`;
}

function shortSha(value: string | undefined): string {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 12)}…` : value;
}

function StudyDetail({ study }: { study: EseStudy }) {
  const pooled = study.pooled ?? {};
  const bugfix = pooled.bugfix ?? {};
  const other = pooled.non_bugfix ?? {};
  const strata = study.strata ?? [];
  const chain = study.chain ?? [];
  const split = study.time_split ?? {};
  const signed = (study.state ?? "").includes("SIGNED");
  const base = `runtime_data/${study.directory}`;

  return (
    <section className="context-section">
      <div className="context-section-head">
        <span>ESE 研究详情</span>
        <span className={signed ? "ese-state-ok" : "ese-state-todo"}>{study.state ?? "—"}</span>
      </div>
      <p className="context-note">
        {study.study_id} · {study.method ?? "—"} · protocol <code>{shortSha(study.protocol_sha256)}</code>
      </p>

      {(study.questions ?? []).length > 0 ? (
        <ul className="ese-rq">
          {(study.questions ?? []).map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      ) : null}

      {(study.repos ?? []).length > 0 ? (
        <div className="ese-detail-block">
          <h4>数据与抽样</h4>
          <table className="ese-runs-table">
            <thead>
              <tr>
                <th>repo</th>
                <th>commits</th>
                <th>rate</th>
                <th>95% CI</th>
              </tr>
            </thead>
            <tbody>
              {(study.repos ?? []).map((repo) => (
                <tr key={repo.repo}>
                  <td title={`HEAD ${repo.head ?? ""}`}>{repo.repo}</td>
                  <td>{repo.commits ?? "—"}</td>
                  <td>{number(repo.rate, 4)}</td>
                  <td>{ci(repo.ci)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="context-note">
          这条研究没有 repository-mining 明细（无 result.json 的 repos 字段）；它是反馈/记忆实验，不产生仓库级结果。
        </p>
      )}

      {typeof pooled.rate === "number" ? (
        <div className="ese-detail-block">
          <h4>结果</h4>
          <p className="context-note">
            合并 {pooled.test_cochange ?? "—"}/{pooled.commits ?? "—"} = <b>{number(pooled.rate, 4)}</b>，95% CI {ci(pooled.ci)}
          </p>
          <p className="context-note">
            缺陷修复 {bugfix.hits ?? "—"}/{bugfix.total ?? "—"} = {number(bugfix.rate, 4)}；其它 {other.hits ?? "—"}/
            {other.total ?? "—"} = {number(other.rate, 4)}；差 <b>{number(pooled.difference, 4)}</b>，置换 p ={" "}
            <b>{pooled.permutation?.p_value_two_sided ?? "—"}</b>
          </p>
          {typeof split.difference === "number" ? (
            <p className="context-note">
              时间切分：早期 {number(split.early?.rate, 4)} {ci(split.early?.ci)}；晚期 {number(split.late?.rate, 4)}{" "}
              {ci(split.late?.ci)}；差 {number(split.difference, 4)}（p = {split.permutation?.p_value_two_sided ?? "—"}）
            </p>
          ) : null}
        </div>
      ) : null}

      {strata.length > 0 ? (
        <div className="ese-detail-block">
          <h4>分层：差异不是每个项目都成立</h4>
          <table className="ese-runs-table">
            <thead>
              <tr>
                <th>factor</th>
                <th>value</th>
                <th>Δ</th>
              </tr>
            </thead>
            <tbody>
              {strata.map((item) => (
                <tr
                  key={`${item.factor}-${item.value}`}
                  title={`bug ${number(item.bug?.rate, 4)} · other ${number(item.other?.rate, 4)}`}
                >
                  <td>{item.factor ?? "—"}</td>
                  <td>{item.value ?? "—"}</td>
                  <td className={typeof item.difference === "number" && item.difference < 0 ? "ese-negative" : ""}>
                    {number(item.difference, 4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="context-note">
            总体差异为正，但 click 与 &gt;5 提交桶的差为负：合并样本的结论不能外推到单项目。
          </p>
        </div>
      ) : null}

      {chain.length > 0 ? (
        <div className="ese-detail-block">
          <h4>证据链（按盘上文件判定）</h4>
          <ul className="ese-chain">
            {chain.map((step) => (
              <li key={step.name}>
                <span className={step.ok ? "ok" : "todo"}>{step.ok ? "✓" : "·"}</span>
                <span className="name">{step.name}</span>
                <span className="detail" title={step.detail}>
                  {step.detail}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {!signed && (study.repos ?? []).length > 0 ? (
        <details className="ese-detail-block">
          <summary className="context-note">人签命令（agent 不代签）</summary>
          <pre className="ese-command">{`# 1) claim（statement / human-reason 由人定稿）
python -m research_agent run claim \\
  --capsule ${base}/run/run-capsule.json \\
  --ea ${base}/run/ea.json \\
  --scope S5/${study.study_id} \\
  --evidence-source ese-exec \\
  --output-dir ${base}/claim

# 2) 结构闭合（只读）
python -m research_agent closure ese-check \\
  --capsule ${base}/run/run-capsule.json \\
  --ea ${base}/run/ea.json \\
  --claim ${base}/claim/claim.json \\
  --output-dir ${base}/closure

# 3) 最终签名（人签）
python -m research_agent closure ese-sign \\
  --report ${base}/closure/closure-report.json \\
  --capsule ${base}/run/run-capsule.json \\
  --ea ${base}/run/ea.json \\
  --claim ${base}/claim/claim.json \\
  --human-reason "..." \\
  --output-dir ${base}/signature`}</pre>
        </details>
      ) : null}

      {study.boundary ? <p className="ese-boundary">{study.boundary}</p> : null}
    </section>
  );
}

export function EseRunsPanel() {
  const [state, setState] = useState<LoadState>({ source: "none", runs: [] });
  const [history, setHistory] = useState<HistoryState>({ source: "none", entries: [] });
  const [studies, setStudies] = useState<EseStudy[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    load().then((next) => {
      if (!cancelled) setState(next);
    });
    loadHistory().then((next) => {
      if (!cancelled) setHistory(next);
    });
    loadStudies().then((next) => {
      if (cancelled) return;
      setStudies(next);
      if (next.length > 0) setSelectedId(next[0].study_id);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const selected = studies.find((study) => study.study_id === selectedId) ?? studies[0];

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
            {history.entries.map((entry) => {
              const match = studies.find((study) => study.study_id === entry.id);
              const active = Boolean(match && match.study_id === (selected?.study_id ?? ""));
              return (
                <li
                  key={entry.id}
                  className={`ese-history-entry${active ? " selected" : ""}`}
                  onClick={() => {
                    if (match) setSelectedId(match.study_id);
                  }}
                >
                  <div className="ese-history-meta">
                    <span>{entry.date ?? "—"}</span>
                    <span>{entry.stage ?? "—"}</span>
                    <code>{entry.id}</code>
                    {match ? (
                      <span className={match.state?.includes("SIGNED") ? "ese-state-ok" : "ese-state-todo"}>
                        {match.state?.includes("SIGNED") ? "signed" : "待签"}
                      </span>
                    ) : null}
                  </div>
                  <div className="ese-history-title">{entry.title ?? entry.id}</div>
                  {entry.question ? <p className="ese-history-question">{entry.question}</p> : null}
                  {entry.finding ? <p className="ese-history-finding">{entry.finding}</p> : null}
                  {entry.caveat ? <p className="ese-history-caveat">边界：{entry.caveat}</p> : null}
                  <div className="ese-history-foot">
                    <span>
                      {entry.method ?? ""}
                      {entry.data ? ` · ${entry.data}` : ""}
                    </span>
                    {entry.link ? <a href={entry.link}>来龙去脉 →</a> : null}
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        <p className="context-note">点击任一条展开详情；详情与 demo 页同源，都按盘上产物判定状态。</p>
      </section>

      {selected ? <StudyDetail study={selected} /> : null}

      <section className="context-section">
        <div className="context-section-head">
          <span>ESE RUNTIME SNAPSHOT</span>
          <span>{state.source === "runtime" ? "LOCAL RUNTIME" : state.source === "static" ? "STATIC SNAPSHOT" : "NO DATA"}</span>
        </div>
        {state.runs.length === 0 ? (
          <p className="context-note">
            {runtimeAvailable ? (
              <>
                本地 runtime 未运行且没有静态快照。运行 <code>python -m research_agent runtime serve</code> 后，
                这里会列出 runtime_data 里的 ESE 研究。
              </>
            ) : (
              <>静态演示构建：runtime 在构建时已禁用且没有 ESE 快照；真实运行结果请在本地 CLI 工作台查看。</>
            )}
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
