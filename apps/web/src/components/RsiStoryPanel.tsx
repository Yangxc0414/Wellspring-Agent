import { useEffect, useState } from "react";
import { fetchRsiStory } from "../adapters/runtimeApi";
import type { RsiEpisodeStory, RsiStory } from "../adapters/runtimeApi";
import type { SnapshotResult } from "../adapters/runtimeApi";
import { Icon } from "./Icon";
import { snapshotDateLabel, tone, verdictTone } from "../domain/rsiSemantics";

function formatNumber(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) return "—";
  return Math.abs(value) >= 100 ? value.toFixed(1) : value.toFixed(3);
}

function gate(episode: RsiEpisodeStory, id: string) {
  return episode.gates.find((item) => item.id === id);
}

function GateRow({ episode, id }: { episode: RsiEpisodeStory; id: string }) {
  const item = gate(episode, id);
  if (!item) return null;
  const mean = item.metrics?.mean_score ?? item.metrics?.mean_r2;
  const cost = item.metrics?.cost;
  return (
    <div className="rsi-gate">
      <span className={`rsi-state ${tone(item.state)}`}>{item.state}</span>
      <b>{item.label}</b>
      <span>{mean !== undefined ? `mean ${formatNumber(mean)} · ` : ""}{cost !== undefined ? `cost ${formatNumber(cost)}` : ""}</span>
    </div>
  );
}

export function RsiStoryPanel() {
  const [state, setState] = useState<{
    result: SnapshotResult<RsiStory> | null;
    error: string;
  }>({ result: null, error: "" });

  useEffect(() => {
    let cancelled = false;
    fetchRsiStory()
      .then((result) => {
        if (!cancelled) setState({ result, error: "" });
      })
      .catch((error: unknown) => {
        if (!cancelled) setState({ result: null, error: String(error) });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (state.error || !state.result) {
    return (
      <section className="context-card">
        <div className="card-label"><span>RSI STORY</span><em>UNAVAILABLE</em></div>
        <p className="rsi-headline">没有可用 RSI 账本。启动本地 runtime 或检查 `apps/web/public/rsi-story.json`。</p>
      </section>
    );
  }

  const story = state.result.data;
  const selected = story.episodes.find((item) => item.episode_id === story.selected_episode_id) ?? story.episodes[0];
  const rejected = story.episodes.filter((item) => item.decision === "rejected");
  const trackingKeys = Object.keys(story.tracking.metrics).slice(0, 3);

  return (
    <div className="rsi-story">
      <section className="context-card rsi-story-card">
        <div className="card-label">
          <span>RSI STORY</span>
          <em>{state.result.source === "runtime" ? "LIVE LEDGER" : "SEALED SNAPSHOT"}</em>
        </div>
        <p className="rsi-headline">{story.summary.headline}</p>
        {selected && (
          <div className="rsi-lane"><Icon name="branch" size={10} />独立证据臂 · {selected.scope} · 与当前任务的演示候选分开</div>
        )}
        <div className="rsi-kpis">
          <span><b>{story.summary.episodes}</b>EPISODES</span>
          <span><b>{story.summary.approved}</b>APPROVED</span>
          <span><b>{story.summary.rejected}</b>REJECTED</span>
          <span><b>{story.summary.active_leases}</b>LEASES</span>
          <span><b>{story.summary.confirmed}</b>CONFIRMED</span>
          <span><b>{story.summary.capability_claims}</b>CLAIMS</span>
        </div>
        {story.ledger_path && <code className="rsi-ledger-path">{story.ledger_path}</code>}
        <div className="rsi-verdict">
          <span className={`rsi-state ${verdictTone(story.summary.gate_verdict)}`}>
            {story.summary.gate_verdict ?? "verdict 未记录"}
          </span>
          <span>
            decided {story.summary.decided ?? "—"} · rejection{" "}
            {story.summary.rejection_rate == null ? "—" : story.summary.rejection_rate}
          </span>
          {(story.provenance?.simulation_episodes ?? story.summary.simulation_episodes ?? 0) > 0 && (
            <span className="rsi-state warn">
              含 {story.provenance?.simulation_episodes ?? story.summary.simulation_episodes} 条演练
              episode · 非真实改进证据
            </span>
          )}
          <span>{snapshotDateLabel(story.generated_at)}</span>
        </div>
      </section>

      {selected && (
        <>
          <section className="context-section">
            <div className="section-title"><span>ADMISSION TIMELINE</span><em>{selected.candidate_id}</em></div>
            <div className="rsi-timeline">
              {story.timeline.map((step) => (
                <div className={`rsi-step ${tone(step.state)}`} key={step.id} title={step.detail}>
                  <i />
                  <span>{step.label}</span>
                  <b>{step.state}</b>
                </div>
              ))}
            </div>
          </section>

          <section className="context-section">
            <div className="section-title"><span>GATES / METRICS</span><em>{selected.stage}</em></div>
            <div className="rsi-gates">
              <GateRow episode={selected} id="public" />
              <GateRow episode={selected} id="hidden" />
              <GateRow episode={selected} id="near_ood" />
              <GateRow episode={selected} id="regression" />
              <GateRow episode={selected} id="human" />
              <GateRow episode={selected} id="lease" />
              <GateRow episode={selected} id="confirmation" />
            </div>
          </section>

          {selected.confirmation && (
            <section className="context-section">
              <div className="section-title">
                <span>CONFIRMATION / DELTA</span>
                <em>{selected.confirmation.status} · {selected.confirmation.split}</em>
              </div>
              <div className="rsi-tracking">
                {Object.entries(selected.confirmation.delta).map(([key, value]) => (
                  <div className="rsi-metric" key={key}>
                    <b>{key.replaceAll("_", " ")}</b>
                    <span>{formatNumber(value)}</span>
                  </div>
                ))}
              </div>
              <p className="rsi-note">
                {selected.confirmation.note || "sealed confirmation 只记录配对结果，不是能力结论。"}
                这不是人工签核，也不自动写入下一轮准入。
              </p>
            </section>
          )}

          <section className="context-section">
            <div className="section-title"><span>PREDICTION AUDIT</span><em>{story.tracking.status.toUpperCase()}</em></div>
            <div className="rsi-tracking">
              {trackingKeys.length ? trackingKeys.map((key) => {
                const metric = story.tracking.metrics[key];
                return (
                  <div className="rsi-metric" key={key}>
                    <b>{key.replaceAll("_", " ")}</b>
                    <span>MAE {formatNumber(metric.mae)}</span>
                    <span>bias {formatNumber(metric.bias)}</span>
                    <span>dir {Math.round(metric.direction_agreement * 100)}%</span>
                  </div>
                );
              }) : <p className="context-empty">尚无数值预测-实际对照；本轮标为 {story.tracking.status}。</p>}
            </div>
            <p className="rsi-note">预测只是过程校准，不是能力证据；平均 R² 方向偏差仍保留在账本里。</p>
          </section>
        </>
      )}

      <section className="context-section">
        <div className="section-title"><span>STAGE MEMORY</span><em>{story.stage_process.length} STAGES</em></div>
        {story.stage_process.map((stage) => (
          <div className="rsi-stage" key={stage.stage}>
            <div className="rsi-stage-head"><b>{stage.stage}</b><span className={`rsi-state ${tone(stage.status)}`}>{stage.status}</span></div>
            <code>{stage.detail}</code>
            <small>{stage.targets.join(" · ")}</small>
            <div className="rsi-chip-row">{stage.candidates.map((id) => <span key={id}>{id}</span>)}</div>
          </div>
        ))}
      </section>

      <section className="context-section">
        <div className="section-title"><span>NEGATIVE RESULTS</span><em>{rejected.length} RETAINED</em></div>
        {rejected.length ? (
          <div className="rsi-negative">
            {rejected.map((item) => (
              <div key={item.episode_id}>
                <b>{item.candidate_id}</b>
                <span>{item.reason || item.decision}</span>
              </div>
            ))}
          </div>
        ) : <p className="context-empty">没有拒绝项；仍然不能把一次通过写成能力结论。</p>}
      </section>

      <section className="context-section">
        <div className="section-title"><span>AUDIT / NEXT</span><em>{story.warnings.length} WARNINGS</em></div>
        <div className="rsi-audit">
          {story.warnings.slice(0, 3).map((warning) => <p key={warning}>{warning}</p>)}
          {story.next_questions.slice(0, 2).map((question) => <p className="is-question" key={question}>{question}</p>)}
          {!story.warnings.length && !story.next_questions.length && <p>账本没有额外警告；仍需人工复核。</p>}
        </div>
      </section>

      <div className="context-footnote">
        <Icon name="lock" size={12} />
        <span>{story.boundary}</span>
      </div>
    </div>
  );
}
