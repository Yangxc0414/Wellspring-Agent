import { useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "../Icon";
import { snapshotDateLabel } from "../../domain/rsiSemantics";
import {
  LINEAGE_KINDS,
  lineageActionLabel,
  lineageKind,
  lineageMetaLabel,
  lineageStage
} from "../../domain/lineageLabels";
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

/** English tags are kept for readers comparing against CLI output; the Chinese names
 *  and explanations live in domain/lineageLabels.ts so every surface agrees. */
const KIND_LABEL: Record<string, string> = Object.fromEntries(
  Object.entries(LINEAGE_KINDS).map(([kind, label]) => [kind, label.en])
);

type CopyState = "idle" | "copied" | "failed";

/** A sha256 is unreadable at full length; keep it short by default, copyable in
 *  one click, and fully visible when the clipboard is unavailable. */
function CopyHash({ value }: { value: string }) {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef(0);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = async () => {
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("failed");
    }
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 1600);
  };

  return (
    <button type="button" className="lineage-hash-copy" onClick={() => void copy()} title="复制完整 SHA256">
      <code title={value}>{state === "failed" ? value : `${value.slice(0, 12)}…${value.slice(-8)}`}</code>
      <span>{state === "copied" ? "已复制" : state === "failed" ? "请手动选中" : "复制"}</span>
      <Icon name={state === "copied" ? "check" : "copy"} size={11} />
    </button>
  );
}

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
        <div className="settings-empty">正在读取 lineage 快照与依赖图…</div>
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

      <section className="lineage-guide" aria-label="这一页在讲什么、怎么用">
        <div className="lineage-guide-head">
          <span className="lineage-guide-icon"><Icon name="branch" size={17} /></span>
          <div>
            <b>这一页在讲什么</b>
            <p>
              把「数据 → 运行 → 证据 → 人工签署的 claim → 稿件 → 导出」这条链上的每个产物，按内容哈希连成一张图。
              上游一旦变化，依赖它的下游全部标为失效，导出会被锁住——这就是「变更不会静默通过」。
            </p>
          </div>
          <span className="lineage-readonly"><Icon name="lock" size={11} />只读预览 · 不执行任何操作</span>
        </div>
        <ol className="lineage-guide-steps">
          <li>
            <b>① 先看整体状态</b>
            <span>顶部「快照已闭合」表示当前产物一致；点「模拟数据集变更」只做本地推演，不会改动真实文件。</span>
          </li>
          <li>
            <b>② 点任意节点</b>
            <span>中间卡片或上方依赖图的方块都能点；右侧会显示它的哈希、依赖了什么、以及谁依赖它。</span>
          </li>
          <li>
            <b>③ 顺着颜色看影响</b>
            <span>红 / 琥珀 = 上游已变需复核，蓝色 = 变化源头。真正的重跑、closure 与人签仍要在本地 CLI 完成。</span>
          </li>
        </ol>
      </section>

      <div className="lineage-legend" aria-label="图例">
        <span><i className="is-ok" />OK · 校验通过</span>
        <span><i className="is-stale" />STALE · 上游已变，需复核</span>
        <span><i className="is-changed" />CHANGED · 本次变化的源头</span>
        <span><i className="is-edge" />箭头 = 上游 → 下游（影响传播方向）</span>
        <span><b>N 个产物</b> = 该阶段包含的节点数</span>
      </div>

      <div className="lineage-summary" aria-label="快照概览">
        <div title="依赖图里的产物总数"><b>{data.summary.nodes}</b><span>产物节点</span></div>
        <div title="导出前必须全部通过的一致性检查"><b>{data.summary.closureChecks}</b><span>闭合检查项</span></div>
        <div title="人工签署的研究主张数量"><b>{data.summary.claims}</b><span>研究主张 claim</span></div>
        <div title="上游失效时导出被锁；签名只在 CLI 产生"><b>{simulated ? "已锁定" : "已签署"}</b><span>导出状态</span></div>
      </div>

      <div className="lineage-toolbar">
        <div className="lineage-snapshot">
          <span className={`lineage-state ${simulated ? "is-stale" : "is-clean"}`} title={simulated ? "本地推演：上游变更已沿依赖图传播" : "所有产物哈希一致，闭合检查通过"}>
            <i />
            {simulated ? "失效传播中（模拟）" : "快照已闭合"}
          </span>
          <span>来源：{data.source} · 主张 {data.summary.claimId} · 签署 {data.summary.signatureId}</span>
          <span>快照时间 {snapshotDateLabel(data.generatedAt ?? data.generated_at)}</span>
        </div>
        <button
          type="button"
          aria-pressed={simulated}
          className={`settings-btn ${simulated ? "primary" : ""}`}
          onClick={toggleSimulation}
          title="只在本页推演失效传播，不改动文件、不执行重跑或签署"
        >
          {simulated ? "恢复闭合快照" : "模拟数据集变更（只读推演）"}
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
          <span className="lineage-blocked">导出已锁定</span>
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
                  <div className="lineage-stage-title">
                    <b>{lineageStage(group.stage).zh}</b>
                    <span>{group.label}</span>
                    <small>{lineageStage(group.stage).hint}</small>
                  </div>
                  <em>{group.nodes.length} 个产物</em>
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
                          <span
                            className="lineage-node-kind"
                            title={`${KIND_LABEL[node.kind] ?? node.kind.toUpperCase()} · ${lineageKind(node.kind).desc}`}
                          >
                            {lineageKind(node.kind).zh}
                            <small>{KIND_LABEL[node.kind] ?? node.kind.toUpperCase()}</small>
                          </span>
                          <em>{changed ? "已变更" : stale ? "需复核" : "通过"}</em>
                        </span>
                        <b title={node.label}>{node.label}</b>
                        <code title={`内容哈希 ${node.hash}`}>sha:{node.shortHash}</code>
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
                <p>{selected ? `${lineageKind(selected.kind).zh} · ${KIND_LABEL[selected.kind] ?? selected.kind.toUpperCase()}` : "点左侧任意节点查看"}</p>
              </div>
              {selected && (
                <span
                  className={`badge ${changedSet.has(selected.id) ? "bad" : staleSet.has(selected.id) ? "warn" : "ok"}`}
                  title="该节点当前的校验状态"
                >
                  {changedSet.has(selected.id) ? "已变更" : staleSet.has(selected.id) ? "需复核" : "通过"}
                </span>
              )}
            </div>
            {selected ? (
              <>
                <div className="lineage-block-intro">
                  <span>产物标识</span>
                  <p>{selected.label}</p>
                  <small>{lineageKind(selected.kind).desc}</small>
                </div>
                <div className="lineage-hash-row">
                  <div className="lineage-deps-head">
                    <span>内容哈希 SHA256</span>
                    <small>内容变一个字节，哈希就变，下游随之失效</small>
                  </div>
                  <CopyHash value={selected.hash} />
                </div>
                {Object.keys(selected.metadata).length > 0 && (
                  <div className="lineage-deps-block">
                    <div className="lineage-deps-head">
                      <span>元数据</span>
                      <small>这个产物自带的属性</small>
                    </div>
                    <div className="lineage-meta-list">
                      {Object.entries(selected.metadata).map(([key, value]) => (
                        <div className="lineage-meta-row" key={key}>
                          <span title={key}>{lineageMetaLabel(key)}</span>
                          <code>{value === null ? "—" : String(value)}</code>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <div className="lineage-deps-block">
                  <div className="lineage-deps-head">
                    <span>上游依赖 {selected.dependencies.length ? `(${selected.dependencies.length})` : ""}</span>
                    <small>这个节点引用了什么 · 点条目可跳过去查看</small>
                  </div>
                  <div className="lineage-dep-list">
                    {selected.dependencies.length ? selected.dependencies.map((id) => {
                      const dep = data.nodes.find((node) => node.id === id);
                      return (
                        <button type="button" key={id} onClick={() => setSelectedId(id)} className={staleSet.has(id) ? "is-stale" : ""}>
                          {dep ? `${lineageKind(dep.kind).zh} · ${dep.label}` : id}
                        </button>
                      );
                    }) : <em>根节点：没有上游，哈希由自身内容决定</em>}
                  </div>
                </div>
                <div className="lineage-deps-block">
                  <div className="lineage-deps-head">
                    <span>下游影响 {dependents.length ? `(${dependents.length})` : ""}</span>
                    <small>谁引用了这个节点 · 它一变，这些都会失效</small>
                  </div>
                  <div className="lineage-dep-list">
                    {dependents.length ? dependents.map((node) => (
                      <button type="button" key={node.id} onClick={() => setSelectedId(node.id)} className={staleSet.has(node.id) ? "is-stale" : ""}>
                        {lineageKind(node.kind).zh} · {node.label}
                      </button>
                    )) : <em>叶子节点：没有下游产物</em>}
                  </div>
                </div>
              </>
            ) : null}
          </div>

          <div className="settings-card lineage-actions-card">
            <div className="settings-card-head">
              <div>
                <h2>处置顺序</h2>
                <p>上游变化后，真实重跑要按什么顺序做</p>
              </div>
            </div>
            <div className="lineage-warning" role="note">
              <Icon name="lock" size={12} />
              <span>
                本页只读：下面 5 步是「如果上游变了该怎么做」，<b>一步都没有执行，也不会代人签</b>。重跑 / closure / 签署都在本地 CLI。
              </span>
            </div>
            {simulated && data.simulatedChange.actionCounts && (
              <div className="lineage-action-counts">
                {(["rerun", "rewrite", "recheck"] as const).map((action) => (
                  <span key={action} className={`is-${action}`} title={`${lineageActionLabel(action)}的产物数量`}>
                    <b>{data.simulatedChange.actionCounts?.[action] ?? 0}</b>
                    {lineageActionLabel(action)}
                  </span>
                ))}
              </div>
            )}
            <p className="settings-note">
              {simulated
                ? "模拟变更已触发：上面是受影响的数量，下面是需要执行的处置；均未执行。"
                : "当前快照已闭合：以下是真实重跑时的顺序，本预览未执行任何一步（含人签）。"}
            </p>
            <ol className="lineage-action-list">
              <li><span><b>重跑 S5 run</b> · 用新数据重新执行，生成新的 RunCapsule</span></li>
              <li><span><b>重新封存 EA 与 claim</b> · 旧结论失效，需重新核对数值后由人签署</span></li>
              <li><span><b>重绑结果图与稿件槽位</b> · 图与段落必须指向新的证据产物</span></li>
              <li><span><b>重跑 {data.summary.closureChecks} 项闭合检查</b> · 检查引用、来源与覆盖是否仍然一致</span></li>
              <li><span><b>人签新的 signature</b> · 只有 CLI 的 closure sign 能产生导出签名</span></li>
            </ol>
            <p className="settings-note">
              闭合快照：状态 {data.summary.closureStatus} · {data.summary.closureChecks} 项检查 · 可投稿={data.summary.submission ? "是" : "否"}
              {simulated && " · 处置清单由 lineage impact 生成，本页不执行"}
            </p>
          </div>

          <p className="settings-inline-note">
            <code>lineage impact --fail-on-stale</code> 返回非零时，CI 与签署流程必须停止。此页只展示真实快照与本地失效推演，不执行重跑、closure 或签名。
          </p>
        </aside>
      </div>
    </div>
  );
}
