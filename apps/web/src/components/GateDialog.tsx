import { useEffect, useMemo, useRef, useState } from "react";
import { GATE_CONTRACTS, type HumanGateId } from "../domain/gateContracts";
import { CLI_ONLY_NOTE } from "../domain/gateCommands";
import { claimSignatureLabel } from "../domain/claimSignature";
import { gateDecisionQuote, humanTurns, turnsForStage } from "../domain/humanTurns";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { GateCommandItem } from "./HumanGateCommand";
import { Icon } from "./Icon";

/** Which transcript stage owns each gate's human decision. */
const GATE_STAGE: Record<HumanGateId, string> = {
  G1: "S2–S3",
  G2: "S4",
  S5b: "S5b",
  G5: "S13–S16"
};

/**
 * Human-gate dialog for G1 (候选收敛) / G2 (协议冻结) / G5 (闭合签署).
 *
 * This is the "对话" layer the claim gate already had (ClaimGateDialog), extended
 * to every human gate: the dialog asks the human to CHOOSE (select a candidate /
 * confirm the protocol / acknowledge the closure checks) and to write the
 * human_reason the CLI will require. It then builds the exact CLI command with
 * that reason filled in, plus a copyable decision record.
 *
 * Hard boundary (AGENTS.md §7): the dialog never performs the gate. It writes
 * nothing to gates/evidence/claim; the signature only happens in the local CLI.
 * S5b/Q0 keep routing to ClaimGateDialog, which owns the claim-specific paths.
 */
export function GateDialog() {
  const open = useWorkspaceStore((state) => state.ui.gateDialog);
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const [ideaId, setIdeaId] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [copied, setCopied] = useState(false);
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    setIdeaId("");
    // The human often states their decision in the transcript already
    // (「G1：收敛到 H1…」); seeding the reason with their own words keeps the
    // dialog honest — questions are never pre-filled (gateDecisionQuote rule).
    setReason("");
    const quote = open ? gateDecisionQuote(humanTurns(task?.messages ?? []), GATE_STAGE[open as HumanGateId], open) : null;
    if (quote) setReason(quote.text);
    setConfirmed(false);
    setCopied(false);
    closeRef.current?.focus();
    const dialog = dialogRef.current;
    if (!dialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const focusables = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", onKeyDown);
    return () => {
      dialog.removeEventListener("keydown", onKeyDown);
      restoreRef.current?.focus?.();
    };
  }, [open]);

  const candidates = useMemo(
    () => task?.evidence.filter((item) => item.kind === "hypothesis") ?? [],
    [task]
  );
  // The person's own words in this session, projected per stage (design/145).
  const stageId = open ? GATE_STAGE[open as HumanGateId] : null;
  const stageTurns = useMemo(
    () => (open && task ? turnsForStage(humanTurns(task.messages), stageId ?? "") : []),
    [open, task, stageId]
  );
  const decisionQuote = useMemo(
    () => (open ? gateDecisionQuote(humanTurns(task?.messages ?? []), stageId ?? "", open) : null),
    [open, task, stageId]
  );

  if (!open) return null;
  const contract = GATE_CONTRACTS[open as HumanGateId];
  if (!contract) return null;

  const claim = task?.evidence.find((item) => item.kind === "claim");
  const claimLabel = claimSignatureLabel(claim);
  const closureGate = task?.gates.find((gate) => gate.id === "G5");

  const decision = {
    ideaId: open === "G1" ? ideaId || undefined : undefined,
    humanReason: reason.trim() || undefined
  };
  const command = contract.command({}, decision);

  const decisionRecord = JSON.stringify(
    {
      gate: contract.id,
      decision: open === "G1" ? { selected: decision.ideaId ?? null } : { confirmed },
      human_reason: reason.trim() || null,
      decided_at: new Date().toISOString(),
      origin: "browser-dialog",
      note: "浏览器收集的决策草稿：真实生效必须执行面板中的 CLI 命令；网页不代签。"
    },
    null,
    2
  );

  const copyRecord = () => {
    if (!confirmed) {
      actions.notify("先勾选确认项，再复制决策记录");
      return;
    }
    if (!reason.trim()) {
      actions.notify("human_reason 是 CLI 必填项；先写下你的理由");
      return;
    }
    if (!navigator.clipboard) {
      actions.notify("当前浏览器不支持复制；请在桌面浏览器重试");
      return;
    }
    void navigator.clipboard
      .writeText(decisionRecord)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => actions.notify("复制失败；请检查浏览器权限"));
  };

  const readyToRecord = confirmed && Boolean(reason.trim()) && (open !== "G1" || Boolean(ideaId));

  return (
    <div
      className="modal-layer claim-gate-layer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) actions.closeGateDialog();
      }}
    >
      <section
        className="modal gate-dialog-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="gate-dialog-title"
        ref={dialogRef}
      >
        <div className="modal-head">
          <div>
            <span className="eyebrow">{contract.eyebrow}</span>
            <h2 id="gate-dialog-title">{contract.title}</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭人工门对话框"
            onClick={actions.closeGateDialog}
            ref={closeRef}
          >
            <Icon name="close" size={14} />
          </button>
        </div>
        <p className="modal-lede">{contract.lede}</p>

        <section className="claim-gate-block is-contract">
          <b>这个门在后端由什么保证</b>
          <ul className="gate-contract-list">
            {contract.contract.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <p className="claim-gate-meta">owner: {contract.owner}</p>
        </section>

        <section className="claim-gate-block is-decision">
          <b>人的决策（选择 + 理由）</b>

          {open === "G1" && (
            <>
              <p className="gate-dialog-q">① 收敛到哪个候选？</p>
              {candidates.length ? (
                <div className="gate-choices" role="radiogroup" aria-label="候选假设">
                  {candidates.map((item) => (
                    <label key={item.id} className={`gate-choice${ideaId === item.id ? " is-on" : ""}`}>
                      <input
                        type="radio"
                        name="gate-candidate"
                        checked={ideaId === item.id}
                        onChange={() => setIdeaId(item.id)}
                      />
                      <span className="gate-choice-id">{item.id}</span>
                      <span className="gate-choice-text">{item.text}</span>
                    </label>
                  ))}
                </div>
              ) : (
                <label className="gate-input-row">
                  <span>候选 ID</span>
                  <input
                    type="text"
                    value={ideaId}
                    placeholder="如 IDEA-02（来自 idea.json）"
                    onChange={(event) => setIdeaId(event.target.value)}
                  />
                </label>
              )}
              <p className="gate-dialog-q">② 为什么收敛到它？（写入 human_reason）</p>
            </>
          )}

          {open === "G2" && (
            <>
              <dl className="gate-protocol">
                <div><dt>假设</dt><dd>{task?.protocol?.hypothesis ?? "（尚无协议草案）"}</dd></div>
                <div><dt>基线</dt><dd>{task?.protocol?.baseline ?? "—"}</dd></div>
                <div><dt>主指标</dt><dd>{task?.protocol?.metric ?? "—"}</dd></div>
                <div><dt>seeds</dt><dd>{task?.protocol?.seeds ?? "—"}</dd></div>
                <div><dt>对照</dt><dd>{(task?.protocol?.controls ?? []).join("、") || "—"}</dd></div>
              </dl>
              <p className="gate-dialog-q">① 确认冻结：主指标、seeds 与对照此后不可改写。</p>
            </>
          )}

          {open === "G5" && (
            <>
              <div className="gate-readiness">
                <div className={`gate-ready-row${claimLabel.state === "signed-cli" || claimLabel.state === "signed-import" ? " is-ok" : ""}`}>
                  <span>claim</span>
                  <b>{claimLabel.badge}</b>
                </div>
                <div className="gate-ready-row">
                  <span>run</span>
                  <b>{task?.run ? `${task.run.id} · ${task.run.status}` : "无 run 记录"}</b>
                </div>
                <div className={`gate-ready-row${closureGate ? " is-note" : ""}`}>
                  <span>closure</span>
                  <b>{closureGate?.reason ?? "未登记"}</b>
                </div>
              </div>
              <p className="gate-dialog-q">① 确认 closure 检查已逐项复核，导出清单由本人签署。</p>
            </>
          )}

          {stageTurns.length > 0 && (
            <div className="gate-quote">
              <b>本会话里人的原话</b>
              {stageTurns.map((turn) => (
                <button
                  type="button"
                  key={turn.id}
                  className={`gate-quote-line${decisionQuote?.id === turn.id ? " is-decision" : ""}`}
                  onClick={() => actions.focusMessage(turn.id)}
                  title="定位到会话中这条发言"
                >
                  <i>{turn.at}</i>
                  {turn.text.length > 90 ? `${turn.text.slice(0, 90)}…` : turn.text}
                </button>
              ))}
            </div>
          )}
          <label className="gate-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            <span>
              {open === "G1"
                ? "我已人工核对这个候选的证据支持与查新，确认收敛。"
                : open === "G2"
                  ? "我确认按当前协议冻结；此后改协议需要重新走 G2。"
                  : "我确认 closure 检查已逐项复核；这份导出签名由我在本地 CLI 产生。"}
            </span>
          </label>
          <p className="gate-dialog-q">{open === "G1" ? "②" : "②"} human_reason（CLI 必填）</p>
          <textarea
            className="gate-reason"
            rows={2}
            value={reason}
            placeholder="写下你的核对过程与理由；空理由会被 CLI 拒绝"
            onChange={(event) => setReason(event.target.value)}
          />
          <button
            type="button"
            className={`text-button gate-record${readyToRecord ? " is-ready" : ""}`}
            onClick={copyRecord}
            title="复制决策记录 JSON（g1-decision 草稿；真实生效仍需执行 CLI 命令）"
          >
            <Icon name={copied ? "check" : "copy"} size={12} />
            {copied ? "已复制决策记录" : "复制决策记录 JSON"}
          </button>
        </section>

        {__STATIC_ONLY__ && (
          <section className="claim-gate-block is-demo">
            <b>在网页上应用决策（演示预览）</b>
            <p>
              演示时不必离开工作台：点下面的按钮，这条门会按你的决策在<b>页面内存</b>里推进——会话出现签署卡片、证据链与面板随之点亮。
              不产生真实签名或决策文件，刷新页面即回待签；真实签署仍以下方的 CLI 命令为准。
            </p>
            <button
              type="button"
              className="solid-button"
              disabled={!readyToRecord}
              onClick={() => actions.applyDemoGateDecision(open)}
            >
              应用决策（演示预览）→
            </button>
            {!readyToRecord && (
              <p className="claim-gate-error">
                {open === "G1" && !ideaId
                  ? "先选择收敛的候选。"
                  : !confirmed
                    ? "先勾选确认项。"
                    : "先写下 human_reason。"}
              </p>
            )}
          </section>
        )}

        <section className="claim-gate-block">
          <b>真实生效（本地 CLI）</b>
          <p>决策与理由已填入命令；在终端执行后，产物（g1-decision.json / protocol-card.json / closure-signature）写回项目目录。占位符替换为本项目的实际路径。</p>
          <GateCommandItem command={command} />
          <p className="claim-gate-note">{CLI_ONLY_NOTE}</p>
        </section>

        <footer className="modal-foot">
          <button type="button" className="text-button" onClick={actions.closeGateDialog}>关闭</button>
        </footer>
      </section>
    </div>
  );
}
