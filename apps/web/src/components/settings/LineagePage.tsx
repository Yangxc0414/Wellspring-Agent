import { useEffect, useMemo, useState } from "react";
import { Icon } from "../Icon";
import { snapshotDateLabel } from "../../domain/rsiSemantics";
import { LineageDag } from "./LineageDag";

interface LineageNode {
  id: string;
  kind: string;
  label: string;
  hash: string;
  shortHash: string;
  dependencies: string[];
  stage: string;
  stageLabel: string;
  metadata: Record<string, string | number | boolean | null>;
}

interface ChangeSummary {
  status: string;
  changed: unknown[];
  staleNodeIds: string[];
  staleClaims?: string[];
  staleSlots?: string[];
  staleFigures?: string[];
  exportAllowed: boolean;
  requiresReclosure?: boolean;
  requiresResign?: boolean;
  actionCounts?: Record<string, number>;
  nextSteps?: string[];
}

interface LineageSnapshot {
  source: string;
  generatedAt: string;
  manifestId: string;
  bundleStatus: string;
  summary: {
    nodes: number;
    claims: number;
    slots: number;
    closureChecks: number;
    closureStatus: string;
    claimId: string;
    claimStatement: string;
    signatureId: string;
    submission: boolean;
  };
  generated_at?: string;
  nodes: LineageNode[];
  clean: ChangeSummary;
  simulatedChange: ChangeSummary & {
    label: string;
    beforeDatasetHash: string;
    afterDatasetHash: string;
    changedNodeIds: string[];
    staleClaims: string[];
    staleSlots: string[];
    staleFigures: string[];
    requiresReclosure: boolean;
    requiresResign: boolean;
  };
}

const STAGES = ["sources", "run", "freeze", "evidence", "claim", "slots", "paper", "closure", "signature"];

const KIND_LABEL: Record<string, string> = {
  dataset: "DATASET",
  code: "CODE",
  bib: "BIBLIOGRAPHY",
  bibliography: "BIBLIOGRAPHY",
  run: "RUN",
  protocol: "PROTOCOL",
  evidence: "EA",
  figure: "FIGURE",
  claim: "CLAIM",
  paper_slot: "SLOT",
  paper: "PAPER",
  closure: "CLOSURE",
  signature: "SIGNATURE",
  export_manifest: "EXPORT"
};

export function LineagePage() {
  const [data, setData] = useState<LineageSnapshot | null>(null);
  const [error, setError] = useState("");
  const [simulated, setSimulated] = useState(false);
  const [selectedId, setSelectedId] = useState("");

  useEffect(() => {
    let active = true;
    fetch(new URL("./lineage-demo.json", document.baseURI).toString())
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<LineageSnapshot>;
      })
      .then((snapshot) => {
        if (!active) return;
        setData(snapshot);
        const closure = snapshot.nodes.find((node) => node.kind === "closure");
        setSelectedId(closure?.id ?? snapshot.nodes[0]?.id ?? "");
      })
      .catch(() => {
        if (active) setError("找不到 lineage 快照；请先运行 lineage build 并重新构建前端。");
      });
    return () => {
      active = false;
    };
  }, []);

  const changedSet = useMemo(
    () => new Set(simulated ? data?.simulatedChange.changedNodeIds ?? [] : []),
    [data, simulated]
  );
  const staleSet = useMemo(
    () => new Set(simulated ? data?.simulatedChange.staleNodeIds ?? [] : []),
    [data, simulated]
  );
  const groups = useMemo(
    () => STAGES.map((stage) => ({
      stage,
      label: data?.nodes.find((node) => node.stage === stage)?.stageLabel ?? stage.toUpperCase(),
      nodes: data?.nodes.filter((node) => node.stage === stage) ?? []
    })).filter((group) => group.nodes.length > 0),
    [data]
  );
  const selected = data?.nodes.find((node) => node.id === selectedId) ?? data?.nodes[0];
  const dependents = data?.nodes.filter((node) => selected && node.dependencies.includes(selected.id)) ?? [];

  const toggleSimulation = () => {
    if (!data) return;
    const next = !simulated;
    setSimulated(next);
    const focus = next
      ? data.simulatedChange.staleNodeIds.find((id) => {
          const node = data.nodes.find((item) => item.id === id);
          return node?.kind === "claim";
        }) ?? data.simulatedChange.staleNodeIds[0]
      : data.nodes.find((node) => node.kind === "closure")?.id;
    if (focus) setSelectedId(focus);
  };

  if (error) {
    return (
      <div className="settings-section-body">
        <div className="settings-page-head">
          <div>
            <span className="eyebrow">DATA & STATISTICS / LINEAGE</span>
            <div className="settings-heading-line"><h1>证据沿袭</h1><span className="settings-tag">变更影响</span></div>
            <p>从数据/代码到签署产物的依赖闭包。</p>
          </div>
        </div>
        <div className="settings-empty-card">
          <Icon name="branch" size={22} />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="settings-section-body">
        <div className="settings-page-head">
          <div>
            <span className="eyebrow">DATA & STATISTICS / LINEAGE</span>
            <div className="settings-heading-line"><h1>证据沿袭</h1><span className="settings-tag">加载中</span></div>
            <p>读取 closed-loop 快照与依赖图…</p>
          </div>
        </div>
        <div className="settings-empty">LOADING LINEAGE SNAPSHOT…</div>
      </div>
    );
  }

  const current = simulated ? data.simulatedChange : data.clean;
  const staleCount = current.staleNodeIds.length;

  return (
    <div className="settings-section-body lineage-page">
      <div className="settings-page-head">
        <div>
          <span className="eyebrow">DATA & STATISTICS / LINEAGE</span>
          <div className="settings-heading-line">
            <h1>证据沿袭</h1>
            <span className="settings-tag">变更影响</span>
          </div>
          <p>从数据、代码、run、EA、claim 到稿件槽位、closure 和 signature 的内容寻址依赖图。变更不会静默通过。</p>
        </div>
      </div>

      <div className="lineage-summary">
        <div><b>{data.summary.nodes}</b><span>节点</span></div>
        <div><b>{data.summary.closureChecks}</b><span>closure checks</span></div>
        <div><b>{data.summary.claims}</b><span>claim</span></div>
        <div><b>{simulated ? "BLOCKED" : "SIGNED"}</b><span>export</span></div>
      </div>

      <div className="lineage-toolbar">
        <div className="lineage-snapshot">
          <span className={`lineage-state ${simulated ? "is-stale" : "is-clean"}`}>
            <i />
            {simulated ? "STALE PROPAGATION" : "CLEAN SNAPSHOT"}
          </span>
          <span>{data.source} · {data.summary.claimId} · {data.summary.signatureId}</span>
          <span>{snapshotDateLabel(data.generatedAt ?? data.generated_at)}</span>
        </div>
        <button type="button" aria-pressed={simulated} className={`settings-btn ${simulated ? "primary" : ""}`} onClick={toggleSimulation}>
          {simulated ? "恢复闭合快照" : "模拟数据集变更"}
        </button>
      </div>

      {simulated && (
        <div className="lineage-alert" role="status">
          <Icon name="alert" size={16} />
          <div>
            <b>导出锁定 · {staleCount} 个下游节点失效</b>
            <p>
              数据集哈希 {data.simulatedChange.beforeDatasetHash.slice(0, 10)}… → {data.simulatedChange.afterDatasetHash.slice(0, 10)}…；
              {current.staleClaims?.length ?? 0} 个 claim、{current.staleSlots?.length ?? 0} 个稿件槽位、{current.staleFigures?.length ?? 0} 个结果图需要重新验证。
              closure 和 signature 不能继续复用。
            </p>
          </div>
          <span className="lineage-blocked">EXPORT BLOCKED</span>
        </div>
      )}

      <LineageDag
        groups={groups}
        selectedId={selected?.id ?? ""}
        staleIds={staleSet}
        changedIds={changedSet}
        onSelect={setSelectedId}
      />

      <div className="lineage-layout">
        <div className="lineage-flow">
          {groups.map((group, groupIndex) => (
            <section className="lineage-stage" key={group.stage}>
              <div className="lineage-rail" aria-hidden="true">
                <span>{String(groupIndex + 1).padStart(2, "0")}</span>
                {groupIndex < groups.length - 1 && <i />}
              </div>
              <div className="lineage-stage-body">
                <div className="lineage-stage-head">
                  <span>{group.label}</span>
                  <em>{group.nodes.length} nodes</em>
                </div>
                <div className="lineage-node-grid">
                  {group.nodes.map((node) => {
                    const changed = changedSet.has(node.id);
                    const stale = staleSet.has(node.id);
                    return (
                      <button
                        type="button"
                        key={node.id}
                        className={`lineage-node${stale ? " is-stale" : ""}${changed ? " is-changed" : ""}${selected?.id === node.id ? " is-selected" : ""}`}
                        onClick={() => setSelectedId(node.id)}
                      >
                        <span className="lineage-node-top">
                          <span>{KIND_LABEL[node.kind] ?? node.kind.toUpperCase()}</span>
                          <em>{changed ? "CHANGED" : stale ? "STALE" : "OK"}</em>
                        </span>
                        <b title={node.label}>{node.label}</b>
                        <code>{node.shortHash}</code>
                      </button>
                    );
                  })}
                </div>
              </div>
            </section>
          ))}
        </div>

        <aside className="lineage-inspector">
          <div className="settings-card">
            <div className="settings-card-head">
              <div>
                <h2>节点详情</h2>
                <p>{selected ? KIND_LABEL[selected.kind] ?? selected.kind : "—"}</p>
              </div>
              {selected && (
                <span className={`badge ${changedSet.has(selected.id) ? "bad" : staleSet.has(selected.id) ? "warn" : "ok"}`}>
                  {changedSet.has(selected.id) ? "changed" : staleSet.has(selected.id) ? "stale" : "ok"}
                </span>
              )}
            </div>
            {selected ? (
              <>
                <p className="lineage-node-label">{selected.label}</p>
                <div className="lineage-hash-row">
                  <span>SHA256</span>
                  <code>{selected.hash}</code>
                </div>
                {Object.keys(selected.metadata).length > 0 && (
                  <div className="lineage-deps-block">
                    <span>METADATA</span>
                    <div className="lineage-meta-list">
                      {Object.entries(selected.metadata).map(([key, value]) => (
                        <div className="lineage-meta-row" key={key}>
                          <span>{key}</span>
                          <code>{value === null ? "—" : String(value)}</code>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="lineage-deps-block">
                  <span>UPSTREAM</span>
                  <div className="lineage-dep-list">
                    {selected.dependencies.length ? selected.dependencies.map((id) => {
                      const dep = data.nodes.find((node) => node.id === id);
                      return (
                        <button type="button" key={id} onClick={() => setSelectedId(id)} className={staleSet.has(id) ? "is-stale" : ""}>
                          {dep ? `${KIND_LABEL[dep.kind] ?? dep.kind} · ${dep.label}` : id}
                        </button>
                      );
                    }) : <em>root node</em>}
                  </div>
                </div>
                <div className="lineage-deps-block">
                  <span>DOWNSTREAM</span>
                  <div className="lineage-dep-list">
                    {dependents.length ? dependents.map((node) => (
                      <button type="button" key={node.id} onClick={() => setSelectedId(node.id)} className={staleSet.has(node.id) ? "is-stale" : ""}>
                        {KIND_LABEL[node.kind] ?? node.kind} · {node.label}
                      </button>
                    )) : <em>leaf node</em>}
                  </div>
                </div>
              </>
            ) : null}
          </div>

          <div className="settings-card lineage-actions-card">
            <div className="settings-card-head">
              <div>
                <h2>处置顺序</h2>
                <p>这是一个静态预览；真实重跑/重签走 CLI。</p>
              </div>
            </div>
            {simulated && data.simulatedChange.actionCounts && (
              <div className="lineage-action-counts">
                {(["rerun", "rewrite", "recheck"] as const).map((action) => (
                  <span key={action} className={`is-${action}`}>
                    <b>{data.simulatedChange.actionCounts?.[action] ?? 0}</b>
                    {action}
                  </span>
                ))}
              </div>
            )}
            <p className="settings-note">
              {simulated
                ? "模拟变更已触发：以下为需要执行的处置，均未执行。"
                : "当前快照已闭合：以下为真实重跑时的处置顺序，本预览未执行任何一步（含人签）。"}
            </p>
            <ol className="lineage-action-list">
              <li>用新数据重跑 S5 run</li>
              <li>重新封存 EA 与 claim</li>
              <li>重绑 figure / paper slots</li>
              <li>重跑 11 项 closure</li>
              <li>人签新 signature</li>
            </ol>
            <p className="settings-note">
              闭合快照：{data.summary.closureStatus} · {data.summary.closureChecks} checks · submission={String(data.summary.submission)}
              {simulated && " · 处置由 lineage impact 生成，本页不执行"}
            </p>
          </div>

          <p className="settings-inline-note">
            `lineage impact --fail-on-stale` 返回非零时，CI 和签署流程必须停止。此页只展示真实快照 + 本地 stale 模拟，不执行重跑或签名。
          </p>
        </aside>
      </div>
    </div>
  );
}
