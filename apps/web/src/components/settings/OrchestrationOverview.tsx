import { useEffect, useMemo, useState } from "react";
import {
  loadLiteratureMemory,
  loadOrchestrationRun,
  loadOrchestrationTopology
} from "../../adapters/runtimeApi";
import type {
  LiteratureTopicMemory,
  OrchestrationRunSnapshot,
  SnapshotResult
} from "../../adapters/runtimeApi";
import { Card } from "./SettingsSections";
import { SourcePill } from "../SourcePill";
import { gateChainLabel } from "../../domain/rsiSemantics";

const FACET_ORDER = ["core", "survey", "method", "evaluation", "limitation", "recent"];
const FACET_LABELS: Record<string, string> = {
  core: "核心问题",
  survey: "综述",
  method: "方法",
  evaluation: "评测",
  limitation: "局限",
  recent: "近期"
};
const GAP_LABELS: Record<string, string> = {
  coverage_cap_reached: "预算耗尽",
  thin_domain_coverage: "面向不足",
  thin_full_text_coverage: "全文不足",
  full_text_unavailable: "摘要-only",
  no_source_hit: "无命中",
  no_full_text: "无全文",
  no_span: "无 span"
};

type SnapshotState<T> = {
  loading: boolean;
  result: SnapshotResult<T> | null;
  error: string;
};

function useSnapshotResource<T>(loader: () => Promise<SnapshotResult<T>>): SnapshotState<T> {
  const [state, setState] = useState<SnapshotState<T>>({ loading: true, result: null, error: "" });
  useEffect(() => {
    let cancelled = false;
    loader()
      .then((result) => {
        if (!cancelled) setState({ loading: false, result, error: "" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ loading: false, result: null, error: String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [loader]);
  return state;
}

function useStaticResource<T>(loader: () => Promise<T>) {
  const [state, setState] = useState<{ loading: boolean; data: T | null; error: string }>({
    loading: true,
    data: null,
    error: ""
  });
  useEffect(() => {
    let cancelled = false;
    loader()
      .then((data) => {
        if (!cancelled) setState({ loading: false, data, error: "" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ loading: false, data: null, error: String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, [loader]);
  return state;
}

function facetNames(facets: string[] | undefined): string {
  return (facets ?? []).map((facet) => FACET_LABELS[facet] ?? facet).join(" + ");
}

function ModeFacets({ topic }: { topic: LiteratureTopicMemory }) {
  const modeName = topic.modes.real ? "real" : Object.keys(topic.modes)[0] ?? "";
  const mode = topic.modes[modeName];
  if (!mode) return <p className="settings-empty">这条主题还没有模式统计。</p>;
  const facets = FACET_ORDER.filter((facet) => mode.facets[facet]).map((facet) => ({
    id: facet,
    label: FACET_LABELS[facet] ?? facet,
    ...mode.facets[facet]
  }));
  return (
    <>
      <div className="orchestration-memory-head">
        <div>
          <b>{topic.question}</b>
          <span>
            {modeName.toUpperCase()} · {mode.runs} runs · 累计 {mode.sources} sources · {mode.spans} spans
          </span>
        </div>
        <span className="settings-state" data-state={mode.gaps.coverage_cap_reached ? "needs_human" : "ok"}>
          {modeName === "real" ? "REAL" : "FIXTURE"}
        </span>
      </div>
      <div className="facet-grid">
        {facets.map((facet) => {
          const ratio = facet.attempts ? facet.covered_runs / facet.attempts : 0;
          return (
            <div className={`facet-cell${facet.covered_runs > 0 ? " is-covered" : ""}`} key={facet.id}>
              <div className="facet-cell-head">
                <span>{facet.label}</span>
                <b>{facet.covered_runs}/{facet.attempts || 0}</b>
              </div>
              <div className="facet-bar" aria-hidden="true">
                <i style={{ width: `${Math.round(ratio * 100)}%` }} />
              </div>
              <small>{facet.spans} spans · {facet.queries} queries</small>
            </div>
          );
        })}
      </div>
      {Object.keys(mode.gaps).length > 0 && (
        <div className="gap-chips">
          {Object.entries(mode.gaps)
            .sort((left, right) => right[1] - left[1])
            .map(([code, count]) => (
              <span className="gap-chip" key={code}>
                {GAP_LABELS[code] ?? code} ×{count}
              </span>
            ))}
        </div>
      )}
    </>
  );
}

function SkillCandidateCard({ candidate }: { candidate: OrchestrationRunSnapshot["skill_candidate"] }) {
  if (!candidate) {
    return (
      <div className="candidate-empty">
        <b>本轮不产生提案</b>
        <span>没有重复缺口，记忆只重排预算。达到阈值才生成 pending candidate；这是治理约束，不是失败。</span>
      </div>
    );
  }
  return (
    <div className="skill-candidate">
      <div className="skill-candidate-head">
        <b>{candidate.kind === "process" ? "PROCESS CANDIDATE" : "SKILL CANDIDATE"}</b>
        <span className="settings-state" data-state="needs_human">{candidate.status}</span>
      </div>
      <code>{candidate.target}</code>
      <p>{candidate.patch}</p>
      <small>{candidate.rationale}</small>
      <div className="candidate-governance">
        <span>{candidate.candidate_id}</span>
        <span>{candidate.scope}</span>
        <span>auto_admitted=false</span>
        <span>{gateChainLabel()}</span>
        <span>immutable: Claim · EA · gate</span>
      </div>
    </div>
  );
}

export function OrchestrationOverview() {
  const topology = useSnapshotResource(loadOrchestrationTopology);
  const memory = useSnapshotResource(loadLiteratureMemory);
  const run = useStaticResource(loadOrchestrationRun);

  const plan = topology.result?.data ?? null;
  const scouts = useMemo(
    () => (plan?.roles ?? []).filter((role) => role.mode === "fan-out"),
    [plan]
  );
  const gated = useMemo(
    () => (plan?.roles ?? []).filter((role) => role.mode === "gated"),
    [plan]
  );
  const customRoles = useMemo(
    () => (plan?.roles ?? []).filter((role) => role.mode === "custom-advisory"),
    [plan]
  );
  const rsi = (plan?.roles ?? []).find((role) => role.id === "rsi-governor");
  const topic = memory.result?.data.topics?.[0] ?? null;
  // A missing topology snapshot is not evidence for 3 scouts / 8 handoffs / 4 gates.
  // Show an explicit unknown instead of substituting plausible-looking numbers.
  const autoEvolve = plan ? Boolean(plan.evolution_policy?.enabled) : null;

  return (
    <div className="orchestration-overview">
      <Card
        title="协作拓扑"
        description="独立的检索面向并行侦察；合并证据视图后只跑一次假设收敛；人工门保持串行。"
      >
        <div className="orchestration-toolbar">
          <SourcePill source={topology.result?.source ?? null} />
          <span className="orchestration-metric">{plan ? scouts.length : "—"} SCOUTS · FAN-OUT</span>
          <span className="orchestration-metric">{plan ? customRoles.length : "—"} ADVISORY</span>
          <span className="orchestration-metric">{plan ? plan.handoffs.length : "—"} TYPED HANDOFFS</span>
          <span className="orchestration-metric">{plan ? plan.human_gates.length : "—"} HUMAN GATES</span>
          <span
            className="settings-state"
            data-state={autoEvolve === null ? "idle" : autoEvolve ? "active" : "needs_human"}
          >
            {autoEvolve === null
              ? "AUTO-EVOLVE UNKNOWN"
              : autoEvolve
                ? "AUTO-EVOLVE ON"
                : "AUTO-EVOLVE PAUSED"}
          </span>
        </div>
        {topology.loading && <p className="settings-empty">读取协作拓扑…</p>}
        {topology.error && <p className="settings-empty">拓扑读取失败：{topology.error}</p>}
        {plan && (
          <>
            <div
              className="orchestration-flow"
              role="img"
              aria-label="S1 文献扇出,汇入 S1 覆盖审计,再到 S2 至 S3 假设收敛,最后停在人工门 G1;候选不自动通过,门后流程见 RSI 面板"
            >
              <div className="orchestration-stage is-fanout">
                <small>S1 · FAN-OUT</small>
                <b>文献侦察 · {scouts.length} 路</b>
                <div className="orchestration-scouts">
                  {scouts.map((scout) => (
                    <div className="orchestration-scout" key={scout.id}>
                      <b>{scout.name.replace("文献侦察 · ", "")}</b>
                      <span>{facetNames(scout.facets)}</span>
                      <em>{scout.budget ?? "—"} src · {scout.id}</em>
                    </div>
                  ))}
                </div>
              </div>
              <div className="orchestration-arrow" aria-hidden="true">→</div>
              <div className="orchestration-stage is-fanin">
                <small>S1 · FAN-IN</small>
                <b>覆盖审计</b>
                <span>source_id / span_id 去重</span>
                <span>facet 覆盖取并集</span>
              </div>
              <div className="orchestration-arrow" aria-hidden="true">→</div>
              <div className="orchestration-stage is-idea">
                <small>S2–S3</small>
                <b>假设收敛</b>
                <span>只在合并 span 上跑一次</span>
                <span>候选帧 · novelty 未核验</span>
              </div>
              <div className="orchestration-arrow is-gate" aria-hidden="true">→</div>
              <div className="orchestration-stage is-gate">
                <small>HUMAN GATE</small>
                <b>G1</b>
                <span>候选不自动通过</span>
                <span>SSE 不提供签核</span>
              </div>
            </div>
            <div className="orchestration-gated">
              {customRoles.map((role) => (
                <span className="orchestration-gate-chip is-advisory" key={role.id} title={(role.outputs ?? []).join(" / ")}>
                  {role.name} · {(role.check_labels ?? role.checks ?? []).join(" + ")} · {role.executes ? "active" : "deferred"}
                </span>
              ))}
              {gated.map((role) => (
                <span className="orchestration-gate-chip" key={role.id}>
                  {role.stage} · {role.name}
                  {role.gates?.length ? ` · ${role.gates.join("/")}` : ""}
                </span>
              ))}
              {rsi && (
                <span className="orchestration-gate-chip is-rsi" title={rsi.note}>
                  META · RSI 治理独立车道
                </span>
              )}
            </div>
            <p className="settings-note">
              {plan.boundary} 当前预算按面向分配；记忆只改变下一轮顺序与预算，不把过程量当证据。
            </p>
          </>
        )}
      </Card>

      <div className="orchestration-grid">
        <Card
          title="文献记忆感知"
          description="只记过程量：面向覆盖、query yield、缺口与饱和度；不保存摘要或 span 文本。"
        >
          {memory.loading && <p className="settings-empty">读取文献记忆…</p>}
          {memory.error && <p className="settings-empty">记忆读取失败：{memory.error}</p>}
          {topic ? <ModeFacets topic={topic} /> : null}
          {!memory.loading && !memory.error && !topic && (
            <p className="settings-empty">还没有过程记忆。运行一次 S1 scout fan-out 后才会出现覆盖/产出统计。</p>
          )}
          {run.data?.memory.next_focus?.length ? (
            <div className="orchestration-next">
              <b>下一轮预算参考</b>
              {run.data.memory.next_focus.map((item) => (
                <span key={item.facet}>
                  {FACET_LABELS[item.facet] ?? item.facet} · {item.reason}
                </span>
              ))}
            </div>
          ) : null}
          <p className="settings-note">{memory.result?.data.boundary ?? "process memory only; never evidence"}</p>
        </Card>

        <Card
          title="自进化提案"
          description="记忆派生的候选永远停在人工门前：可以提议 query/budget 改动，不能改写证据与门禁。"
        >
          {run.loading && <p className="settings-empty">读取最近一次 fan-out…</p>}
          {run.error && <p className="settings-empty">运行快照读取失败：{run.error}</p>}
          {run.data && (
            <>
              <SkillCandidateCard candidate={run.data.skill_candidate} />
              <div className="orchestration-next is-compact">
                <b>候选路径</b>
                <span>facet 重复覆盖不足 → literature.query_planner skill candidate；</span>
                <span>预算/全文持续受限 → orchestrator.facet_budget process candidate。</span>
              </div>
              <div className="orchestration-next is-compact">
                <b>为什么不是自动进化</b>
                <span>候选只进入 dry-run / public / hidden / regression / human admission；</span>
                <span>Claim、EA、gate、rubric、export、signature 全部不可变。</span>
              </div>
            </>
          )}
        </Card>
      </div>

      <Card
        title="最近一次 scout fan-out"
        description="真实 CC-BY 语料；只展示计数、面向覆盖与候选帧，不展示 source/span 文本。"
      >
        {run.loading && <p className="settings-empty">读取运行摘要…</p>}
        {run.error && <p className="settings-empty">运行摘要读取失败：{run.error}</p>}
        {run.data && (
          <>
            <div className="orchestration-run-head">
              <code>{run.data.run_id}</code>
              <span className="settings-state" data-state={run.data.fixture_mode ? "draft" : "ok"}>
                {run.data.fixture_mode ? "FIXTURE" : "REAL"}
              </span>
              <span className="settings-state" data-state="needs_human">STOPPED BEFORE G1</span>
              <span className="orchestration-run-topic">{run.data.topic}</span>
            </div>
            <div className="orchestration-stats">
              <div><b>{run.data.merged.sources}</b><span>sources</span></div>
              <div><b>{run.data.merged.full_text}</b><span>full text</span></div>
              <div><b>{run.data.merged.spans_count}</b><span>spans</span></div>
              <div><b>{run.data.merged.covered_facets}/{run.data.merged.planned_facets}</b><span>facets</span></div>
              <div><b>{Math.round(run.data.merged.coverage_score * 100)}%</b><span>coverage</span></div>
            </div>
            <div className="orchestration-run-scouts">
              {run.data.scouts.map((scout) => (
                <div className="orchestration-run-scout" key={scout.role_id}>
                  <span>{facetNames(scout.facets)}</span>
                  <b>{scout.sources} src · {scout.spans} spans</b>
                  <em>{scout.saturation} · {scout.status}</em>
                </div>
              ))}
            </div>
            {run.data.merged.gaps.length > 0 && (
              <div className="gap-chips">
                {run.data.merged.gaps.map((gap) => (
                  <span className="gap-chip" key={gap.code}>{GAP_LABELS[gap.code] ?? gap.code}</span>
                ))}
              </div>
            )}
            {(run.data.advisory_notes ?? []).length > 0 && (
              <div className="orchestration-advisories">
                <div className="orchestration-idea-head">
                  <b>自定义子智能体 advisory</b>
                  <span>只读检查 · 不是 Claim/门禁</span>
                </div>
                {(run.data.advisory_notes ?? []).map((note) => (
                  <div className="orchestration-advisory-row" data-status={note.status} key={note.id}>
                    <b>{note.agent_name} · {note.check_label}</b>
                    <span>{note.summary}</span>
                    <em>{note.status}</em>
                  </div>
                ))}
              </div>
            )}
            <div className="orchestration-idea">
              <div className="orchestration-idea-head">
                <b>{run.data.idea.candidates.length} 个候选帧</b>
                <span>{run.data.idea.status} · G1 未通过 · novelty unverified</span>
              </div>
              {run.data.idea.candidates.slice(0, 2).map((candidate) => (
                <div className="orchestration-idea-row" key={candidate.idea_id}>
                  <b>{candidate.title}</b>
                  <span>
                    {candidate.evidence_count} refs / {candidate.source_count} sources · {candidate.lens}
                    {candidate.prior_art_scope ? ` · prior-art ${candidate.prior_art_scope}` : ""}
                    {candidate.contrast_refs?.length ? " · A/B contrast" : ""}
                  </span>
                </div>
              ))}
              {run.data.idea.shortlist && run.data.idea.shortlist.ranked.length > 0 && (
                <div className="orchestration-shortlist">
                  <div className="orchestration-idea-head">
                    <b>Advisory shortlist</b>
                    <span>{run.data.idea.shortlist.selection} · 不自动选 · novelty unverified</span>
                  </div>
                  {run.data.idea.shortlist.ranked.slice(0, 3).map((item) => (
                    <div className="orchestration-idea-row" key={item.idea_id}>
                      <b>#{item.rank} {item.idea_id}</b>
                      <span>
                        {item.evidence_count} refs / {item.source_count} sources · {item.prior_art_scope}
                        {item.has_contrast ? " · contrast" : ""}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <p className="settings-note">{run.data.boundary}</p>
          </>
        )}
      </Card>
    </div>
  );
}
