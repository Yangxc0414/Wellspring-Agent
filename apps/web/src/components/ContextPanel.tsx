import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { modelProfile } from "../domain/catalog";
import { writingCard } from "../domain/seed";
import type { AutopilotSnapshot, AutoStage, Card, ClosureInventory, ContextTab, EvidenceItem, EvidencePackage, GateStatus, ProjectExperimentInventory, ProjectSummary, ResearchTask, RuntimeFlowMode, RuntimeSource, RuntimeTaskType } from "../domain/types";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { claimSignCommand, closureSignCommand, experimentApproveCommands, protocolFreezeCommand } from "../domain/gateCommands";
import { claimSignatureLabel } from "../domain/claimSignature";
import { hypothesisConvergence, literatureCoverage } from "../domain/researchBrief";
import { defaultRuntimeSource, runtimeRunState, runtimeSourceLabel } from "../domain/runtimeSnapshot";
import type { ResearchCheck } from "../domain/researchBrief";
import { probeRuntime, loadAutopilotStatus, loadEvolutionActive, loadEvolutionObservations, loadProjectClosures, loadProjects, loadProjectExperiments } from "../adapters/runtimeApi";
import type { EvolutionActive, EvolutionObservations, RuntimeHealth } from "../adapters/runtimeApi";
import { GateCommandItem, HumanGateCommand } from "./HumanGateCommand";
import { Icon } from "./Icon";
import { GovernancePanel } from "./GovernancePanel";
import { RsiStoryPanel } from "./RsiStoryPanel";
import { HostModelPanel } from "./HostModelPanel";

const TABS: Array<{ id: ContextTab; label: string }> = [
  { id: "brief", label: "BRIEF" },
  { id: "run", label: "RUN" },
  { id: "evidence", label: "EVIDENCE" },
  { id: "projects", label: "PROJECTS" },
  { id: "evolution", label: "EVOLUTION" },
  { id: "eval", label: "EVAL" }
];

const GATE_NAMES: Record<string, string> = {
  Q0: "Coverage",
  G1: "Hypotheses",
  G2: "Protocol",
  S5: "EA sealed",
  G5: "Closure"
};

function statusTone(status: GateStatus): string {
  if (status === "pass") return "ok";
  if (status === "needs_human") return "warn";
  if (status === "blocked") return "bad";
  return "idle";
}

function runtimeGateTone(status: string): string {
  if (status === "pass") return "ok";
  if (status === "needs_human" || status === "pending") return "warn";
  if (status === "blocked" || status === "fail") return "bad";
  return "idle";
}

type RuntimeCard = Extract<Card, { type: "runtime-run" }>;

function StageAction({
  children,
  onClick,
  disabled = false,
  primary = false
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      type="button"
      className={`stage-action${primary ? " primary" : ""}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

function CheckRail({ checks }: { checks: ResearchCheck[] }) {
  return (
    <div className="stage-checks">
      {checks.map((check) => (
        <div className={`stage-check is-${check.status}`} key={check.id}>
          <span className="stage-check-icon">
            {check.status === "ok" ? <Icon name="check" size={10} /> : check.status === "warn" ? <Icon name="alert" size={10} /> : <Icon name="lock" size={10} />}
          </span>
          <span className="stage-check-copy">
            <b>{check.label}</b>
            <small>{check.note}</small>
          </span>
          <em>{check.value}</em>
        </div>
      ))}
    </div>
  );
}

function StageDetailBody({ task, stage, index }: { task: ResearchTask; stage: AutoStage; index: number }) {
  const actions = useWorkspaceStore((state) => state.actions);
  const [gateRevealed, setGateRevealed] = useState(false);
  const autoBusy = task.auto.running;
  const claim = task.evidence.find((item) => item.kind === "claim");
  const claimSigned = claim?.status === "signed";
  const claimLabel = claimSignatureLabel(claim);
  const hypotheses = task.evidence.filter((item) => item.kind === "hypothesis");
  const g5 = task.gates.find((gate) => gate.id === "G5");
  const coverage = literatureCoverage(task);
  const convergence = hypothesisConvergence(task);
  const writing = writingCard({ claimSigned, protocolFrozen: task.protocolFrozen });
  const slots = writing.type === "writing" ? writing.slots : [];
  const bound = slots.filter((slot) => slot.status === "bound").length;
  const pending = slots.filter((slot) => slot.status === "pending").length;
  const locked = slots.filter((slot) => slot.status === "locked").length;
  const hasStageData =
    index === 0
      ? task.coverage.sources > 0 || task.coverage.spans > 0
      : index === 1
        ? hypotheses.length > 0
        : index === 2
          ? Boolean(task.protocol)
          : index === 3
            ? Boolean(task.run)
            : index === 4
              ? Boolean(task.run || claim)
              : index === 5
                ? Boolean(task.run)
                : index === 6
                  ? Boolean(task.protocol || claim)
                  : index === 7
                    ? Boolean(g5 && g5.status !== "not_started")
                    : index === 8
                      ? Boolean(task.evolution.candidate)
                      : false;

  if (stage.status === "skipped") {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{stage.output} · skipped in manual mode；没有收集 S1/S2 证据，结论仍停在人工门。</p>
        <div className="stage-detail-actions">
          <StageAction onClick={() => actions.setMode("research")}>回到调研补证据</StageAction>
          <StageAction onClick={() => actions.setContextTab("evidence")}>查看证据链</StageAction>
        </div>
      </div>
    );
  }

  if (stage.status === "pending" && !hasStageData) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>尚未执行。计划输出：{stage.output}</p>
      </div>
    );
  }

  if (index === 0) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{stage.output}</p>
        <div className="stage-kv-grid">
          <span>SOURCES<b>{task.coverage.sources}</b></span>
          <span>SPANS<b>{task.coverage.spans}</b></span>
          <span>GAPS<b>{task.coverage.gaps}</b></span>
          <span>ABSTRACT-ONLY<b>{task.coverage.abstractOnly}</b></span>
        </div>
        <p className="stage-note">摘要-only 只作线索，不生成 span，也不进入 claim。</p>
        <div className="stage-brief">
          <div className="stage-brief-head">
            <span>覆盖与总结</span>
            <em>{coverage.saturation} · {Math.round(coverage.score * 100)}%</em>
          </div>
          <p>{coverage.summary}</p>
          <CheckRail checks={coverage.checks} />
          <p className="stage-note">综述/方法/评测/局限/近期等六面向由 runtime LiteratureBrief 计算；这里先审计来源、全文、span 与 gap。</p>
        </div>
        <div className="stage-detail-actions">
          <StageAction primary onClick={() => actions.setContextTab("evidence")}>查看证据链</StageAction>
          <StageAction onClick={actions.runResearch} disabled={autoBusy}>扩展检索</StageAction>
        </div>
      </div>
    );
  }

  if (index === 1) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{stage.output}</p>
        {hypotheses.length ? (
          <ul className="stage-mini-list">
            {hypotheses.map((item) => (
              <li key={item.id}>
                <b>{item.id}</b>
                <span>{item.text}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="stage-note">还没有候选假设；先完成 S1 并登记 gap。</p>
        )}
        <div className="stage-brief">
          <div className="stage-brief-head">
            <span>候选收敛</span>
            <em>{convergence.multiRef}/{convergence.candidates} multi-ref</em>
          </div>
          <p>{convergence.summary}</p>
          <CheckRail checks={convergence.checks} />
        </div>
        <div className="stage-detail-actions">
          <StageAction primary onClick={actions.designExperiment} disabled={autoBusy || hypotheses.length === 0}>
            送入实验设计
          </StageAction>
          <StageAction onClick={() => actions.setContextTab("evidence")}>查看证据链</StageAction>
        </div>
      </div>
    );
  }

  if (index === 2) {
    const protocol = task.protocol;
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{protocol ? stage.output : "还没有协议草案；先收敛一个候选假设并进入 S4。"}</p>
        {protocol && (
          <div className="stage-kv-grid">
            <span>BASELINE<b>{protocol.baseline}</b></span>
            <span>SEEDS<b>{protocol.seeds}</b></span>
            <span>METRIC<b>{protocol.metric}</b></span>
            <span>CONTROL<b>{protocol.controls.join(" / ")}</b></span>
          </div>
        )}
        <div className="stage-detail-actions">
          <StageAction
            primary
            onClick={() => setGateRevealed((open) => !open)}
            disabled={autoBusy}
          >
            {gateRevealed ? "收起 G2 命令" : "G2 人工冻结命令"}
          </StageAction>
          <StageAction onClick={() => actions.setContextTab("evidence")}>证据链</StageAction>
        </div>
        {gateRevealed && (
          <HumanGateCommand
            title="G2 · 待人工冻结"
            detail="协议保持待冻结状态；先在终端核对设计，再运行下面的命令。网页不代为冻结。"
            commands={[protocolFreezeCommand(), ...experimentApproveCommands()]}
          />
        )}
      </div>
    );
  }

  if (index === 3) {
    const run = task.run;
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{run ? stage.output : "还没有可引用的 run；先冻结协议（G2）并执行 S5a。"}</p>
        {run && (
          <>
            <p className="demo-disclaimer">演示数值 · 本地 fixture，不构成研究证据；真实结果须经 CLI 人签。</p>
            <div className="stage-kv-grid">
              <span>MEAN<b>{run.mean} {run.metric}</b></span>
              <span>BASELINE<b>{run.baseline ?? "—"}</b></span>
              <span>SEEDS<b>{run.seeds}</b></span>
              <span>EA<b>{run.ea}</b></span>
            </div>
          </>
        )}
        <div className="stage-detail-actions">
          <StageAction primary onClick={() => actions.setContextTab("evidence")}>查看 EA</StageAction>
          <StageAction
            onClick={actions.runExperiment}
            disabled={!task.protocolFrozen || autoBusy || task.evaluation.hiddenAccessCount > 0}
          >
            运行 3 seeds
          </StageAction>
        </div>
      </div>
    );
  }

  if (index === 4) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{claimLabel.detail}</p>
        <div className="stage-kv-grid">
          <span>CLAIM<b>{claimLabel.short}</b></span>
          <span>EA<b>{task.run?.ea ?? "NOT SEALED"}</b></span>
        </div>
        <div className="stage-detail-actions">
          <StageAction primary onClick={actions.signClaim}>
            {claimLabel.state === "unsigned" || claimLabel.state === "missing"
              ? "签署 claim · 人工门"
              : "查看 claim 签署来源"}
          </StageAction>
          <StageAction onClick={() => actions.setContextTab("evidence")}>查看证据链</StageAction>
        </div>
      </div>
    );
  }

  if (index === 5) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{task.run ? "SVG 与 manifest 已绑定到 EA-7c41；图不能脱离 EA 单独引用。" : "等待 EA 封存后才能绑定结果图。"}</p>
        <div className="stage-detail-actions">
          <StageAction onClick={() => actions.setContextTab("evidence")}>查看证据链</StageAction>
        </div>
      </div>
    );
  }

  if (index === 6) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{`${bound}/6 已绑定 · ${pending} pending · ${locked} locked`}</p>
        <div className="stage-kv-grid">
          <span>BOUND<b>{bound}</b></span>
          <span>LOCKED<b>{locked}</b></span>
        </div>
        <p className="stage-note">没有已签 claim 的结果/摘要槽位保持 locked；正文不先于证据填数。</p>
        <div className="stage-detail-actions">
          <StageAction primary onClick={actions.prepareWriting} disabled={autoBusy}>生成写作槽位</StageAction>
          <StageAction onClick={() => actions.setContextTab("evidence")}>检查证据边界</StageAction>
        </div>
      </div>
    );
  }

  if (index === 7) {
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{g5?.reason ?? "closure 尚未运行。"}</p>
        <div className="stage-detail-actions">
          <StageAction primary onClick={() => setGateRevealed((open) => !open)}>
            {gateRevealed ? "收起 G5 命令" : "G5 闭合签核命令"}
          </StageAction>
          <StageAction onClick={() => actions.setContextTab("eval")}>查看评估隔离</StageAction>
          <StageAction onClick={() => actions.setContextTab("evidence")}>证据链</StageAction>
        </div>
        {gateRevealed && (
          <HumanGateCommand
            title="G5 · 待人工闭合签核"
            detail="closure 通过后导出仍需人工签核；runtime 不提供 sign 端点，网页也不会代为签核。"
            commands={[closureSignCommand()]}
          />
        )}
      </div>
    );
  }

  if (index === 8) {
    const candidate = task.evolution.candidate;
    return (
      <div className="stage-detail">
        <code>{stage.cmd}</code>
        <p>{candidate ? `${candidate.id} · ${candidate.status} · ${candidate.lease}` : "还没有自进化候选；到达 META 后生成并等待人工准入。"}</p>
        <div className="stage-detail-actions">
          <StageAction primary onClick={() => actions.setContextTab("evolution")}>查看自进化</StageAction>
        </div>
      </div>
    );
  }

  return (
    <div className="stage-detail">
      <code>{stage.cmd}</code>
      <p>{stage.output}</p>
    </div>
  );
}

function useRuntimeHealth() {
  const [health, setHealth] = useState<RuntimeHealth | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    if (__STATIC_ONLY__) return;
    let cancelled = false;
    let timer = 0;
    const load = () => {
      probeRuntime()
        .then((value) => {
          if (cancelled) return;
          setHealth(value);
          setOffline(false);
        })
        .catch(() => {
          if (!cancelled) setOffline(true);
        });
    };
    load();
    timer = window.setInterval(load, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { health, offline };
}

function RuntimePreflight({
  health,
  offline
}: {
  health: RuntimeHealth | null;
  offline: boolean;
}) {
  const actions = useWorkspaceStore((state) => state.actions);

  if (__STATIC_ONLY__) return null;
  if (offline) {
    return (
      <div className="run-preflight is-bad">
        <Icon name="shield" size={13} />
        <div>
          <b>本地 runtime 未连接</b>
          <small>任务不会执行。先运行 `python -m research_agent.runtime --port 8787`，再刷新本页。</small>
        </div>
      </div>
    );
  }
  if (!health) return null;
  const blocking = health.model_readiness?.blocking ?? [];
  if (health.research_mode === "production" && !health.production_ready) {
    return (
      <div className="run-preflight is-warn">
        <Icon name="shield" size={13} />
        <div>
          <b>生产模式未就绪</b>
          <small>{blocking.slice(0, 3).join(" · ") || "required 模块尚未全部绑定并配置 key"}</small>
          <button type="button" onClick={() => actions.openSettings("model")}>
            打开模型设置
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className={`run-preflight ${health.production_ready ? "is-ok" : "is-test"}`}>
      <Icon name={health.production_ready ? "check" : "shield"} size={13} />
      <div>
        <b>{health.production_ready ? "runtime · production ready" : "runtime · test 模式"}</b>
        <small>
          {health.production_ready
            ? "required 模块已绑定并配置 key；claim/closure/导出仍需人工。"
            : "缺模型 key 时会回退规则/模板，仅用于流程验证；正式结果需配置 API key 与模块绑定。"}
        </small>
      </div>
    </div>
  );
}

function RunContext({ task }: { task: ResearchTask }) {
  const actions = useWorkspaceStore((state) => state.actions);
  const { health, offline } = useRuntimeHealth();
  const [runtimeSource, setRuntimeSource] = useState<RuntimeSource>(() => defaultRuntimeSource(task));
  const [runtimeTaskType, setRuntimeTaskType] = useState<RuntimeTaskType>("auto");
  const [runtimeFlowMode, setRuntimeFlowMode] = useState<RuntimeFlowMode>("review");
  const [runtimeDataset, setRuntimeDataset] = useState<"" | "iris" | "breast_cancer" | "chemlab">(() => {
    const value = (task.run?.dataset ?? "").toLowerCase();
    if (value.includes("chemlab")) return "chemlab";
    if (value.includes("breast")) return "breast_cancer";
    if (value.includes("iris")) return "iris";
    return "";
  });
  const [runtimeSeeds, setRuntimeSeeds] = useState(() => task.protocol?.seeds ?? task.run?.seeds ?? 3);
  const [g1DecisionFile, setG1DecisionFile] = useState("");
  const [protocolFile, setProtocolFile] = useState("");
  const [claimFile, setClaimFile] = useState("");
  const [bibliographyFile, setBibliographyFile] = useState("");
  const [runDir, setRunDir] = useState("");
  const runtimeCard = [...task.messages]
    .reverse()
    .find((entry) => entry.card?.type === "runtime-run")?.card as RuntimeCard | undefined;
  const runtimeBacked = Boolean(task.runtime ?? runtimeCard);
  const sourceUnavailable = Boolean(
    health
    && ((runtimeSource === "local" && !health.local_corpus)
      || (runtimeSource === "real_corpus" && !health.real_corpus))
  );
  const showRunDataset = runtimeTaskType === "auto"
    || runtimeTaskType === "experiment_validation"
    || runtimeTaskType === "full_research";

  useEffect(() => {
    if (
      runtimeTaskType === "experiment_validation"
      || runtimeTaskType === "full_research"
      || Boolean(runtimeDataset)
    ) {
      setRuntimeFlowMode("strict");
    }
  }, [runtimeTaskType, runtimeDataset]);
  const autoExpand = useWorkspaceStore((state) => state.preferences.autoExpandRunning);
  const claim = task.evidence.find((item) => item.kind === "claim");
  const claimSigned = task.evidence.some((item) => item.kind === "claim" && item.status === "signed");
  const claimLabel = claimSignatureLabel(claim);
  const done = task.autoStages.filter((stage) => stage.status === "done").length;
  const skipped = task.autoStages.filter((stage) => stage.status === "skipped").length;
  const progress = runtimeBacked
    ? Math.round((task.completedStages.length / task.autoStages.length) * 100)
    : Math.round((done / task.autoStages.length) * 100);
  const runtimeLabel = runtimeRunState(runtimeCard);
  const runtimeLive = runtimeCard?.status === "queued" || runtimeCard?.status === "running";
  const pausedAtGate = task.auto.running && task.auto.paused && task.auto.gate === "claim";
  const stateLabel = !task.auto.running
    ? done === task.autoStages.length && done > 0
      ? "待人工闭合"
      : "IDLE"
    : pausedAtGate
      ? "PAUSED AT CLAIM"
      : task.auto.paused
        ? "PAUSED"
        : "RUNNING";
  const canResume = task.auto.running && task.auto.paused && (!pausedAtGate || claimSigned);
  const activeIndex = task.auto.running
    ? task.auto.paused
      ? Math.max(task.auto.index - 1, 0)
      : task.auto.index
    : task.autoStages.findIndex((stage) => stage.status !== "done" && stage.status !== "skipped");
  const current = activeIndex >= 0 ? task.autoStages[activeIndex] : undefined;
  const blockedGate = task.gates.find((gate) => gate.status === "needs_human")
    ?? task.gates.find((gate) => gate.status === "blocked");
  const [expandedStage, setExpandedStage] = useState<string | null>(null);

  useEffect(() => {
    setExpandedStage(null);
  }, [task.id]);

  useEffect(() => {
    if (!autoExpand || !task.auto.running) return;
    const stage = task.autoStages[activeIndex];
    if (stage) setExpandedStage(stage.id);
  }, [activeIndex, autoExpand, task.auto.running, task.auto.index, task.autoStages]);

  const traceLabel = runtimeBacked
    ? `RUNTIME ${runtimeLabel}`
    : !task.auto.running
      ? blockedGate
        ? `WAIT ${blockedGate.id}`
        : current
          ? `NEXT ${current.id}`
          : "COMPLETE"
      : pausedAtGate
      ? "WAITING AT GATE"
      : task.auto.paused
        ? `PAUSED AFTER ${current?.id ?? "RUN"}`
        : `RUNNING ${current?.id ?? "RUN"}`;

  return (
    <div className="context-stack">
      <section className="context-card run-overview">
        {runtimeBacked ? (
          <>
            <div className="card-label">
              <span>RUNTIME RUN</span>
              <em>{runtimeCard ? runtimeCard.status.toUpperCase() : "LOCAL API"}</em>
            </div>
            <div className="run-state-row">
              <span className={`run-state${runtimeLive ? " is-live" : ""}`}>
                <i />
                {runtimeLabel}
              </span>
              <span>{runtimeCard ? `${runtimeCard.events} events` : "等待事件"}</span>
            </div>
            <div className="progress-track" aria-label={`已完成 ${progress}%`}>
              <i style={{ width: `${progress}%` }} />
            </div>
            <div className="run-numbers">
              <span>JOB <b>{runtimeCard?.jobId ? runtimeCard.jobId.slice(-8) : "—"}</b></span>
              <span>ROUTE <b>{runtimeCard?.route ?? runtimeCard?.taskType ?? "auto"}</b></span>
            </div>
            <div className="run-numbers">
              <span>FLOW <b>{runtimeCard?.flowMode ?? "review"}</b></span>
              <span>STAGE <b>{runtimeCard?.stage ?? "—"}</b></span>
            </div>
            {runtimeCard?.verdictBus?.closure ? (
              <div className="run-numbers">
                <span>
                  CLOSURE <b>{runtimeCard.verdictBus.closure.status ?? "unknown"}</b>
                  {runtimeCard.verdictBus.closure.delegated ? " · delegated" : ""}
                </span>
                <span>CLAIM <b>{runtimeCard.verdictBus.closure.has_signed_claim ? "signed" : "unsigned"}</b></span>
              </div>
            ) : null}
            {runtimeCard?.verdictBus?.capsule_source ? (
              <div className="run-numbers">
                <span>
                  CAPSULE <b>{runtimeCard.verdictBus.capsule_source === "recomputed" ? "产物为准 · 读时重算" : "快照兜底"}</b>
                </span>
              </div>
            ) : null}
            {runtimeCard?.execStats?.counts && Object.keys(runtimeCard.execStats.counts).length ? (
              <div className="run-numbers">
                <span>
                  EXEC{" "}
                  <b>
                    {Object.entries(runtimeCard.execStats.counts)
                      .map(([kind, count]) => `${kind}×${count}`)
                      .join(" · ")}
                  </b>
                </span>
                <span>{runtimeCard.execStats.faces ?? 0} faces</span>
              </div>
            ) : null}
            {runtimeCard?.execStats?.counts && Object.keys(runtimeCard.execStats.counts).length ? (
              <p className="run-hint">
                执行面接缝计数（ExecPort dispatch）：每次本地执行/桥接/宿主模型调度都经同一接缝计数放行——只读遥测，不含门禁语义。
              </p>
            ) : null}
            {runtimeCard?.verdictBus?.verdict_override ? (
              <p className="run-hint">
                快照冲突已由判定总线裁定：快照说 {runtimeCard.verdictBus.verdict_override.snapshot}，
                重算 = <b>{runtimeCard.verdictBus.verdict_override.recomputed}</b>——以总线为准，不要按快照建议重签。
              </p>
            ) : null}
            {runtimeCard?.verdictBus?.error ? (
              <p className="run-hint">判定总线不可用：{runtimeCard.verdictBus.error}</p>
            ) : (
              <p className="run-hint">
                闭包判定从产物重算（verdict-ledger 单点）；事件来自本地 runtime；claim、closure 与导出仍只能在终端人工完成。
              </p>
            )}
          </>
        ) : (
          <>
            <div className="card-label">
              <span>GOVERNED AUTO</span>
              <em>{task.auto.cycle ? `CYCLE ${task.auto.cycle}` : "演示数据"}</em>
            </div>
            <div className="run-state-row">
              <span className={`run-state${task.auto.running && !task.auto.paused ? " is-live" : ""}`}>
                <i />
                {stateLabel}
              </span>
              <span>
                {done}/{task.autoStages.length} stages
                {skipped > 0 ? ` · ${skipped} skipped` : ""}
              </span>
            </div>
            <div className="progress-track" aria-label={`已完成 ${progress}%`}>
              <i style={{ width: `${progress}%` }} />
            </div>
            <div className="run-numbers">
              <span>BUDGET <b>{task.budget.used}/{task.budget.total}</b></span>
              <span>HARNESS <b>{task.harness.version}</b></span>
            </div>
          </>
        )}
        {task.autoPlan && !runtimeBacked && (
          <div className="auto-plan-card">
            <div className="auto-plan-head">
              <span>BACKEND PLAN</span>
              <em>{task.autoPlan.fingerprint.slice(-8)}</em>
            </div>
            <div className="auto-plan-grid">
              <span>STAGES<b>{task.autoPlan.stages.length}</b></span>
              <span>STOP<b>{task.autoPlan.stop_at}</b></span>
              <span>GATES<b>{task.autoPlan.human_gates.length}</b></span>
              <span>SOURCES<b>{String(task.autoPlan.budget.max_sources ?? "—")}</b></span>
            </div>
            <p title={task.autoPlan.boundary}>
              {task.autoPlan.adaptive_literature.strategy.replaceAll("_", " ")} · {task.autoPlan.human_gates.map((gate) => gate.id).join(" / ")}
            </p>
          </div>
        )}
        {pausedAtGate && !runtimeBacked && (
          <div className="gate-hint">
            <Icon name="lock" size={13} />
            <span>
              {claimSigned
                ? "claim 已签；可以继续运行。"
                : "claim 未签；继续/单步会被门禁拒绝。签核只能在本地 CLI 完成，前端不会代为签署或解锁；签核后请重新载入状态或以 /live 续跑。"}
            </span>
          </div>
        )}
        <div className="run-controls">
          {!runtimeBacked && (
            <>
              {!task.auto.running ? (
                <button type="button" className="control primary" onClick={actions.startAuto}>
                  <Icon name="play" size={12} />
                  启动全自动
                </button>
              ) : canResume ? (
                <button type="button" className="control primary" onClick={actions.resumeAuto}>
                  <Icon name="play" size={12} />
                  继续
                </button>
              ) : (
                !task.auto.paused && (
                  <button type="button" className="control" onClick={actions.pauseAuto}>
                    <Icon name="pause" size={12} />
                    暂停
                  </button>
                )
              )}
              <button
                type="button"
                className="control"
                onClick={actions.stepAuto}
                disabled={pausedAtGate && !claimSigned}
                title="执行一个阶段后暂停"
              >
                <Icon name="step" size={12} />
                单步
              </button>
              {task.auto.running && (
                <button type="button" className="control danger" onClick={actions.stopAuto}>
                  <Icon name="stop" size={12} />
                  停止
                </button>
              )}
            </>
          )}
          {!__STATIC_ONLY__ && (
            <>
              <select
                className="control"
                value={runtimeTaskType}
                onChange={(event) => setRuntimeTaskType(event.target.value as RuntimeTaskType)}
                disabled={task.auto.running || claimSigned}
                title="任务路由：自动只跑必要阶段"
                aria-label="选择任务类型"
              >
                <option value="auto">自动路由</option>
                <option value="literature_review">文献综述</option>
                <option value="hypothesis_design">假设设计</option>
                <option value="experiment_validation">实验验证</option>
                <option value="full_research">完整研究</option>
              </select>
              <select
                className="control"
                value={runtimeSource}
                onChange={(event) => setRuntimeSource(event.target.value as RuntimeSource)}
                disabled={task.auto.running || claimSigned}
                title={runtimeSourceLabel(runtimeSource)}
                aria-label="选择证据来源"
              >
                <option value="fixture">fixture 演示</option>
                <option value="real_corpus" disabled={health ? !health.real_corpus : false}>
                  CC-BY 正文{health && !health.real_corpus ? "（未配置）" : ""}
                </option>
                <option value="local" disabled={health ? !health.local_corpus : false}>
                  本地全文{health && !health.local_corpus ? "（未配置）" : ""}
                </option>
                <option value="openalex">OpenAlex 摘要</option>
              </select>
              <select
                className="control"
                value={runtimeFlowMode}
                onChange={(event) => setRuntimeFlowMode(event.target.value as RuntimeFlowMode)}
                disabled={task.auto.running || claimSigned}
                title="review 生成完整待审包；strict 在 Q0/G1/G2 前停止"
                aria-label="选择流程模式"
              >
                <option value="review">待审包 review</option>
                <option value="strict">门禁 strict</option>
              </select>
              <button
                type="button"
                className="control"
                onClick={() => void actions.startLiveRun(
                  runtimeSource,
                  runtimeTaskType,
                  runtimeFlowMode,
                  {
                    runDataset: showRunDataset ? runtimeDataset : "",
                    runSeeds: runtimeSeeds,
                    g1DecisionFile,
                    protocolFile,
                    claimFile,
                    bibliographyFile,
                    runDir
                  }
                )}
                disabled={task.auto.running || claimSigned || sourceUnavailable}
                title={
                  sourceUnavailable
                    ? "所选来源未配置；请先在执行环境中配置，或切换来源"
                    : `运行本地 runtime 任务：${runtimeTaskType} · ${runtimeSourceLabel(runtimeSource)} · ${runtimeFlowMode}；不会自动签 claim`
                }
              >
                <Icon name="play" size={12} />
                运行任务
              </button>
            </>
          )}
        </div>
        <RuntimePreflight health={health} offline={offline} />
        {sourceUnavailable && (
          <p className="run-hint">所选来源未配置，运行已禁用；请在执行环境中配置目录，或切换来源。</p>
        )}
        {runtimeBacked && (
          <p className="run-hint">
            该任务已由本地 runtime 执行；演示自动推进已禁用，请使用“运行任务”或严格流程续跑。
          </p>
        )}
        {!__STATIC_ONLY__ && showRunDataset && (
          <div className="run-options">
            <label>
              <span>S5 数据集</span>
              <select
                className="control"
                value={runtimeDataset}
                onChange={(event) => setRuntimeDataset(event.target.value as typeof runtimeDataset)}
                disabled={task.auto.running || claimSigned}
                aria-label="选择实验数据集"
              >
                <option value="">不执行 S5</option>
                <option value="iris">iris</option>
                <option value="breast_cancer">breast_cancer</option>
                <option value="chemlab">chemlab</option>
              </select>
            </label>
            <label>
              <span>seeds</span>
              <input
                className="control"
                type="number"
                min={1}
                max={10}
                value={runtimeSeeds}
                onChange={(event) => setRuntimeSeeds(Math.max(1, Math.min(10, Number(event.target.value) || 1)))}
                disabled={task.auto.running || claimSigned}
                aria-label="实验 seeds"
              />
            </label>
          </div>
        )}
        {!__STATIC_ONLY__ && runtimeFlowMode === "review" && showRunDataset && (
          <p className="run-hint">
            review 会先执行阶段、事后报告门禁；涉及实验验证或 claim 时请切换到 strict，先过 G1/G2。
          </p>
        )}
        {!__STATIC_ONLY__ && runtimeFlowMode === "strict" && (
          <div className="strict-resume">
            <div className="strict-resume-head">
              <b>严格流程续跑</b>
              <span>可选：填入本地 G1/G2/claim 文件路径</span>
            </div>
            <p>
              strict 会在 Q0 / G1 / G2 前停止。请先在终端人工确认，并用 CLI 生成
              <code>g1-decision.json</code>、<code>protocol-card.json</code>；runtime 不代签。
              填好路径后点击“运行任务”，会按同一主题重新执行到下一停点。
            </p>
            <label className="strict-resume-field">
              <span>G1 决策 JSON</span>
              <input
                value={g1DecisionFile}
                onChange={(event) => setG1DecisionFile(event.target.value)}
                placeholder="runtime_data/jobs/.../g1-decision.json"
                spellCheck={false}
              />
            </label>
            <label className="strict-resume-field">
              <span>ProtocolCard JSON</span>
              <input
                value={protocolFile}
                onChange={(event) => setProtocolFile(event.target.value)}
                placeholder="runtime_data/jobs/.../protocol-card.json"
                spellCheck={false}
              />
            </label>
            <label className="strict-resume-field">
              <span>已签 Claim（可选）</span>
              <input
                value={claimFile}
                onChange={(event) => setClaimFile(event.target.value)}
                placeholder="runtime_data/jobs/.../claim/claim.json"
                spellCheck={false}
              />
            </label>
            <label className="strict-resume-field">
              <span>Bibliography JSON（可选）</span>
              <input
                value={bibliographyFile}
                onChange={(event) => setBibliographyFile(event.target.value)}
                placeholder="research_agent/web/data/bibliography/bibliography.json"
                spellCheck={false}
              />
            </label>
            <label className="strict-resume-field">
              <span>复用 Run 目录（可选）</span>
              <input
                value={runDir}
                onChange={(event) => setRunDir(event.target.value)}
                placeholder="runtime_data/jobs/.../run"
                spellCheck={false}
              />
            </label>
            <p>
              签署 claim 后必须填“复用 Run 目录”，让系统复用原 RunCapsule/EA；否则重跑 S5 会产生新 EA，已签 claim 会失效。
            </p>
          </div>
        )}
        {pausedAtGate && !claimSigned && !task.runtime && (
          <HumanGateCommand
            title="Q0 · 停在 claim 人工门"
            detail="全自动已在 claim 门暂停；浏览器不产生签名。在终端核对 EA 后运行下面命令，再回到这里续跑。"
            commands={[claimSignCommand({ runDir })]}
          />
        )}
        {pausedAtGate && !claimSigned && task.runtime && (
          <p className="run-hint">
            当前是 runtime 任务：claim 必须在终端人工签署，浏览器不会代为签核。
          </p>
        )}
        {pausedAtGate && !claimSigned && (
          <div className="stage-detail-actions">
            <StageAction primary onClick={actions.signClaim}>
              打开 claim 人工门面板（命令 / 导入 / DEMO 预览）
            </StageAction>
          </div>
        )}
      </section>

      {runtimeBacked ? (
        <section className="context-section">
          <div className="section-title">
            <span>RUNTIME TRACE</span>
            <em>{traceLabel}</em>
          </div>
          {runtimeCard?.lastEvent && (
            <p className="run-hint">最近事件：{runtimeCard.lastEvent}</p>
          )}
          {runtimeCard?.eventLog?.length ? (
            <div className="runtime-events">
              {runtimeCard.eventLog.slice(-12).map((event) => (
                <div className="runtime-event-row" key={event.seq}>
                  <code>#{event.seq}</code>
                  <span>{event.stage ?? event.type}</span>
                  <em>{event.message}</em>
                </div>
              ))}
            </div>
          ) : (
            <p className="context-empty">runtime 尚未返回事件。</p>
          )}
          <p className="run-hint">
            只展示 runtime 实际产生的事件；未出现的阶段不可假定已执行。9 阶段是完整研究目录，不表示本任务全部执行。
          </p>
        </section>
      ) : (
        <section className="context-section">
          <div className="section-title">
            <span>STAGE TRACE</span>
            <em>{traceLabel}</em>
          </div>
          {blockedGate && !task.auto.running && (
            <p className="run-hint">当前停在 {blockedGate.id}：{blockedGate.reason}</p>
          )}
          <div className="stage-list">
            {task.autoStages.map((stage, index) => {
              const isTracked = index === activeIndex;
              const isLive = isTracked && task.auto.running && !task.auto.paused;
              const isCurrent = isTracked && !blockedGate && stage.status !== "done" && stage.status !== "skipped";
              const isDone = stage.status === "done";
              const isSkipped = stage.status === "skipped";
              const isExpanded = expandedStage === stage.id;
              return (
                <div
                  className={`stage-row${isCurrent || isLive ? " is-current" : ""}${isTracked && !task.auto.running && !blockedGate ? " is-next" : ""}${isLive ? " is-live" : ""}${isDone ? " is-done" : ""}${isSkipped ? " is-skipped" : ""}${isTracked && pausedAtGate ? " is-waiting-gate" : ""}${isExpanded ? " is-expanded" : ""}`}
                  key={stage.id}
                >
                  <button
                    type="button"
                    className="stage-summary"
                    onClick={() => setExpandedStage((current) => current === stage.id ? null : stage.id)}
                    aria-expanded={isExpanded}
                    aria-current={isTracked ? "step" : undefined}
                    title={isExpanded ? "收起阶段详情" : "展开阶段详情"}
                  >
                    <span className="stage-status">
                      {isDone ? <Icon name="check" size={11} /> : isSkipped ? <span className="stage-skip-mark">–</span> : isCurrent ? <span className={`stage-live-dot${isLive ? " is-live" : ""}`} title={isLive ? "当前阶段 · 实时运行中" : "当前阶段 · 等待继续"} aria-label={isLive ? "当前阶段，正在运行" : "当前阶段，等待继续"} /> : <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>}
                    </span>
                    <span className="stage-name">
                      <b>{stage.id}</b>
                      <small>{stage.label}</small>
                    </span>
                    {isSkipped && <span className="stage-skip">SKIP</span>}
                    {stage.gate && <span className="stage-gate">GATE</span>}
                    <span className={`chevron${isExpanded ? " is-open" : ""}`}>
                      <Icon name="chevron" size={10} />
                    </span>
                  </button>
                  {isExpanded && <StageDetailBody task={task} stage={stage} index={index} />}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {runtimeBacked ? (
        <section className="context-section">
          <div className="section-title">
            <span>RUNTIME GATES</span>
            <em>{runtimeCard?.gates?.length ?? 0} REPORTED</em>
          </div>
          <div className="gate-list">
            {runtimeCard?.gates?.length ? (
              runtimeCard.gates.map((gate, index) => (
                <div className="gate-row" key={`${gate.gate}-${index}`}>
                  <span className={`gate-dot ${runtimeGateTone(gate.status)}`} />
                  <span className="gate-name">
                    <b>{gate.gate}{GATE_NAMES[gate.gate] ? ` · ${GATE_NAMES[gate.gate]}` : ""}</b>
                    <small>{gate.reason}</small>
                  </span>
                  <span className={`badge ${runtimeGateTone(gate.status)}`}>
                    {gate.status.replaceAll("_", " ")}
                  </span>
                </div>
              ))
            ) : (
              <p className="context-empty">runtime 未返回 gate 记录；不能据此推断门禁已通过。</p>
            )}
            <div className="gate-row">
              <span className={`gate-dot ${claimLabel.demo ? "warn" : claimSigned ? "ok" : "warn"}`} />
              <span className="gate-name">
                <b>CLAIM · human signature</b>
                <small>{claimLabel.detail}</small>
              </span>
              <span className={`badge ${claimLabel.demo ? "warn" : claimSigned ? "ok" : "warn"}`}>
                {claimLabel.badge}
              </span>
            </div>
          </div>
        </section>
      ) : (
        <section className="context-section">
          <div className="section-title">
            <span>GATES</span>
            <em>{task.gates.filter((gate) => gate.status === "pass").length}/{task.gates.length} PASS</em>
          </div>
          <div className="gate-list">
            {task.gates.map((gate) => (
              <div className="gate-row" key={gate.id}>
                <span className={`gate-dot ${statusTone(gate.status)}`} />
                <span className="gate-name">
                  <b>{gate.id} · {GATE_NAMES[gate.id] ?? gate.id}</b>
                  <small>{gate.reason}</small>
                </span>
                <span className={`badge ${statusTone(gate.status)}`}>{gate.status.replace("_", " ")}</span>
              </div>
            ))}
            <div className="gate-row">
              <span className={`gate-dot ${claimLabel.demo ? "warn" : claimSigned ? "ok" : task.run ? "warn" : "idle"}`} />
              <span className="gate-name">
                <b>CLAIM · human signature</b>
                <small>{claimLabel.detail}</small>
              </span>
              <span className={`badge ${claimLabel.demo ? "warn" : claimSigned ? "ok" : task.run ? "warn" : "idle"}`}>
                {claimLabel.badge}
              </span>
            </div>
          </div>
        </section>
      )}

      {!runtimeBacked && (
        <section className="context-section">
          <div className="section-title">
            <span>GUIDANCE QUEUE</span>
            <em>{task.guidance.filter((item) => item.status === "pending").length} PENDING</em>
          </div>
          {task.guidance.length ? (
            <div className="guidance-list">
              {[...task.guidance].reverse().slice(0, 4).map((item) => (
                <div className={`guidance-row ${item.status}`} key={item.id}>
                  <span className="guidance-status">{item.status === "pending" ? "QUEUED" : "APPLIED"}</span>
                  <p>{item.text}</p>
                  <small>{item.status === "applied" ? `应用 ${item.appliedAt}` : `记录 ${item.at}`}</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="context-empty">运行中输入任何文本都会进入指导队列，在下一阶段边界生效，并写入 trace。</p>
          )}
        </section>
      )}

      <div className="context-footnote">
        <Icon name="shield" size={12} />
        <span>
          {runtimeBacked
            ? "RUNTIME worker：阶段由本地 runtime 真实执行；claim、closure 与导出仍需离线人工签署。"
            : "静态 worker：阶段推进为本地模拟，不启动真实实验或外部调用。"}
        </span>
      </div>
    </div>
  );
}

const packageStatusLabel: Record<EvidencePackage["status"], string> = {
  ready: "就绪",
  partial: "部分",
  needs_human: "待人工",
  needs_signature: "待签署",
  missing: "缺失",
  blocked: "阻断",
  not_run: "未运行"
};

function packageTone(status: EvidencePackage["status"]): string {
  if (status === "ready") return "ok";
  if (status === "blocked") return "bad";
  if (status === "missing" || status === "not_run") return "idle";
  return "warn";
}

function ProjectExperimentInventoryPanel() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [active, setActive] = useState("");
  const [inventory, setInventory] = useState<ProjectExperimentInventory | null>(null);
  const [closures, setClosures] = useState<ClosureInventory | null>(null);
  const [autopilot, setAutopilot] = useState<AutopilotSnapshot | null>(null);
  const [closureError, setClosureError] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadProjects()
      .then((list) => {
        if (cancelled) return;
        setProjects(list);
        const first = list.find((item) => item.experiment_count > 0) ?? list[0];
        setActive(first?.project_dir ?? "");
        if (!first) setLoading(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "项目清单读取失败");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!active) {
      setInventory(null);
      setClosures(null);
      setAutopilot(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError("");
    // Clear the previous project's rows immediately: keeping them on screen while the new
    // request is in flight shows one project's closure under another project's name.
    setInventory(null);
    setClosures(null);
    setAutopilot(null);
    loadAutopilotStatus(active)
      .then((data) => {
        if (!cancelled) setAutopilot(data);
      })
      .catch(() => {
        if (!cancelled) setAutopilot(null);
      });
    // A closure read failing must not blank the experiment chain: they are separate inventories.
    loadProjectClosures(active)
      .then((data) => {
        if (!cancelled) setClosures(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setClosures(null);
          setClosureError(err instanceof Error ? err.message : String(err));
        }
      });
    loadProjectExperiments(active)
      .then((data) => {
        if (cancelled) return;
        setInventory(data);
        setLoading(false);
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "项目实验链读取失败");
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  if (!projects.length && !loading && !error) return null;

  return (
    <section className="context-section project-experiments">
      <div className="section-title">
        <span>PROJECT EXPERIMENTS</span>
        <em>READ-ONLY INVENTORY</em>
      </div>
      {projects.length > 1 && (
        <div className="project-experiment-tabs">
          {projects.map((project) => (
            <button
              type="button"
              key={project.project_dir}
              className={project.project_dir === active ? "is-active" : ""}
              onClick={() => setActive(project.project_dir)}
              title={project.project_dir}
            >
              {project.name}
              <em>{project.experiment_count}</em>
            </button>
          ))}
        </div>
      )}
      {loading && <p className="run-hint">读取项目实验链…</p>}
      {error && <p className="run-hint">项目实验链不可用：{error}</p>}
      {inventory && inventory.experiments.length === 0 && (
        <p className="run-hint">该 project 尚无 experiments；CLI 生成实验包后会出现在这里。</p>
      )}
      {inventory?.experiments.map((experiment) => {
        const tone =
          experiment.stages?.signature === "signed"
            ? "ready"
            : experiment.stages?.claim === "signed"
              ? "needs_human"
              : "blocked";
        const mean =
          typeof experiment.evidence_summary?.mean === "number"
            ? experiment.evidence_summary.mean.toFixed(4)
            : "—";
        const std =
          typeof experiment.evidence_summary?.std === "number"
            ? experiment.evidence_summary.std.toFixed(4)
            : "—";
        return (
          <article className={`evidence-package ${tone}`} key={experiment.experiment_id}>
            <div className="evidence-package-head">
              <span className="evidence-package-stage">EXP</span>
              <b>{experiment.experiment_id}</b>
              <span className={`badge ${tone === "ready" ? "ok" : tone === "blocked" ? "bad" : "warn"}`}>
                {tone === "ready" ? "已闭合" : tone === "needs_human" ? "待人工" : "未闭合"}
              </span>
            </div>
            <p>
              {experiment.idea_id || "no idea"} · {experiment.run_id || "no run"} · evidence=
              {experiment.stages?.evidence ?? "missing"} · claim={experiment.stages?.claim ?? "missing"}
            </p>
            <small>
              closure={experiment.stages?.closure ?? "missing"} · signature=
              {experiment.stages?.signature ?? "missing"} · next: {experiment.next_action || "unknown"}
            </small>
            <small>
              result={experiment.evidence_summary?.status ?? "missing"} · mean={mean} · std={std}
              {experiment.evidence_summary?.cv_folds ? ` · cv=${experiment.evidence_summary.cv_folds}` : ""}
            </small>
            {experiment.error && <small>status error: {experiment.error}</small>}
          </article>
        );
      })}
      {!closures && closureError && (
        <div className="closure-inventory">
          <div className="section-title">
            <span>CLOSURE PROFILES</span>
            <em>UNAVAILABLE · READ-ONLY</em>
          </div>
          <p className="run-hint">
            该项目没有可盘点的 closure 对象，或盘点请求失败：runtime 只能读取项目内的研究包，
            项目外的目录不会出现在这里。原因：{closureError}
          </p>
        </div>
      )}
      {closures && (
        <div className="closure-inventory">
          <div className="section-title">
            <span>CLOSURE PROFILES</span>
            <em>
              {(closures.present_profiles ?? []).length} / 3 · READ-ONLY
            </em>
          </div>
          {!closures.search_study.length && !closures.local_experiment.length && !closures.canonical_run.length && (
            <p className="run-hint">
              该项目目前没有可盘点的 closure 对象：canonical run、本地实验包与研究包都为空。
            </p>
          )}
          {closures.search_study.map((study) => (
            <article className="closure-row" key={`${study.profile}-${study.study_dir}`}>
              <b>search_study</b>
              <span>{study.dataset}</span>
              <em className={study.signed ? "is-ready" : study.underpowered ? "is-bad" : "is-warn"}>
                {study.closure_status}
              </em>
              <small>
                {study.underpowered ? "功效不足：加种子或收窄主张，而不是降阈值 · " : ""}
                next: {study.next}
              </small>
              {study.origin && study.origin !== "absent" && (
                <small className={study.origin === "stale" ? "is-bad" : ""}>
                  源自想法 {study.idea_id || "?"}（origin {study.origin}）
                  {study.idea_title ? ` · ${study.idea_title}` : ""}
                  {study.origin === "stale"
                    ? " · 研究已被重跑，这份数字不再回答当初那个假设"
                    : study.falsification
                      ? ` · 否证条件：${study.falsification}`
                      : ""}
                </small>
              )}
              {(study.verdict?.comparisons ?? []).map((item) => (
                <div className="verdict-line" key={item.comparison}>
                  <em className={`is-${item.state}`}>{item.state}</em>
                  <code>{item.comparison}</code>
                  <span>
                    {typeof item.mean_diff === "number" ? item.mean_diff.toFixed(4) : "—"}
                    {item.ci95
                      ? ` CI [${item.ci95[0].toFixed(4)}, ${item.ci95[1].toFixed(4)}]`
                      : " CI 不可用"}
                  </span>
                  {item.state === "undecidable" && (
                    <small>
                      {typeof item.mean_diff === "number" && item.mean_diff > 0
                        ? "点估计为正但区间跨零：不算提升，只是还没判定"
                        : "区间跨零：没有方向，不算结果"}
                      {typeof item.seeds_for_80pct === "number"
                        ? `；按当前效应量约需 ${item.seeds_for_80pct} 种子才可能判定`
                        : ""}
                    </small>
                  )}
                </div>
              ))}
              {study.verdict && study.verdict.available && (
                <small>
                  可判定 {study.verdict.decidable ?? 0} /{" "}
                  {(study.verdict.comparisons ?? []).length} 项；不可判定{" "}
                  {study.verdict.undecidable ?? 0} 项——不可判定是结果，不是失败。
                </small>
              )}
            </article>
          ))}
          {!!(closures.replication?.power_audit?.decided_at_lower_power ?? 0) && (
            <p className="run-hint">
              过早判定的代价：低功效下可判定的 {closures.replication?.power_audit?.decided_at_lower_power}{" "}
              条里，{closures.replication?.power_audit?.overturned} 条在更高功效上不再成立（反转率{" "}
              {((closures.replication?.power_audit?.reversal_rate ?? 0) * 100).toFixed(1)}%）——
              这不是失败，是"早下结论的价格"。
            </p>
          )}
          {(closures.replication?.overturned ?? []).map((item) => (
            <article
              className="closure-row"
              key={`${item.dataset}-${item.comparison}-${item.decided_at.directory}`}
            >
              <b>overturned</b>
              <span>{item.dataset}</span>
              <em className="is-bad">{item.comparison}</em>
              <small>{item.reason}</small>
              <small>
                {item.decided_at.state} @
                {item.decided_at.seeds} 种子 ={" "}
                {typeof item.decided_at.mean_diff === "number"
                  ? item.decided_at.mean_diff.toFixed(4)
                  : "—"}
                {" → "}
                {item.at_higher_power.state} @
                {item.at_higher_power.seeds} 种子 ={" "}
                {typeof item.at_higher_power.mean_diff === "number"
                  ? item.at_higher_power.mean_diff.toFixed(4)
                  : "—"}
              </small>
              <small>
                {item.decided_at.directory} 的低功效判定不能签成结论，已被{" "}
                {item.at_higher_power.directory} 取代。
              </small>
            </article>
          ))}
          {closures.replication?.groups?.map((group) => (
            <article className="closure-row" key={group.design_key}>
              <b>replication</b>
              <span>{group.datasets.join(" · ")}</span>
              <em
                className={
                  Object.values(group.comparisons ?? {}).some((row) => row.generalizes)
                    ? "is-ready"
                    : Object.values(group.comparisons ?? {}).some((row) => row.status === "conflict")
                      ? "is-bad"
                      : "is-warn"
                }
              >
                {group.datasets.length} 个数据集
              </em>
              <small>
                同一设计在各数据集上重跑；复现只数“真正判定的数据集”，不数“试过的数据集”。
              </small>
              {Object.entries(group.comparisons ?? {}).map(([name, row]) => (
                <div className="verdict-line" key={name}>
                  <em className={`is-${row.status === "consistent" ? "positive" : row.status === "conflict" ? "negative" : "undecidable"}`}>
                    {row.status}
                  </em>
                  <code>{name}</code>
                  <span>
                    {row.decided_in?.length
                      ? `${row.direction ?? ""} 判定于 ${row.decided_in.join("/")}`
                      : "没有数据集判定"}
                  </span>
                  {row.status === "undecided" ? (
                    <small>没有任何数据集给出排除零的区间</small>
                  ) : !row.generalizes && row.status !== "conflict" ? (
                    <small>其余数据集区间跨零：不能说它泛化</small>
                  ) : row.generalizes ? (
                    <small>每个数据集都同向判定：这才叫复现</small>
                  ) : null}
                </div>
              ))}
              {new Set(Object.values(group.seed_counts ?? {})).size > 1 && (
                <small>各数据集种子数不同：只在某个数据集训定，可能只是功效差异</small>
              )}
            </article>
          ))}
          {(closures.replication?.unreplicated ?? []).map((item) => (
            <article className="closure-row" key={item.design_key}>
              <b>replication</b>
              <span>{item.datasets.join(" · ")}</span>
              <em className="is-warn">unreplicated</em>
              <small>{item.reason}</small>
            </article>
          ))}
          {closures.replication?.boundary && (
            <p className="run-hint">{closures.replication.boundary}</p>
          )}
          {closures.local_experiment.map((item) => (
            <article className="closure-row" key={`${item.profile}-${item.experiment_id}`}>
              <b>local_experiment</b>
              <span>{item.experiment_id}</span>
              <em className={item.signed ? "is-ready" : "is-warn"}>{item.closure_status}</em>
              <small>
                panel={item.support_panel_status ?? "missing"} · next: {item.next}
              </small>
            </article>
          ))}
          {closures.canonical_run.map((item) => (
            <article className="closure-row" key={`${item.profile}-${item.run_id}`}>
              <b>canonical_run</b>
              <span>{item.run_id}</span>
              <em className={item.closure_status === "ready" ? "is-warn" : "is-idle"}>
                {item.closure_status}
              </em>
              <small>
                claim={item.has_signed_claim ? "signed" : "unsigned"} · sig=
                {item.has_signature ? (item.delegated ? "delegated" : "human") : "none"} · design=
                {item.study_design
                  ? `${item.study_design.status}/${item.study_design.ccfa_level || "—"}`
                  : "none"}{" "}
                · panel={item.support_panel_status ?? "missing"} · next: {item.next}
              </small>
              {item.study_design?.status === "incomplete" && (
                <small>
                  研究设计披露不完整，G2 不应冻结：{item.study_design.blockers.join(" · ")}
                </small>
              )}
              {item.claim_draft && (
                <div className="closure-draft">
                  <p>
                    <b>待签陈述</b>
                    <span>{item.claim_draft.statement}</span>
                  </p>
                  <small>
                    {item.claim_draft.assertion
                      ? `建议断言（最差种子下限）：${item.claim_draft.assertion}`
                      : "胶囊里没有逐种子指标，断言由人给出"}
                    {item.claim_draft.reading ? ` · ${item.claim_draft.reading}` : ""}
                  </small>
                  <GateCommandItem command={item.claim_draft.command} />
                  <small>
                    在项目根目录执行；statement 与 human-reason 必须由人改写后填写——复制命令不构成签署。
                  </small>
                </div>
              )}
            </article>
          ))}
          <p className="run-hint">
            三套 closure profile 的词汇不互换，都需要人签或人预先授权的 autopilot 策略；sig=delegated
            表示由策略代签，不是人签。策略由人写一次：`autopilot policy init` → `autopilot run
            --project … --run-id … --policy …`；越界即停。code.unchanged 与 power.sufficient
            是研究闭包条件——改了研究代码或种子数不足时，旧结论不能再被引用。网页不代为签署。
          </p>
        </div>
      )}
      <AutopilotStrip snapshot={autopilot} />
      {inventory && (
        <p className="run-hint">
          项目级实验链只读；执行、claim、closure、signature 仍由本地 CLI 完成（人，或人预先授权的 autopilot 策略）。
        </p>
      )}
    </section>
  );
}

function AutopilotStrip({ snapshot }: { snapshot: AutopilotSnapshot | null }) {
  if (!snapshot) return null;
  const idle = snapshot.status === "missing";
  return (
    <div className="closure-inventory">
      <div className="section-title">
        <span>AUTOPILOT</span>
        <em>{idle ? "NO POLICY RUN · READ-ONLY" : `${snapshot.status.toUpperCase()} · READ-ONLY`}</em>
      </div>
      {idle ? (
        <p className="run-hint">
          还没有策略运行记录。人写一次 `autopilot policy init` 后，`autopilot run` / `autopilot
          research` 可在边界内代跑 G1/G2/S5b/G5 并封装证据包；网页只读，不触发。
        </p>
      ) : (
        <>
          <div className="verdict-line">
            <em className={`is-${snapshot.status === "completed" ? "positive" : "undecidable"}`}>
              {snapshot.status}
            </em>
            <code>{snapshot.policy.policy_id ?? "—"}</code>
            <span>authorized_by {snapshot.policy.authorized_by ?? "—"}</span>
          </div>
          <div className="verdict-line">
            <em className={snapshot.bundle.verified ? "is-positive" : "is-undecidable"}>
              bundle
            </em>
            <code>{snapshot.bundle.path || "—"}</code>
            <span>
              claim {snapshot.claim.claim_id ?? "—"} · sig {snapshot.signature.signature_id ?? "—"}
              {snapshot.bundle.verified ? " · verified" : ""} {snapshot.bundle.artifact_count} files
            </span>
          </div>
          <div className="autopilot-steps">
            {snapshot.steps.map((step) => (
              <span key={step.step} title={step.detail} className={`is-${step.status}`}>
                {step.step}
              </span>
            ))}
          </div>
          {snapshot.reasons.length > 0 && <small>stopped: {snapshot.reasons.join(" · ")}</small>}
          <small>
            委托签名：{snapshot.delegation.not_a_human_signature ? "是按策略代签，不是人签" : "—"} · run{" "}
            {snapshot.run_id}
          </small>
        </>
      )}
    </div>
  );
}

function RuntimeLoopMap({ task }: { task: ResearchTask }) {
  const loop = task.runtimeLoop;
  if (!task.runtime) return null;
  const idea = loop?.idea;
  const design = loop?.design;
  const paper = loop?.paper;
  const figure = loop?.figure;
  const registry = loop?.claimRegistry;
  const closure = loop?.closure;
  const experiment = loop?.experiments?.[0];
  const experimentStages = experiment?.stages ?? {};
  const writing = loop?.writing;
  const externalGateText = Object.entries(writing?.externalGates ?? {})
    .map(([name, gate]) => `${name}=${gate.status ?? "unknown"}${typeof gate.issue_count === "number" && gate.issue_count > 0 ? `(${gate.issue_count})` : ""}`)
    .join(" · ");
  const pendingSlots = paper?.slots.filter((slot) => slot.status !== "bound_claim" && slot.status !== "bound" && slot.status !== "ready").length ?? 0;
  const rows = [
    {
      stage: "S1",
      label: "文献与 span",
      tone: task.coverage.spans > 0 ? "partial" : "missing",
      detail: `${task.coverage.sources} sources · ${task.coverage.spans} spans · ${task.coverage.gaps} gaps`,
      note: "抽象-only 只作线索；span 来自全文"
    },
    {
      stage: "S2–S3",
      label: "假设候选",
      tone: idea?.candidates.length ? (idea.status?.includes("need") ? "needs_human" : "partial") : "missing",
      detail: idea?.candidates.length
        ? `${idea.candidates.length} candidates · selection=${idea.selection ?? "unset"}`
        : "尚未产出 idea.json",
      note: idea?.candidates[0]?.title ?? "候选不是 claim；G1 由人选定"
    },
    ...(loop?.feedback
      ? [{
          stage: "S2·FB",
          label: "反馈约束消费",
          tone: loop.feedback.constraints_applied > 0 ? "ready" : "partial",
          detail: `${loop.feedback.constraints_applied} constraints · loops: ${loop.feedback.loops.join(", ") || "—"}`,
          note: loop.feedback.constraints_applied > 0
            ? "判定→生成的 provenance（loop_id/subject/effect 已写 idea.json）；stale 约束已被拒绝"
            : "capsule 带反馈投影但本 run 未消费约束（环关闭或无匹配候选）"
        }]
      : []),
    {
      stage: "S4",
      label: "实验设计",
      tone: design ? (design.status === "needs_human" ? "needs_human" : "partial") : "missing",
      detail: design
        ? `${design.status ?? "unknown"} · baseline=${design.baseline || "未填"} · metric=${design.primary_metric || "未填"} · seeds=${design.seeds ?? "—"}`
        : "尚未产出 experiment.json",
      note: design?.idea_id ? `idea_id=${design.idea_id} · G2 冻结前不能执行` : "设计草稿不替代 G2"
    },
    {
      stage: "S5",
      label: "运行与 EA",
      tone: experiment
        ? experimentStages.claim === "signed" ? "ready" : "needs_human"
        : task.run ? "partial" : "not_run",
      detail: experiment
        ? `${experiment.experiment_id} · evidence=${experimentStages.evidence ?? "—"} · claim=${experimentStages.claim ?? "—"}`
        : task.run
          ? `${task.run.id} · EA=${task.run.ea} · ${task.run.seeds} seeds`
          : "当前 job 未执行 S5",
      note: experiment?.next_action
        ? `next: ${experiment.next_action} · 执行与 claim 仍需本地人审`
        : "实验执行需本地审批；claim 不在浏览器签署"
    },
    {
      stage: "S6",
      label: "结果图",
      tone: figure ? (figure.schematic ? "partial" : "ready") : "missing",
      detail: figure
        ? `${figure.kind ?? "figure"} · ${figure.schematic ? "schematic" : "data_result"}`
        : "尚未产出 figure manifest",
      note: figure?.schematic ? "示意图不得当结果证据" : "结果图必须绑定 EA 与 manifest"
    },
    {
      stage: "S8–S12",
      label: "写作槽位",
      tone: writing?.status === "blocked"
        ? "blocked"
        : writing || pendingSlots ? "needs_human"
        : paper ? "ready" : "missing",
      detail: writing
        ? `audit=${writing.status ?? "unknown"} · submission_ready=${writing.submission_ready ? "true" : "false"} · ${writing.blockers?.length ?? 0} blockers`
        : paper
          ? `${paper.status ?? "unknown"} · ${paper.slots.length} slots · ${pendingSlots} pending`
          : "尚未产出 paper.json",
      note: [externalGateText ? `external: ${externalGateText}` : "", writing?.blockers?.[0] ?? ""].filter(Boolean).join(" · ") || "未签 claim 时结果为 pending_evidence"
    },
    {
      stage: "S13",
      label: "闭包",
      tone: experiment
        ? experimentStages.signature === "signed" ? "ready" : "blocked"
        : closure ? (closure.status === "ready" ? "ready" : "blocked") : "not_run",
      detail: experiment
        ? `closure=${experimentStages.closure ?? "—"} · signature=${experimentStages.signature ?? "—"}`
        : closure
          ? `${closure.status ?? "unknown"} · ${closure.checks ?? 0} checks · ${closure.unresolved?.length ?? 0} unresolved`
          : "尚未运行 closure",
      note: "closure 仍需人签，不自动导出"
    },
    {
      stage: "META",
      label: "自进化",
      tone: loop?.observationId || loop?.activePolicyId ? "partial" : "not_run",
      detail: [
        loop?.observationId ? `observation=${loop.observationId}` : "",
        loop?.activePolicyId ? `active=${loop.activePolicyId}` : "",
        loop?.appliedPolicy?.policy_id ? `applied=${loop.appliedPolicy.policy_id}` : "",
        loop?.activeLease?.lease_id
          ? `lease=${loop.activeLease.lease_id}${loop.activeLease.seeds ? ` · seeds=${loop.activeLease.seeds}` : ""}`
          : ""
      ].filter(Boolean).join(" · ") || "本 job 未关联 observation / active policy",
      note: "观测不是证据；active/lease 只能由 CLI 人审激活；这里只显示本 job 实际消费的 policy/lease"
    }
  ];
  return (
    <>
      <section className="context-section">
        <div className="section-title">
          <span>RESEARCH LOOP</span>
          <em>RUNTIME PROJECTION</em>
        </div>
      <div className="evidence-package-list">
        {rows.map((row) => (
          <article className={`evidence-package ${row.tone}`} key={row.stage}>
            <div className="evidence-package-head">
              <span className="evidence-package-stage">{row.stage}</span>
              <b>{row.label}</b>
              <span className={`badge ${packageTone(row.tone as EvidencePackage["status"])}`}>
                {packageStatusLabel[row.tone as EvidencePackage["status"]] ?? row.tone}
              </span>
            </div>
            <p>{row.detail}</p>
            <small>{row.note}</small>
          </article>
        ))}
      </div>
      {loop?.blockers?.length ? (
        <p className="run-hint">BLOCKERS · {loop.blockers.join(" · ")}</p>
      ) : null}
      {loop?.nextActions?.length ? (
        <details className="runtime-events loop-next" open>
          <summary>NEXT ACTIONS · {loop.nextActions.length}<span>人工门/下一步命令</span></summary>
          {loop.nextActions.map((action, index) => (
            <div className="runtime-event-row" key={`${action.gate ?? "next"}-${index}`}>
              <code>{action.gate ?? "NEXT"}</code>
              <span>{action.owner ?? "human"}</span>
              <em>{action.command}</em>
            </div>
          ))}
        </details>
      ) : null}
      {idea?.candidates[0] && (
        <details className="runtime-events">
          <summary>G1 候选详情 · {idea.candidates[0].idea_id}<span>打开查看假设与否证条件</span></summary>
          <div className="runtime-event-row">
            <code>{idea.candidates[0].idea_id}</code>
            <span>hypothesis</span>
            <em>{idea.candidates[0].hypothesis}</em>
          </div>
          {idea.candidates[0].falsification && (
            <div className="runtime-event-row">
              <code>kill</code>
              <span>falsification</span>
              <em>{idea.candidates[0].falsification}</em>
            </div>
          )}
        </details>
      )}
      {idea?.ranked?.length ? (
        <details className="runtime-events" open>
          <summary>
            G1 SHORTLIST · {idea.ranked.length}
            <span>advisory only · human G1</span>
          </summary>
          {idea.ranked.map((item, index) => (
            <div className="runtime-event-row" key={`${item.idea_id ?? "idea"}-${index}`}>
              <code>#{item.rank ?? index + 1} {item.idea_id ?? "IDEA"}</code>
              <span>{item.testability ?? "testability unset"}</span>
              <em>
                evidence={item.evidence_count ?? "—"} · sources={item.source_count ?? "—"} · prior=
                {item.prior_art_scope ?? "none"} · novelty={item.novelty_status ?? "unverified"} ·
                kill={item.has_kill_criteria ? "yes" : "no"} · contrast=
                {item.has_contrast ? "yes" : "no"}
              </em>
            </div>
          ))}
        </details>
      ) : null}
      {registry && (
        <p className="run-hint">
          Claim registry：{registry.entries} entries · coverage={registry.coverage_rate ?? "unknown"} · verified anchors={registry.verified_anchor_rows ?? "unknown"}。它不是 claim 签名。
        </p>
      )}
      <p className="run-hint">
        闭环节点只来自当前 job 的真实产物；缺失表示未产出，不表示通过。人工门仍在 RUN / CLI。
      </p>
    </section>
      <ProjectExperimentInventoryPanel />
    </>
  );
}

function EvidenceContext({ task }: { task: ResearchTask }) {
  const actions = useWorkspaceStore((state) => state.actions);
  const claim = task.evidence.find((item) => item.kind === "claim");
  const closure = task.gates.find((gate) => gate.id === "G5");
  const packages = task.evidencePackages ?? [];
  const packageReady = packages.filter((item) => item.status === "ready").length;
  const packageAction = packages.filter((item) =>
    ["partial", "needs_human", "needs_signature"].includes(item.status)
  ).length;
  const packageMissing = packages.filter((item) =>
    ["missing", "blocked", "not_run"].includes(item.status)
  ).length;
  const nodes = [
    { label: "SOURCE HIT", value: `${task.coverage.sources} sources`, state: task.coverage.sources ? "ok" : "idle" },
    { label: "SPAN", value: `${task.coverage.spans} located`, state: task.coverage.spans ? "ok" : "idle" },
    { label: "CLAIM", value: claim ? (claim.status === "signed" ? "signed" : "unsigned") : "none", state: claim?.status === "signed" ? "ok" : claim ? "warn" : "idle" },
    { label: "EA", value: task.run ? task.run.ea : "not sealed", state: task.run ? "ok" : "idle" },
    { label: "CLOSURE", value: closure?.status === "pass" ? "pass" : task.run ? "locked" : "n/a", state: closure?.status === "pass" ? "ok" : task.run ? "warn" : "idle" }
  ];

  const kindLabel: Record<EvidenceItem["kind"], string> = {
    gap: "GAP",
    hypothesis: "HYPOTHESIS",
    claim: "CLAIM"
  };

  return (
    <div className="context-stack">
      {task.runtime && <RuntimeLoopMap task={task} />}
      <section className="context-card">
        <div className="card-label">
          <span>EVIDENCE CHAIN</span>
          <em>SPAN-ONLY</em>
        </div>
        <div className="chain">
          {nodes.map((node, index) => (
            <div className={`chain-node ${node.state}`} key={node.label}>
              <span>{node.label}</span>
              <b>{node.value}</b>
              {index < nodes.length - 1 && <i className="chain-link" />}
            </div>
          ))}
        </div>
        <div className="coverage-grid">
          <div><b>{task.coverage.spans}</b><span>SPANS</span></div>
          <div><b>{task.coverage.gaps}</b><span>GAPS</span></div>
          <div><b>{task.coverage.abstractOnly}</b><span>ABSTRACT-ONLY</span></div>
          <div><b>{claim?.status === "signed" ? 1 : 0}</b><span>SIGNED CLAIMS</span></div>
        </div>
      </section>

      <section className="context-section evidence-package-section">
        <div className="section-title">
          <span>EVIDENCE PACKAGES</span>
          <em>{packages.length ? `${packages.length} PACKAGES` : "NO RUNTIME PACKAGES"}</em>
        </div>
        {packages.length ? (
          <>
            <div className="evidence-package-summary">
              <span><b>{packageReady}</b> 就绪</span>
              <span><b>{packageAction}</b> 待处理</span>
              <span><b>{packageMissing}</b> 缺失/阻断</span>
            </div>
            <div className="evidence-package-list">
              {packages.map((item) => (
                <article className={`evidence-package ${item.status}`} key={item.id}>
                  <div className="evidence-package-head">
                    <span className="evidence-package-stage">{item.stage}</span>
                    <b>{item.label}</b>
                    <span className={`badge ${packageTone(item.status)}`}>
                      {packageStatusLabel[item.status]}
                    </span>
                  </div>
                  <p>{item.detail}</p>
                  <small>{item.boundary}</small>
                  {item.refs.length > 0 && (
                    <div className="evidence-package-refs">
                      {item.refs.slice(0, 4).map((ref) => <code key={ref}>{ref}</code>)}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </>
        ) : (
          <p className="context-empty">
            运行本地 runtime 任务后，这里会显示 S1–S13 每个证据包的状态（就绪 / 待人工 / 待签署 / 缺失）。
            静态预览不产生真实证据包。
          </p>
        )}
      </section>

      <section className="context-section">
        <div className="section-title">
          <span>REGISTRY</span>
          <em>{task.evidence.length} ITEMS</em>
        </div>
        <div className="evidence-list">
          {task.evidence.length ? (
            task.evidence.map((item) => (
              <article className={`evidence-card ${item.kind}`} key={item.id}>
                <div className="evidence-head">
                  <span className="evidence-kind">{kindLabel[item.kind]}</span>
                  <span className="evidence-id">{item.id}</span>
                  <span className={`badge ${item.status === "signed" ? "ok" : item.status === "unsigned" ? "warn" : item.status === "open" ? "warn" : "idle"}`}>
                    {item.status}
                  </span>
                </div>
                <p>{item.text}</p>
                <div className="evidence-foot">
                  <span>{item.scope}</span>
                  <span>{item.refs.join(" · ")}</span>
                </div>
                {item.note && <small>{item.note}</small>}
              </article>
            ))
          ) : (
            <p className="context-empty">还没有 span 或 gap。先运行一次检索；摘要-only 来源不会进入这里。</p>
          )}
        </div>
      </section>

      <section className="context-section">
        <div className="section-title">
          <span>ADMISSION</span>
          <em>HUMAN GATES</em>
        </div>
        <div className="gate-list">
          {task.gates.map((gate) => (
            <div className="gate-row" key={gate.id}>
              <span className={`gate-dot ${statusTone(gate.status)}`} />
              <span className="gate-name"><b>{gate.id}</b><small>{gate.reason}</small></span>
              <span className={`badge ${statusTone(gate.status)}`}>{gate.status.replace("_", " ")}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="context-footnote">
        <Icon name="lock" size={12} />
        <span>claim 不进入检索层；没有全文时只保留 SourceHit 线索，不生成 span。</span>
      </div>
      <button type="button" className="context-link" onClick={() => actions.openSettings("lineage")}>
        查看沿袭与变更影响
        <Icon name="branch" size={12} />
      </button>
      <button type="button" className="context-link" onClick={() => actions.setContextTab("run")}>
        回到运行面板
        <Icon name="arrow" size={12} />
      </button>
    </div>
  );
}

function EvaluationContext({ task }: { task: ResearchTask }) {
  const actions = useWorkspaceStore((state) => state.actions);
  const evaluation = task.evaluation;
  const engineering = evaluation.interventions.filter((item) => item.kind === "engineering").length;
  const domain = evaluation.interventions.filter((item) => item.kind === "domain").length;
  const total = engineering + domain;
  const domainPercent = total ? Math.round((domain / total) * 100) : 0;
  const hiddenUsed = evaluation.hiddenAccessCount > 0;
  const auditTone = evaluation.audit === "pass" ? "ok" : evaluation.audit === "flagged" ? "bad" : "warn";
  const baselineDelta =
    evaluation.baselinePaper && evaluation.baselineReproduced
      ? ((evaluation.baselineReproduced - evaluation.baselinePaper) / evaluation.baselinePaper) * 100
      : null;
  const selectionRisk = evaluation.validationSelections > 10;

  return (
    <div className="context-stack">
      <section className="context-card eval-overview">
        <div className="card-label">
          <span>EVAL / PROTOCOL</span>
          <em>隔离 · 演示数据</em>
        </div>
        <div className="eval-stages">
          <div className="eval-stage is-done">
            <span>01</span>
            <b>Improve</b>
            <small>train / val only</small>
          </div>
          <div className={`eval-stage${hiddenUsed ? " is-done" : " is-locked"}`}>
            <span>02</span>
            <b>Evaluate</b>
            <small>held-out once</small>
          </div>
          <div className={`eval-stage${evaluation.audit !== "pending" ? " is-done" : " is-locked"}`}>
            <span>03</span>
            <b>Audit</b>
            <small>process evidence</small>
          </div>
        </div>
        <div className="eval-keyrow">
          <span>HELD-OUT ACCESS</span>
          <b className={hiddenUsed ? "is-warn" : ""}>{evaluation.hiddenAccessCount}/1</b>
        </div>
        <div className="eval-keyrow">
          <span>EVAL RULE</span>
          <b>{evaluation.evalRuleHash}</b>
        </div>
        <div className="eval-keyrow">
          <span>AUDIT</span>
          <span className={`badge ${auditTone}`}>{evaluation.audit}</span>
        </div>
        <div className="eval-actions">
          <button
            type="button"
            className="control primary"
            onClick={actions.submitEvaluation}
            disabled={!task.run || hiddenUsed || task.auto.running}
            title={!task.run ? "先完成 S5 run" : hiddenUsed ? "held-out 已消耗" : "提交一次最终评估"}
          >
            <Icon name="lock" size={12} />
            {hiddenUsed ? "已提交评估" : "提交独立评估"}
          </button>
          <button
            type="button"
            className="control"
            onClick={actions.runEvaluationAudit}
            disabled={!hiddenUsed || evaluation.audit !== "pending"}
            title={!hiddenUsed ? "先提交独立评估" : "检查验证选择与评价规则"}
          >
            <Icon name="shield" size={12} />
            {evaluation.audit === "pending" ? "运行过程审计" : "审计已完成"}
          </button>
        </div>
      </section>

      <section className="context-section">
        <div className="section-title">
          <span>REPRODUCED BASELINE</span>
          <em>NOT PAPER NUMBER</em>
        </div>
        <div className="eval-baseline">
          <div><span>PAPER</span><b>{evaluation.baselinePaper ?? "—"}</b></div>
          <div><span>REPRODUCED</span><b>{evaluation.baselineReproduced ?? "—"}</b></div>
          <div><span>Δ REPRO</span><b>{baselineDelta === null ? "—" : `${baselineDelta.toFixed(1)}%`}</b></div>
        </div>
        <p className="context-empty">改进只与复现基线比较；复现差异不隐藏，也不冒充论文原数字。</p>
      </section>

      <section className="context-section">
        <div className="section-title">
          <span>SELECTION PRESSURE</span>
          <em>{evaluation.validationSelections} VAL</em>
        </div>
        <div className={`eval-warning${selectionRisk ? " is-warn" : ""}`}>
          <Icon name={selectionRisk ? "alert" : "info"} size={12} />
          <span>
            {selectionRisk
              ? "验证选择次数偏高；审计会检查是否出现验证集过拟合。"
              : "验证选择仍在可控范围；独立测试不回流到改进阶段。"}
          </span>
        </div>
        <dl className="artifact-kv compact">
          <dt>Train cost</dt>
          <dd>{evaluation.trainCost === null ? "—" : `${evaluation.trainCost} GPU·h`}</dd>
          <dt>Inference</dt>
          <dd>{evaluation.inferenceCost === null ? "—" : `${evaluation.inferenceCost}× baseline`}</dd>
          <dt>Seeds</dt>
          <dd>{task.run?.seeds ?? "—"}</dd>
        </dl>
      </section>

      <section className="context-section">
        <div className="section-title">
          <span>METHOD MIX</span>
          <em>{domain}/{total} DOMAIN</em>
        </div>
        {total ? (
          <>
            <div className="eval-mix" title={`${domainPercent}% domain`}>
              <span style={{ width: `${domainPercent}%` }} />
            </div>
            <div className="eval-counts">
              <span><i className="is-domain" />domain {domain}</span>
              <span><i className="is-engineering" />engineering {engineering}</span>
            </div>
            <ul className="eval-interventions">
              {evaluation.interventions.slice(0, 5).map((item) => (
                <li key={item.id}>
                  <span className={`badge ${item.kind === "domain" ? "ok" : "idle"}`}>{item.kind}</span>
                  <span>
                    <b>{item.label}</b>
                    <small>{item.note}</small>
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="context-empty">还没有登记干预台账；示例任务预置了工程/领域干预，新任务需在接入真实运行时后由 run diff 与实验记录写入。</p>
        )}
      </section>

      <div className="context-footnote">
        <Icon name="shield" size={12} />
        <span>独立评估与审计是控制面演示：真实系统必须由服务端隔离 held-out、冻结评价规则并保存完整轨迹。</span>
      </div>
    </div>
  );
}

function EvolutionRuntimeContext() {
  const [observations, setObservations] = useState<EvolutionObservations | null>(null);
  const [active, setActive] = useState<EvolutionActive | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    Promise.all([loadEvolutionObservations(8), loadEvolutionActive()])
      .then(([observationBody, activeBody]) => {
        if (!alive) return;
        setObservations(observationBody);
        setActive(activeBody);
      })
      .catch((reason) => {
        if (alive) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      alive = false;
    };
  }, []);
  const summary = observations?.summary;
  const activePolicy = active?.active;
  return (
    <section className="context-card evolution-overview">
      <div className="card-label">
        <span>RUNTIME EVOLUTION</span>
        <em>READ ONLY</em>
      </div>
      <div className="run-numbers">
        <span>OBSERVATIONS <b>{summary?.count ?? 0}</b></span>
        <span>FIXTURE <b>{summary?.fixture_count ?? 0}</b></span>
      </div>
      <div className="run-numbers">
        <span>ACTIVE <b>{activePolicy?.policy_id ?? "none"}</b></span>
        <span>TARGET <b>{activePolicy?.target ?? "—"}</b></span>
        <span>LEASE <b>{activePolicy?.lease_state ?? "—"}</b></span>
        <span>AUTO-DEMOTE <b>{active?.auto_deactivations ?? 0}</b></span>
      </div>
      {activePolicy && activePolicy.lease_state && activePolicy.lease_state !== "active" && (
        <p className="run-hint">
          源租约在消费时复查为 {activePolicy.lease_state}；该参数已自动停用并回到 incumbent。
          降级可自动，升级仍需人工签署。
        </p>
      )}
      {active?.expired && <p className="run-hint">active policy 已过期；下次 runtime job 不会应用它。</p>}
      {activePolicy && (
        <p className="run-hint">
          patch={JSON.stringify(activePolicy.patch ?? {})} · expires={activePolicy.expires_at ?? "unknown"}
        </p>
      )}
      {observations?.observations.length ? (
        <div className="runtime-events">
          {observations.observations.slice(0, 4).map((item) => (
            <div className="runtime-event-row" key={item.observation_id ?? item.created_at ?? item.topic}>
              <code>{item.observation_id ?? "OBS"}</code>
              <span>{item.q0_status ?? item.status ?? "unknown"}</span>
              <em>
                {item.topic ?? "—"} · max_sources={item.max_sources ?? "—"} · {item.fixture_mode ? "fixture" : "non-fixture"}
              </em>
            </div>
          ))}
        </div>
      ) : (
        <p className="context-empty">
          {error ? `runtime 不可达：${error}` : "还没有 runtime observation；跑完一次 job 后自动写入，但不会成为证据。"}
        </p>
      )}
      <p className="run-hint">
        闭环命令（CLI 人审）：<code>rsi observations suggest</code> → real-trial → admit → <code>rsi active activate</code>。
        浏览器只读；MCP/runtime 不提供激活或签核。
      </p>
    </section>
  );
}

function EvolutionContext({ task }: { task: ResearchTask }) {
  const actions = useWorkspaceStore((state) => state.actions);
  const candidate = task.evolution.candidate;
  const status = candidate?.status;
  const steps = [
    { label: "candidate", done: Boolean(candidate), denied: status === "rejected" },
    { label: "dry-run", done: Boolean(candidate) },
    { label: "public / hidden", done: Boolean(candidate) },
    { label: "human admit", done: status === "active" || status === "rolled_back", denied: status === "rejected" },
    { label: "lease", done: status === "active", revoked: status === "rolled_back" },
    { label: "consume / trace", done: status === "active" || status === "rolled_back" }
  ];

  return (
    <div className="context-stack">
      <RsiStoryPanel />
      <GovernancePanel />
      <HostModelPanel />
      <EvolutionRuntimeContext />
      <section className="context-card evolution-overview">
        <div className="card-label">
          <span>LOCAL DEMO CANDIDATE</span>
          <em>演示数据</em>
        </div>
        <div className="evolution-state">
          <span className={`badge ${status === "active" ? "ok" : status === "rejected" ? "bad" : status ? "warn" : "idle"}`}>
            {task.evolution.status.toUpperCase()}
          </span>
          <span>{candidate ? candidate.id : "NO CANDIDATE"}</span>
        </div>
        <p className="evolution-copy">
          上方是真实 RSI 账本；这里是当前任务的本地演示候选。改进只在策略层提案；claim、evidence、gate、rubric、export、signature 是不可写面。准入必须经过 dry-run、public/hidden 与人工。
        </p>
        <div className="evolution-steps">
          {steps.map((step) => (
            <div className={`evolution-step${step.done ? " is-done" : ""}${step.denied ? " is-denied" : ""}${step.revoked ? " is-revoked" : ""}`} key={step.label}>
              <span>{step.done ? <Icon name="check" size={10} /> : step.denied ? <Icon name="close" size={10} /> : <i />}</span>
              {step.label}
            </div>
          ))}
        </div>
      </section>

      {candidate ? (
        <section className="context-section">
          <div className="section-title">
            <span>CANDIDATE</span>
            <em>{candidate.id}</em>
          </div>
          <article className="candidate-detail">
            <div className="candidate-target">
              <Icon name="spark" size={14} />
              <b>{candidate.target}</b>
            </div>
            <dl className="artifact-kv">
              <dt>Patch</dt>
              <dd>{candidate.patch}</dd>
              <dt>Why</dt>
              <dd>{candidate.rationale}</dd>
              <dt>Predicted</dt>
              <dd>{candidate.predicted}</dd>
              <dt>Evidence</dt>
              <dd>{candidate.evidence}</dd>
              <dt>Lease</dt>
              <dd>{candidate.lease}</dd>
            </dl>
            <div className="candidate-actions">
              {status === "pending" && (
                <>
                  <button type="button" className="action-button primary" onClick={actions.approveCandidate}>批准</button>
                  <button type="button" className="action-button danger" onClick={actions.rejectCandidate}>拒绝</button>
                </>
              )}
              {status === "active" && (
                <button type="button" className="action-button danger" onClick={actions.rollbackHarness}>撤销租约</button>
              )}
            </div>
          </article>
        </section>
      ) : (
        <section className="context-section">
          <div className="section-title">
            <span>CANDIDATE</span>
            <em>EMPTY</em>
          </div>
          <div className="context-empty-card">
            <Icon name="evolution" size={22} />
            <p>运行全自动到 META 阶段会生成一个受治理候选；也可以直接生成静态候选查看流程。</p>
            <button type="button" className="action-button" onClick={actions.previewCandidate}>
              模拟生成候选
            </button>
          </div>
        </section>
      )}

      <section className="context-section">
        <div className="section-title">
          <span>IMMUTABLE SURFACES</span>
          <em>READ-ONLY</em>
        </div>
        <div className="surface-grid">
          {["claim", "evidence", "gate", "rubric", "export", "signature"].map((surface) => (
            <span key={surface}><Icon name="lock" size={10} />{surface}</span>
          ))}
        </div>
      </section>

      <section className="context-section">
        <div className="section-title">
          <span>TRACE</span>
          <em>{task.evolution.history.length} EVENTS</em>
        </div>
        {task.evolution.history.length ? (
          <div className="history-list">
            {[...task.evolution.history].reverse().map((event, index) => (
              <div className="history-row" key={`${event.at}-${index}`}>
                <span>{event.at}</span>
                <p>{event.text}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="context-empty">暂无准入记录。候选被拒绝时负结果也会保留。</p>
        )}
      </section>

      <div className="context-footnote">
        <Icon name="shield" size={12} />
        <span>RSI 只能提案；能力增益必须绑定 public/hidden/regression 证据与人工租约。</span>
      </div>
    </div>
  );
}

function briefStage(task: ResearchTask): AutoStage | null {
  const running = task.autoStages.find((stage) => stage.status === "running");
  if (running) return running;
  return task.autoStages[Math.min(task.stage, Math.max(0, task.autoStages.length - 1))] ?? null;
}

function briefNext(task: ResearchTask): string {
  const closure = task.gates.find((gate) => gate.id === "G5");
  const claim = task.evidence.find((item) => item.kind === "claim");
  if (task.status === "done") return "任务已完成；复核证据链后再进入导出。";
  if (task.auto.running && task.auto.paused) {
    return task.auto.gate === "claim"
      ? "全自动停在 claim 人工门；请作者签核，或回到证据链补证据。"
      : "全自动已暂停；检查当前阶段后继续。";
  }
  if (!claim || claim.status !== "signed") {
    return task.coverage.spans > 0
      ? "证据已到 span 层；下一步是 G1 收敛与 claim 人工签署。"
      : "先跑文献调研，至少拿到可定位的 span，再进入假设收敛。";
  }
  if (!closure || closure.status !== "pass") {
    return "claim 已签；下一步运行 closure，修复未绑定槽位后再导出。";
  }
  const next = task.autoStages.find((stage) => stage.status === "pending");
  return next ? `继续 ${next.label}。` : "证据已闭合；复核签名与导出清单。";
}

function briefMarkdown(task: ResearchTask): string {
  const stage = briefStage(task);
  const claim = task.evidence.find((item) => item.kind === "claim");
  const closure = task.gates.find((gate) => gate.id === "G5");
  const blockers = task.gates.filter((gate) => gate.status === "needs_human" || gate.status === "blocked");
  const reviews = task.reviewPack;
  return [
    `# ${task.name}`,
    "",
    "## Mission",
    task.goal || "（未填写 mission）",
    "",
    "## State",
    `- stage: ${stage?.label ?? "未开始"} (${stage?.status ?? "pending"})`,
    `- status: ${task.status}`,
    `- coverage: ${task.coverage.sources} sources / ${task.coverage.spans} spans / ${task.coverage.gaps} gaps`,
    `- claim: ${claim?.status ?? "none"}`,
    `- closure: ${closure?.status ?? "not_started"}`,
    "",
    "## Blockers",
    ...(blockers.length ? blockers.map((gate) => `- ${gate.id}: ${gate.reason}`) : ["- none recorded"]),
    "",
    "## Next",
    briefNext(task),
    "",
    "## Evidence boundary",
    "- This brief is a state summary, not a Claim, EA, Verdict, or signature.",
    reviews ? `- last review: ${reviews.summary} (${reviews.generatedAt})` : "- last review: none",
  ].join("\n");
}

function BriefContext({ task }: { task: ResearchTask }) {
  const actions = useWorkspaceStore((state) => state.actions);
  const stage = briefStage(task);
  const claim = task.evidence.find((item) => item.kind === "claim");
  const closure = task.gates.find((gate) => gate.id === "G5");
  const blockers = task.gates.filter((gate) => gate.status === "needs_human" || gate.status === "blocked");
  const reviews = task.reviewPack;
  const artifacts = [
    task.run?.id ? `run ${task.run.id}` : "",
    task.run?.ea ? `EA ${task.run.ea}` : "",
    reviews?.id ? `review ${reviews.id}` : "",
  ].filter(Boolean);
  const copy = () => {
    const text = briefMarkdown(task);
    if (!navigator.clipboard) {
      actions.notify("当前浏览器不支持复制；请在桌面浏览器重试");
      return;
    }
    void navigator.clipboard.writeText(text)
      .then(() => actions.notify("Project Brief 已复制为 Markdown"))
      .catch(() => actions.notify("复制失败；请检查浏览器权限"));
  };
  return (
    <div className="context-stack">
      <section className="context-section">
        <div className="section-title">
          <span>PROJECT BRIEF</span>
          <button type="button" className="context-link" onClick={copy}>复制 Markdown</button>
        </div>
        <div className="brief-card">
          <span className="brief-kicker">MISSION</span>
          <h3>{task.name}</h3>
          <p>{task.goal || "还没有 mission；先写清目标、成功条件和边界。"}</p>
          <div className="brief-kpis">
            <span><b>{stage?.label ?? "未开始"}</b>STAGE</span>
            <span><b>{task.coverage.spans}</b>SPANS</span>
            <span><b>{claim?.status ?? "none"}</b>CLAIM</span>
            <span><b>{closure?.status ?? "not_started"}</b>CLOSURE</span>
          </div>
        </div>
      </section>

      <section className="context-section">
        <div className="section-title"><span>BLOCKERS</span><em>{blockers.length}</em></div>
        {blockers.length ? (
          <div className="brief-list">
            {blockers.map((gate) => (
              <div className="brief-row" key={gate.id}>
                <b>{gate.id} · {gate.status === "needs_human" ? "等待人工" : "阻塞"}</b>
                <p>{gate.reason}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="brief-row"><b>当前没有登记的 blocker</b><p>仍需检查 claim、closure 与导出签名。</p></div>
        )}
      </section>

      <section className="context-section">
        <div className="section-title"><span>NEXT</span><em>{task.auto.running ? "AUTO" : "MANUAL"}</em></div>
        <div className="brief-next">{briefNext(task)}</div>
      </section>

      <section className="context-section">
        <div className="section-title"><span>DECISIONS &amp; ARTIFACTS</span><em>{artifacts.length} ARTIFACTS</em></div>
        <div className="brief-list">
          <div className="brief-row"><b>G2 协议</b><p>{task.protocolFrozen
            ? (task.runtime ? "runtime 证据：ProtocolCard 已冻结" : "演示推进；真实 G2 由 CLI 冻结")
            : "待人工冻结；网页不代为冻结"}</p></div>
          <div className="brief-row"><b>claim</b><p>{claim?.status === "signed" ? "已签署（证据来自 CLI）；不是浏览器生成" : "待人工签署；写作与导出保持锁定"}</p></div>
          <div className="brief-row"><b>最近 review</b><p>{reviews ? `${reviews.summary} · ${reviews.generatedAt}` : "尚未运行 Review Pack"}</p></div>
          {artifacts.map((artifact) => <div className="brief-row" key={artifact}><p>{artifact}</p></div>)}
        </div>
      </section>

      <div className="context-footnote">
        <Icon name="shield" size={12} />
        <span>BRIEF 只是状态摘要；不创建 Claim/EA，不改变 gate，也不代替作者签名。</span>
      </div>
    </div>
  );
}

export function ContextPanel() {
  const task = useWorkspaceStore(selectCurrentTask);
  const tab = useWorkspaceStore((state) => state.ui.contextTab);
  const contextOpen = useWorkspaceStore((state) => state.ui.contextOpen);
  const actions = useWorkspaceStore((state) => state.actions);
  if (!task) return null;
  const profile = modelProfile(task.model);
  const runtimeCard = [...task.messages]
    .reverse()
    .find((entry) => entry.card?.type === "runtime-run")?.card as RuntimeCard | undefined;
  const runtimeBacked = Boolean(task.runtime ?? runtimeCard);

  return (
    <aside className={`context-panel${contextOpen ? " is-open" : ""}`} aria-label="运行上下文">
      <div className="context-head">
        <div className="context-tabs" role="tablist" aria-label="上下文视图">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={tab === item.id ? "is-on" : ""}
              onClick={() => actions.setContextTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="icon-button context-collapse"
          onClick={() => actions.setUI({ contextCollapsed: true })}
          aria-label="收起运行上下文"
          title="收起运行上下文"
        >
          <Icon name="chevron" size={13} />
        </button>
        <button
          type="button"
          className="icon-button context-close"
          onClick={() => actions.setUI({ contextOpen: false })}
          aria-label="关闭运行上下文"
        >
          <Icon name="close" size={13} />
        </button>
      </div>
      <div className="context-body">
        {/* key={task.id}: RunContext 等 tab 面板持有本地表单状态（runtimeSource/seeds/文件路径…），
            不加 key 时切换任务会沿用上一个任务的表单值，可能带着 A 任务的 seeds 去 run B 任务。 */}
        {tab === "brief" && <BriefContext key={task.id} task={task} />}
        {tab === "run" && <RunContext key={task.id} task={task} />}
        {tab === "evidence" && <EvidenceContext key={task.id} task={task} />}
        {tab === "projects" && (
          <div className="context-stack">
            <ProjectExperimentInventoryPanel />
          </div>
        )}
        {tab === "evolution" && <EvolutionContext key={task.id} task={task} />}
        {tab === "eval" && <EvaluationContext key={task.id} task={task} />}
      </div>
      <div className="context-foot">
        <span>
          {runtimeBacked
            ? `local runtime · ${runtimeCard?.route ?? runtimeCard?.taskType ?? "auto"}`
            : `${profile.short} · ${profile.provider}`}
        </span>
        <span>
          {runtimeBacked
            ? `RUNTIME · ${(task.runtime?.source ?? runtimeCard?.source ?? "fixture").toUpperCase()}`
            : "演示数据 · 无 worker"}
        </span>
      </div>
    </aside>
  );
}
