import type { EvidenceItem } from "./types";

/**
 * Q0 / S5b is a human gate: the browser never creates a signature. But the workbench
 * still has to *display* a signed state in two legitimate cases — a claim.json produced
 * by `python -m research_agent run claim` and imported by the user, and a static-demo
 * preview that only walks the UI through later stages. Keeping the wording in one place
 * is what stops a demo preview from being read as a real human signature.
 */

export type ClaimSignatureState =
  | "missing"
  | "unsigned"
  | "signed-cli"
  | "signed-import"
  | "signed-demo";

export interface ClaimSignatureLabel {
  state: ClaimSignatureState;
  badge: string;
  short: string;
  detail: string;
  demo: boolean;
}

export function claimSignatureLabel(claim?: EvidenceItem): ClaimSignatureLabel {
  if (!claim) {
    return {
      state: "missing",
      badge: "n/a",
      short: "NOT CREATED",
      detail: "还没有 claim draft；先跑出 RunCapsule / EA。",
      demo: false
    };
  }
  if (claim.status !== "signed") {
    return {
      state: "unsigned",
      badge: "待人工签署",
      short: "待人工签署",
      detail: "EA 已封存，但 claim 必须由作者/PI 在终端签核；系统不会自动签署。",
      demo: false
    };
  }
  if (claim.origin === "demo") {
    return {
      state: "signed-demo",
      badge: "DEMO · 无真实签名",
      short: "演示态预览（未签署）",
      detail:
        "演示态预览：仅用于展示签署后的界面流程。浏览器没有产生签名，未写入证据层；closure 与导出签名仍需 CLI 人签。",
      demo: true
    };
  }
  if (claim.origin === "cli-import") {
    return {
      state: "signed-import",
      badge: "signed · CLI 产物",
      short: "已导入 CLI 签署产物",
      detail: "签名来自用户在终端执行 run claim 后导入的 claim.json；工作台只读取，不代签、不回写。",
      demo: false
    };
  }
  return {
    state: "signed-cli",
    badge: "signed",
    short: "已人工签署（证据来自 CLI）",
    detail: "签名来自本地 CLI 的证据文件；工作台只读取该状态，不会代为签署。",
    demo: false
  };
}

/** Result of validating a local `claim/claim.json` produced by `research_agent run claim`. */
export interface SignedClaimRecord {
  claimId: string;
  statement: string;
  scope: string;
  humanReason: string;
  evidenceRefs: string[];
  status: string;
  warnings: string[];
}

export type ParseClaimResult =
  | { ok: true; record: SignedClaimRecord; scopeMismatch?: string }
  | { ok: false; error: string };

/**
 * Read-only validation of the CLI artifact. We deliberately do not require a
 * `signature` field: `run claim` writes claim_id / human_reason, and the separate
 * `closure sign` command owns the export signature. Requiring one here would reject
 * every genuine artifact.
 */
export function parseSignedClaim(input: unknown, expectedScope?: string): ParseClaimResult {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    return { ok: false, error: "不是 JSON 对象；请选择 run claim 产出的 claim.json" };
  }
  const data = input as Record<string, unknown>;
  const str = (key: string): string =>
    typeof data[key] === "string" ? (data[key] as string).trim() : "";

  const claimId = str("claim_id");
  const statement = str("statement");
  const scope = str("scope");
  const humanReason = str("human_reason");
  const status = str("status");

  for (const [key, value] of [
    ["claim_id", claimId],
    ["statement", statement],
    ["scope", scope],
    ["human_reason", humanReason]
  ] as const) {
    if (!value) return { ok: false, error: `缺少人签字段 ${key}；这不是 run claim 的完整产物` };
  }
  if (status && /unsigned|draft|pending/i.test(status)) {
    return { ok: false, error: `claim.json 的 status=${status} 仍是待签状态；请先在终端完成人签` };
  }
  const evidenceRefs = Array.isArray(data.evidence_refs)
    ? data.evidence_refs.filter((item): item is string => typeof item === "string")
    : [];
  const warnings = Array.isArray(data.warnings)
    ? data.warnings.filter((item): item is string => typeof item === "string")
    : [];

  const record: SignedClaimRecord = {
    claimId,
    statement,
    scope,
    humanReason,
    evidenceRefs,
    status: status || "supported",
    warnings
  };
  if (expectedScope && expectedScope !== scope) {
    return {
      ok: true,
      record,
      scopeMismatch: `导入文件 scope=${scope}，当前 claim scope=${expectedScope}；请确认是同一次 run 的产物。`
    };
  }
  return { ok: true, record };
}
