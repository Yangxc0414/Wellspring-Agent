import { useState } from "react";
import type { ReactNode } from "react";
import type { Card } from "../domain/types";
import { runtimeUrl } from "../adapters/runtimeApi";
import { experimentApproveCommands, protocolFreezeCommand } from "../domain/gateCommands";
import { claimSignatureLabel } from "../domain/claimSignature";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { usePreviewStore } from "../state/previewStore";
import { HumanGateCommand } from "./HumanGateCommand";
import { Icon } from "./Icon";

function failureSuggestion(
  errorType: string,
  retryable: boolean,
  fallback?: string
): string {
  if (errorType === "OpenAlexError") {
    return "OpenAlex 配额或网络受限：设置 OPENALEX_API_KEY 和/或 OPENALEX_EMAIL 后重试，或改用 local / CC-BY 来源；不要把 fixture 当真实结果。";
  }
  if (errorType === "ModelRequiredError") {
    return "在设置页为必需模块绑定 runtime profile 并配置 API key，然后重试；这是配置问题，不是瞬时错误。";
  }
  if (errorType === "SupportAuditError") {
    return "支持审稿发现矛盾引用：检查 support-audit.json 的句子级引用，修正证据或结论；不要签署当前 claim。";
  }
  if (retryable) {
    return "瞬时检索或网络失败：检查网络后重试，或切换到其他来源。";
  }
  return fallback || "打开 failure.json 查看诊断，修复输入或环境后重跑。";
}

function CardHead({ label, meta }: { label: string; meta?: string }) {
  return (
    <div className="artifact-head">
      <span>{label}</span>
      {meta && <em>{meta}</em>}
    </div>
  );
}

function Actions({ children }: { children: ReactNode }) {
  return <div className="artifact-actions">{children}</div>;
}

function ActionButton({
  children,
  onClick,
  variant = "quiet",
  disabled = false
}: {
  children: ReactNode;
  onClick: () => void;
  variant?: "primary" | "quiet" | "danger";
  disabled?: boolean;
}) {
  return (
    <button type="button" className={`action-button ${variant}`} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

export function ArtifactCard({ card }: { card: Card }) {
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const [gateRevealed, setGateRevealed] = useState(false);
  const autoBusy = Boolean(task?.auto.running);
  const evaluated = (task?.evaluation.hiddenAccessCount ?? 0) > 0;

  if (card.type === "plan") {
    return (
      <article className="artifact">
        <CardHead label="PLAN / RETRIEVAL" meta="span-only" />
        <ol className="query-list">
          {card.queries.map((query, index) => (
            <li key={query}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {query}
            </li>
          ))}
        </ol>
        <dl className="artifact-kv">
          <dt>范围</dt>
          <dd>{card.scope}</dd>
          <dt>预算</dt>
          <dd>{card.budget}</dd>
        </dl>
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton variant="primary" onClick={actions.runResearch} disabled={autoBusy}>
            开始检索
          </ActionButton>
          <ActionButton onClick={actions.focusComposer}>调整问题</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "sources") {
    return (
      <article className="artifact">
        <CardHead label="COVERAGE / SOURCES" meta={`${card.items.length} sources`} />
        <ul className="source-list">
          {card.items.map((item, index) => (
            <li key={item.title}>
              <span className="source-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="source-copy">
                <b>{item.title}</b>
                <small>{item.meta}</small>
              </span>
              <span className={`badge ${item.status === "ok" ? "ok" : "warn"}`}>
                {item.status === "ok" ? "FULL" : "ABSTRACT"}
              </span>
            </li>
          ))}
        </ul>
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看 gap</ActionButton>
          <ActionButton onClick={actions.runResearch} disabled={autoBusy}>扩展检索</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "idea") {
    return (
      <article className="artifact">
        <CardHead label="GAP → HYPOTHESES" meta="S2–S3" />
        <div className="gap-block">
          <span>OPEN GAP</span>
          <p>{card.gap}</p>
        </div>
        <ul className="candidate-list">
          {card.candidates.map((candidate) => (
            <li key={candidate.id}>
              <span className="candidate-id">{candidate.id}</span>
              <span>{candidate.text}</span>
            </li>
          ))}
        </ul>
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton variant="primary" onClick={actions.designExperiment} disabled={autoBusy}>
            送入实验设计
          </ActionButton>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看证据链</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "protocol") {
    const frozen = task?.protocolFrozen ?? false;
    return (
      <article className="artifact">
        <CardHead label="PROTOCOL / S4" meta={frozen ? "DRAFT · 演示已推进" : "DRAFT"} />
        <p className="artifact-lede">{card.hypothesis}</p>
        <dl className="artifact-kv">
          <dt>Baseline</dt>
          <dd>{card.baseline}</dd>
          <dt>主指标</dt>
          <dd>{card.metric}</dd>
          <dt>Seeds</dt>
          <dd>{card.seeds}</dd>
          <dt>对照</dt>
          <dd>{card.controls.join(" · ")}</dd>
        </dl>
        <div className="artifact-status-row">
          <span className="badge warn">待人工冻结</span>
          <span>G2 由人工在终端冻结；冻结后不得改写主指标、对照与 seeds</span>
        </div>
        <Actions>
          <ActionButton variant="primary" onClick={() => setGateRevealed((open) => !open)} disabled={autoBusy}>
            {gateRevealed ? "收起 G2 命令" : "G2 人工冻结命令"}
          </ActionButton>
          <ActionButton onClick={actions.runExperiment} disabled={!frozen || autoBusy || evaluated}>运行 3 seeds</ActionButton>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>证据链</ActionButton>
        </Actions>
        {gateRevealed && (
          <HumanGateCommand
            title="G2 · 待人工冻结"
            detail="在终端核对设计、切分与停止规则后运行下面的命令；网页与 runtime 都不会代为冻结。"
            commands={[
              protocolFreezeCommand(),
              ...experimentApproveCommands()
            ]}
          />
        )}
      </article>
    );
  }

  if (card.type === "run") {
    const claim = task?.evidence.find((item) => item.kind === "claim");
    const claimLabel = claimSignatureLabel(claim);
    const delta = card.mean - card.baseline;
    return (
      <article className="artifact">
        <CardHead label={`RUN / ${card.id}`} meta="EA SEALED" />
        <div className="metric-grid">
          <div>
            <span>MEAN T80</span>
            <b>{card.mean}<small> h</small></b>
          </div>
          <div>
            <span>BASELINE</span>
            <b>{card.baseline}<small> h</small></b>
          </div>
          <div className="metric-delta">
            <span>DELTA</span>
            <b>+{delta}<small> h</small></b>
          </div>
        </div>
        <dl className="artifact-kv compact">
          <dt>Dataset</dt>
          <dd>{card.dataset}</dd>
          <dt>Seeds</dt>
          <dd>{card.seeds}</dd>
          <dt>EA</dt>
          <dd>{card.ea}</dd>
          <dt>Claim</dt>
          <dd>{claimLabel.short}</dd>
        </dl>
        <p className="artifact-note">数值是演示数据，仅用于展示 EA → claim 的边界，不作为真实材料实验结论。</p>
        <Actions>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看 EA</ActionButton>
          <ActionButton variant="primary" onClick={actions.signClaim}>
            {claimLabel.state === "unsigned" || claimLabel.state === "missing"
              ? "签署 claim · 人工门"
              : "查看 claim 签署来源"}
          </ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "gate") {
    const claim = task?.evidence.find((item) => item.kind === "claim");
    const claimLabel = claimSignatureLabel(claim);
    const passed = claimLabel.state === "signed-cli" || claimLabel.state === "signed-import";
    return (
      <article className={`artifact gate-card${passed ? " is-pass" : ""}${claimLabel.demo ? " is-demo" : ""}`}>
        <CardHead label={card.gate} meta={claimLabel.badge} />
        <div className="gate-title">
          <span className="gate-icon">
            <Icon name={passed ? "check" : "lock"} size={16} />
          </span>
          <div>
            <b>
              {claimLabel.demo
                ? "演示态预览 · claim 未真实签署"
                : passed
                  ? "claim 已签署（来源见证据面板）"
                  : card.title}
            </b>
            <p>{claimLabel.detail}</p>
          </div>
        </div>
        <Actions>
          <ActionButton variant="primary" onClick={actions.signClaim}>
            {claimLabel.state === "unsigned" || claimLabel.state === "missing"
              ? "签署 claim · 人工门"
              : "查看 claim 签署来源"}
          </ActionButton>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看证据链</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "evolution") {
    const candidate =
      task?.evolution.candidate?.id === card.candidate.id ? task.evolution.candidate : card.candidate;
    const status = candidate.status;
    return (
      <article className="artifact evolution-card">
        <CardHead label={`EVOLUTION / ${candidate.id}`} meta={status.toUpperCase()} />
        <div className="evolution-target">
          <span>TARGET</span>
          <b>{candidate.target}</b>
          <span className={`badge ${status === "active" ? "ok" : status === "rejected" ? "bad" : "warn"}`}>
            {status}
          </span>
        </div>
        <dl className="artifact-kv">
          <dt>Patch</dt>
          <dd>{candidate.patch}</dd>
          <dt>Rationale</dt>
          <dd>{candidate.rationale}</dd>
          <dt>Predicted</dt>
          <dd>{candidate.predicted}</dd>
          <dt>Evidence</dt>
          <dd>{candidate.evidence}</dd>
          <dt>Lease</dt>
          <dd>{candidate.lease}</dd>
        </dl>
        <p className="artifact-note">不可写层：claim / evidence / gate / rubric / export / signature。候选只能改策略参数。</p>
        <Actions>
          {status === "pending" && (
            <>
              <ActionButton variant="primary" onClick={actions.approveCandidate}>
                批准候选
              </ActionButton>
              <ActionButton variant="danger" onClick={actions.rejectCandidate}>
                拒绝并保留负结果
              </ActionButton>
            </>
          )}
          {status === "active" && (
            <ActionButton variant="danger" onClick={actions.rollbackHarness}>
              撤销租约并回滚
            </ActionButton>
          )}
          <ActionButton onClick={() => actions.setContextTab("evolution")}>查看自进化</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "review-pack") {
    return (
      <article className="artifact review-pack-card">
        <CardHead label="REVIEW PACK" meta={`${card.reviewers} reviewers · advisory`} />
        <p className="review-pack-summary">{card.summary}</p>
        <ul className="review-pack-findings">
          {card.findings.map((item) => (
            <li key={item.id} data-status={item.status}>
              <span className="review-pack-status">{item.status.toUpperCase()}</span>
              <span className="review-pack-copy">
                <b>{item.label}</b>
                <small>{item.reviewer} · {item.summary}</small>
              </span>
            </li>
          ))}
        </ul>
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看证据链</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "skill-use") {
    return (
      <article className="artifact skill-use-card">
        <div className="skill-use-head">
          <span className="skill-use-mark"><Icon name="spark" size={13} /></span>
          <div className="skill-use-copy">
            <span className="skill-use-kicker">
              SKILL / {card.mode === "auto" ? "按需加载" : "手动加载"}
            </span>
            <b>{card.name}</b>
            <small>{card.reason}</small>
          </div>
          <span className="skill-use-version">v{card.version}</span>
        </div>
        <p className="skill-use-summary">{card.summary}</p>
        {card.steps.length > 0 && (
          <ul className="skill-use-steps">
            {card.steps.map((step) => (
              <li key={step.label} data-status={step.status}>
                <span className="skill-use-dot">
                  {step.status === "done" ? <Icon name="check" size={9} /> : step.status === "blocked" ? <Icon name="lock" size={9} /> : <i />}
                </span>
                <span className="skill-use-step-copy">
                  <b>{step.label}</b>
                  <small>{step.note}</small>
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="skill-use-note">{card.note}</p>
        <Actions>
          <ActionButton onClick={() => actions.openOverlay("skillsOpen")}>查看 Skill</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "skill") {
    return (
      <article className="artifact skill-card">
        <CardHead label={`SKILL / ${card.skillId}`} meta={`v${card.version} · ${card.status}`} />
        <div className="skill-summary">
          <span className="skill-mark"><Icon name="spark" size={13} /></span>
          <p>{card.summary}</p>
        </div>
        <ul className="skill-steps">
          {card.steps.map((step) => (
            <li key={step.label} data-status={step.status}>
              <span className="skill-step-dot">
                {step.status === "done" ? <Icon name="check" size={10} /> : step.status === "blocked" ? <Icon name="lock" size={10} /> : <i />}
              </span>
              <span className="skill-step-copy">
                <b>{step.label}</b>
                <small>{step.note}</small>
              </span>
              <span className="skill-step-state">{step.status.toUpperCase()}</span>
            </li>
          ))}
        </ul>
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton variant="primary" onClick={() => actions.invokeSkill(card.skillId)} disabled={autoBusy}>
            重新调用
          </ActionButton>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看证据链</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type === "writing") {
    const bound = card.slots.filter((slot) => slot.status === "bound").length;
    const locked = card.slots.filter((slot) => slot.status === "locked").length;
    return (
      <article className="artifact writing-card">
        <CardHead label="WRITING / SLOT BINDING" meta={`${bound}/${card.slots.length} bound`} />
        <ul className="writing-slots">
          {card.slots.map((slot) => (
            <li key={slot.id} data-status={slot.status}>
              <span className="slot-id">{slot.id}</span>
              <span className="slot-copy">
                <b>{slot.label}</b>
                <small>{slot.note}</small>
              </span>
              <span className={`slot-badge ${slot.status}`}>
                {slot.status === "bound" ? "BOUND" : slot.status === "pending" ? "PENDING" : "LOCKED"}
              </span>
            </li>
          ))}
        </ul>
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton variant="primary" onClick={actions.prepareWriting} disabled={autoBusy}>
            刷新槽位绑定
          </ActionButton>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>检查证据边界</ActionButton>
          {locked > 0 && <span className="writing-lock-note">{locked} 个槽位等待已签 claim</span>}
        </Actions>
      </article>
    );
  }

  if (card.type === "runtime-run") {
    const taskFailed = card.status === "failed" || card.taskStatus === "failed";
    const taskNeedsHuman = !taskFailed && card.status === "completed" && card.taskStatus === "needs_human";
    const statusTone = taskFailed ? "bad" : taskNeedsHuman ? "warn" : card.status === "completed" ? "ok" : "warn";
    const packages = card.evidencePackages ?? [];
    const readyPackages = packages.filter((item) => item.status === "ready").length;
    const actionPackages = packages.filter((item) =>
      ["partial", "needs_human", "needs_signature"].includes(item.status)
    ).length;
    const blockedPackages = packages.filter((item) =>
      ["missing", "blocked", "not_run"].includes(item.status)
    ).length;
    const sourceLabel = card.source === "fixture"
      ? "fixture 演示"
      : card.source === "openalex"
        ? "OpenAlex 摘要"
        : card.source === "real_corpus"
          ? "CC-BY 正文"
          : "runtime";
    const provenanceLabel = card.source === "openalex"
      ? "OpenAlex 摘要（无全文）"
      : card.source === "local"
        ? "本地全文"
        : card.source === "real_corpus"
          ? "CC-BY 真实正文"
          : card.fixtureMode
            ? "fixture（不可引用）"
            : "runtime";
    const openArtifact = async (artifact: { path: string; url: string }) => {
      try {
        const response = await fetch(runtimeUrl(artifact.url));
        if (!response.ok) throw new Error(String(response.status));
        const blob = await response.blob();
        const name = artifact.path.split("/").pop() || "artifact";
        const extension = name.split(".").pop()?.toLowerCase() ?? "";
        const type = extension === "md"
          ? "text/markdown"
          : extension === "json"
            ? "application/json"
            : extension === "svg"
              ? "image/svg+xml"
              : "text/plain";
        usePreviewStore.getState().addFile(new File([blob], name, { type }), artifact.path);
      } catch {
        actions.notify("产物预览失败；可直接打开链接或在本地 job 目录查看");
      }
    };
    return (
      <article className="artifact tool-card">
        <CardHead label="LOCAL API / RUNTIME" meta={taskFailed ? "FAILED" : taskNeedsHuman ? "NEEDS HUMAN" : card.status.toUpperCase()} />
        <div className="tool-head">
          <span className="tool-server"><Icon name="terminal" size={14} />local runtime</span>
          <code>{card.jobId || "queued"}</code>
        </div>
        <dl className="artifact-kv compact">
          <dt>Status</dt>
          <dd><span className={`badge ${statusTone}`}>{taskFailed ? "failed" : taskNeedsHuman ? "needs human" : card.status}</span></dd>
          <dt>Source</dt>
          <dd>{sourceLabel}</dd>
          <dt>Task</dt>
          <dd>{card.taskType ?? "—"}{card.route ? ` → ${card.route}` : ""}</dd>
          <dt>Task status</dt>
          <dd>{card.taskStatus ?? "—"}</dd>
          <dt>Flow</dt>
          <dd>{card.flowMode ?? "—"}{card.stoppedAt ? ` · stopped at ${card.stoppedAt}` : ""}</dd>
          <dt>Run</dt>
          <dd>{card.runId ?? "—"}</dd>
          <dt>Job dir</dt>
          <dd><code>{card.jobDir ?? "—"}</code></dd>
          <dt>Stage</dt>
          <dd>{card.stage ?? "—"} · {card.events} events</dd>
          <dt>Provenance</dt>
          <dd>{provenanceLabel}</dd>
          <dt>Evidence packages</dt>
          <dd>
            {packages.length
              ? `${readyPackages} 就绪 · ${actionPackages} 待处理 · ${blockedPackages} 缺失/阻断`
              : "—"}
          </dd>
        </dl>
        {card.lastEvent && <p className="artifact-note">最近事件：{card.lastEvent}</p>}
        {card.eventLog && card.eventLog.length > 0 && (
          <details className="runtime-events">
            <summary>
              事件流 · {card.eventLog.length} 条
              <span>打开查看阶段边界</span>
            </summary>
            {card.eventLog.slice(-10).map((event) => (
              <div className="runtime-event-row" key={event.seq}>
                <code>#{event.seq}</code>
                <span>{event.stage ?? event.type}</span>
                <em>{event.message}</em>
              </div>
            ))}
          </details>
        )}
        {card.warnings.length > 0 && <p className="artifact-note">{card.warnings.slice(0, 4).join(" · ")}</p>}
        {card.error && !card.failure && <p className="artifact-note">{card.error}</p>}
        {card.failure && (
          <div className="artifact-next failure">
            <b>
              任务失败 · {card.failure.error_type || "error"} ·{" "}
              {card.failure.retryable ? "可重试" : "需人工修复"}
            </b>
            <p>
              {failureSuggestion(
                card.failure.error_type || "",
                Boolean(card.failure.retryable),
                card.failure.suggested_action
              )}
            </p>
            {card.failure.error && <pre>{card.failure.error}</pre>}
          </div>
        )}
        {card.status === "completed" && card.stoppedAt === "G1" && card.jobDir && (
          <div className="artifact-next">
            <b>严格流程停在 G1</b>
            <p>先在终端人工选择候选并生成 G1 决策，然后在 RUN 面板填入路径续跑。</p>
            <pre>{`python -m research_agent flow g1 \\
  --idea-file ${card.jobDir}/idea.json \\
  --idea-id <IDEA-ID> \\
  --human-reason "选择该候选的理由" \\
  --output-dir ${card.jobDir}`}</pre>
          </div>
        )}
        {card.status === "completed" && card.stoppedAt === "G2" && card.jobDir && (
          <div className="artifact-next">
            <b>严格流程停在 G2</b>
            <p>先检查 S4 设计，再用 CLI 冻结 ProtocolCard；runtime 不会代签 G2。</p>
            <pre>{`python -m research_agent protocol freeze-design \\
  --design ${card.jobDir}/experiment.json \\
  --limitation "本次适用范围" \\
  --human-reason "已核对 baseline / 指标 / seeds" \\
  --output-dir ${card.jobDir}/protocol`}</pre>
          </div>
        )}
        {card.status === "completed"
          && !card.stoppedAt
          && card.jobDir
          && card.gates?.some((gate) => gate.gate === "S5" && gate.status === "needs_human") && (
          <div className="artifact-next">
            <b>下一步：人签 claim</b>
            <p>RunCapsule/EA 已生成；结果仍保持 pending。请在终端核对 EA 与数值后签署 claim，再回到 RUN 面板填入 claim 路径续跑。</p>
            <pre>{`python -m research_agent run claim \\
  --capsule ${card.jobDir}/run/run-capsule.json \\
  --ea ${card.jobDir}/run/ea.json \\
  --statement "<claim-draft.json 中的 statement>" \\
  --human-reason "已核对 EA 与指标" \\
  --scope S5/demo/${card.dataset || "iris"} \\
  --output-dir ${card.jobDir}/claim`}</pre>
            <p>续跑时在 RUN 面板填入本 job 的 run 目录，复用原 RunCapsule/EA；不要再执行新的 S5。</p>
          </div>
        )}
        {card.status === "completed"
          && !card.stoppedAt
          && card.artifacts.some((artifact) => artifact.path.endsWith("claim/claim.json"))
          && card.gates?.some((gate) => gate.gate === "G5" && gate.status === "blocked") && (
          <div className="artifact-next">
            <b>下一步：补全 Closure</b>
            <p>claim 已绑定，但 closure 仍有未通过项。打开下方 closure-report.json 查看具体缺口；常见项是 citation.related 未绑定 bibliography。</p>
          </div>
        )}
        {card.status === "completed"
          && !card.stoppedAt
          && card.jobDir
          && card.artifacts.some((artifact) => artifact.path.endsWith("claim/claim.json"))
          && card.gates?.some((gate) => gate.gate === "G5" && gate.status === "needs_human") && (
          <div className="artifact-next">
            <b>Closure 已就绪，等待导出签核</b>
            <p>closure report 已通过；导出仍需人工签核。runtime 不提供 sign 端点。</p>
            <pre>{`python -m research_agent closure sign \\
  --report ${card.jobDir}/closure/closure-report.json \\
  --demo ${card.jobDir}/demo.json \\
  --claim ${card.jobDir}/claim/claim.json \\
  --human-reason "已复核 closure 与导出清单" \\
  --output-dir ${card.jobDir}/closure-signature`}</pre>
          </div>
        )}
        {card.status === "completed"
          && card.artifacts.some((artifact) => artifact.path.endsWith("support-audit.json")) && (
          <p className="artifact-note">
            {card.supportAudit?.counts
              ? `Support audit（${card.supportAudit.method || "unknown"}）：${card.supportAudit.counts.supported ?? 0} supported · ${card.supportAudit.counts.partial ?? 0} partial · ${card.supportAudit.counts.contradicted ?? 0} contradicted · ${card.supportAudit.counts.insufficient ?? 0} insufficient。`
              : "Support audit 已生成："}
            句子级判定是 advisory（production 下 contradicted 会阻断），不修改 claim/gate；打开 support-audit.json 查看逐句 verdict。
          </p>
        )}
        {card.status === "completed"
          && card.artifacts.some((artifact) => artifact.path.endsWith("manuscript-audit.json")) && (
          <p className="artifact-note">
            中文投稿工作稿：`manuscript.md`；审计见 `manuscript-audit.json`（submission_ready
            以文件中的 blockers 为准，不保证期刊录用）。
          </p>
        )}
        {card.artifacts.length > 0 ? (
          <ul className="source-list">
            {card.artifacts.map((artifact, index) => (
              <li key={artifact.path} className="runtime-artifact">
                <span className="source-index">{String(index + 1).padStart(2, "0")}</span>
                <a href={runtimeUrl(artifact.url)} target="_blank" rel="noopener noreferrer">{artifact.path}</a>
                <small>{artifact.kind} · {Math.round(artifact.size / 1024)} KB</small>
                {(artifact.kind === "text" || artifact.kind === "data" || artifact.kind === "figure") && (
                  <button type="button" className="artifact-preview-btn" onClick={() => void openArtifact(artifact)}>
                    预览
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="artifact-note">运行中；artifacts 会在 job 完成后出现在这里。</p>
        )}
        <p className="artifact-note">{card.note}</p>
        <Actions>
          <ActionButton onClick={() => actions.setContextTab("evidence")}>查看证据包</ActionButton>
          <ActionButton onClick={() => actions.openSettings("runtime")}>打开执行环境</ActionButton>
        </Actions>
      </article>
    );
  }

  if (card.type !== "tool") return null;
  const liveCall = task?.toolCalls.find((call) => call.tool === card.tool && call.args === card.args);
  const status = liveCall?.status ?? card.status;
  return (
    <article className="artifact tool-card">
      <CardHead label="TOOL CALL / MCP" meta={status.toUpperCase()} />
      <div className="tool-head">
        <span className="tool-server">
          <Icon name="terminal" size={14} />
          {card.server}
        </span>
        <code>{card.tool}</code>
      </div>
      <dl className="artifact-kv compact">
        <dt>Arguments</dt>
        <dd>{card.args}</dd>
        <dt>Security</dt>
        <dd>read-only · 结果视为 UNTRUSTED</dd>
        {liveCall?.result && (
          <>
            <dt>Result</dt>
            <dd>{liveCall.result}</dd>
          </>
        )}
      </dl>
      <Actions>
        {status === "proposed" && (
          <ActionButton variant="primary" onClick={() => actions.openOverlay("pluginsOpen")}>
            处理审批
          </ActionButton>
        )}
        {status !== "proposed" && <span className="tool-outcome">状态：{status}</span>}
      </Actions>
    </article>
  );
}
