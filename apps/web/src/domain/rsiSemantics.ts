/**
 * Visual semantics for the RSI / governance surfaces, kept out of the components so they can be
 * tested without a DOM.
 *
 * Two rules this module exists to enforce, both measured as defects in the rendered UI:
 *
 * 1. A gate clearing is not evidence of improvement. `approved` (a human said yes), `active` (a
 *    lease is running) and `recorded` (a consume was logged) used to share the success colour with
 *    `confirmed` (sealed re-check passed), which erased the distinction the backend boundary keeps
 *    insisting on. They are now neutral; only passed/confirmed/done read as success.
 * 2. The gate chain must not be retyped by hand in a component. The previous orchestration strip
 *    hard-coded "dry-run → public → hidden → regression → human" and silently dropped near_ood -
 *    the very environment the agent-level archive says must be primary. The chain lives here once,
 *    and a cross-language test compares it against the backend timeline so the two cannot drift.
 */

export type Tone = "ok" | "warn" | "bad" | "idle";

/** Success is reserved for evidence that actually passed a check, not for a gate merely clearing. */
export function tone(state: string): Tone {
  if (["passed", "confirmed", "done"].includes(state)) return "ok";
  if (["failed", "rejected", "regressed", "revoked", "expired"].includes(state)) return "bad";
  if (["pending", "pending_human", "missing", "not_recorded", "unsupported"].includes(state)) return "warn";
  // approved / active / recorded: a decision or a linkage, not a result. Neutral on purpose.
  return "idle";
}

/**
 * The instrument's verdict is information about the gate, never a success badge.
 * `gate_uninformative` (nothing was rejected) is the case worth flagging; `informative` means the
 * gate said no, which is the instrument working, not an improvement.
 */
export function verdictTone(verdict?: string): Tone {
  if (verdict === "gate_uninformative") return "warn";
  return "idle";
}

/** Must equal the backend admission timeline minus observe/candidate; guarded by a python test. */
export const RSI_GATE_CHAIN = [
  "dry-run",
  "public",
  "hidden",
  "near_ood",
  "regression",
  "human",
  "lease",
  "consume",
  "confirmation",
] as const;

export function gateChainLabel(): string {
  return RSI_GATE_CHAIN.join(" → ");
}

/** A snapshot without a date must say so rather than let the reader assume it is current. */
export function snapshotDateLabel(generatedAt?: string): string {
  return generatedAt ? `快照 ${generatedAt}` : "快照日期未记录";
}
