import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { claimSignCommand, CLI_ONLY_NOTE } from "../domain/gateCommands";
import { claimSignatureLabel, parseSignedClaim } from "../domain/claimSignature";
import { selectCurrentTask, useWorkspaceStore } from "../state/workspaceStore";
import { GateCommandItem } from "./HumanGateCommand";
import { Icon } from "./Icon";

/**
 * Q0 / S5b human gate. A browser click must never create a signature, but it must
 * give visible, actionable feedback. Three legitimate paths are offered here:
 *   1. copy the CLI command and sign locally (the only way a real signature appears);
 *   2. import the claim.json produced by `run claim` — read-only, no write-back;
 *   3. in the static Pages demo only, preview the post-signature UI, labelled DEMO.
 * Path 3 is gated on __STATIC_ONLY__ so the product workbench never offers to fake a gate.
 */
export function ClaimGateDialog() {
  const open = useWorkspaceStore((state) => state.ui.claimGateOpen);
  const task = useWorkspaceStore(selectCurrentTask);
  const actions = useWorkspaceStore((state) => state.actions);
  const [error, setError] = useState("");
  const [imported, setImported] = useState("");
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    setError("");
    setImported("");
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

  if (!open) return null;

  const claim = task?.evidence.find((item) => item.kind === "claim");
  const label = claimSignatureLabel(claim);
  // In the static demo the preview may create a demo claim itself, so the button
  // must be enabled even when the session has no claim row yet. In the product
  // workbench there is no preview button at all (__STATIC_ONLY__ gate below).
  const pending = __STATIC_ONLY__
    ? label.state !== "signed-demo"
    // A delegated (autopilot) signature still leaves the human gate open, so it must
    // keep the gate actionable rather than counting as "already signed".
    : Boolean(
        claim &&
          (claim.status !== "signed" || claim.origin === "demo" || claim.origin === "delegated")
      );

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setImported("");
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const result = parseSignedClaim(parsed, claim?.scope);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setImported(result.record.claimId);
      actions.importSignedClaim(result.record, result.scopeMismatch);
    } catch {
      setError("JSON 解析失败；请选择 run claim 产出的 claim.json");
    }
  };

  return (
    <div
      className="modal-layer claim-gate-layer"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) actions.closeClaimGate();
      }}
    >
      <section
        className="modal claim-gate-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="claim-gate-title"
        ref={dialogRef}
      >
        <div className="modal-head">
          <div>
            <span className="eyebrow">Q0 / S5b · HUMAN GATE</span>
            <h2 id="claim-gate-title">claim 签署：网页不代签</h2>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="关闭人工门面板"
            onClick={actions.closeClaimGate}
            ref={closeRef}
          >
            <Icon name="close" size={14} />
          </button>
        </div>
        <p className="modal-lede">
          这一步是人工门。静态演示构建里可以在网页上签署（页面内存预览，刷新即回）；真实签署用下面的 CLI 命令，或导入已签署产物。两条路都不会让浏览器产生真实签名。
        </p>

        <div className="claim-gate-state">
          <div className="claim-gate-state-head">
            <b>当前 claim</b>
            <span className={`claim-gate-badge${label.demo ? " is-demo" : ""}`}>{label.badge}</span>
          </div>
          {claim ? (
            <>
              <p className="claim-gate-text">{claim.text}</p>
              <p className="claim-gate-meta">scope: {claim.scope} · refs: {claim.refs.join(", ") || "—"}</p>
            </>
          ) : (
            <p className="claim-gate-text">
              {__STATIC_ONLY__
                ? task?.run
                  ? "这条任务已有 RunCapsule 与 EA，但还没有 claim draft；用下方演示签署查看签署后的界面即可。"
                  : "这条是静态演示会话，没有真实 claim；用下方演示签署查看签署后的界面即可。"
                : task?.run
                  ? "RunCapsule 与 EA 已就位，但还没有 claim draft。先在本地 CLI 执行 run claim 生成待签 claim，再回到这里。"
                  : "还没有 claim draft。先运行 pipeline 生成 RunCapsule / EA，再回到这里。"}
            </p>
          )}
          <p className="claim-gate-detail">{label.detail}</p>
        </div>

        {__STATIC_ONLY__ && (
          <section className="claim-gate-block is-demo is-first">
            <b>在网页上签署（演示预览）</b>
            <p>
              演示时不必去 CLI：点下面的按钮，claim 按演示流程推进，会话与证据链立即反映签署后的样子。
              <strong>不产生真实签名、不写入证据层、不解锁导出</strong>；刷新页面即回待签。
            </p>
            {label.state === "signed-demo" ? (
              <button type="button" className="text-button" onClick={actions.resetDemoClaim}>
                撤销演示签署，回到待签
              </button>
            ) : (
              <button
                type="button"
                className="solid-button"
                disabled={!pending}
                onClick={actions.previewDemoClaim}
              >
                在网页上签署（演示预览）→
              </button>
            )}
          </section>
        )}

        <section className="claim-gate-block">
          <b>真实签署（本地 CLI）</b>
          <p>在终端核对 EA 与数值后执行；产物是 <code>claim/claim.json</code>。占位符需替换为本次 run 的实际路径。</p>
          <GateCommandItem command={claimSignCommand({ scope: claim?.scope })} />
          <p className="claim-gate-note">{CLI_ONLY_NOTE}</p>
        </section>

        <section className="claim-gate-block">
          <b>导入已签署产物（只读，不代签）</b>
          <p>选择 CLI 生成的 <code>claim.json</code>；校验 claim_id / statement / scope / human_reason 后，工作台读取签署状态并继续展示后续阶段。</p>
          <label className="claim-gate-file">
            <input
              type="file"
              accept=".json,application/json"
              aria-label="选择 claim.json"
              onChange={(event) => void onFile(event)}
            />
            <span>选择 claim.json</span>
          </label>
          {error && <p className="claim-gate-error" role="alert">{error}</p>}
          {imported && <p className="claim-gate-ok">已校验并导入 {imported}</p>}
        </section>

        <footer className="modal-foot">
          <button type="button" className="text-button" onClick={actions.closeClaimGate}>关闭</button>
        </footer>
      </section>
    </div>
  );
}
