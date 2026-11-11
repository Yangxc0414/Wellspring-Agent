import assert from "node:assert/strict";
import test from "node:test";

import { claimSignatureLabel, parseSignedClaim } from "../src/domain/claimSignature.ts";
import type { EvidenceItem } from "../src/domain/types.ts";

// Shape of research_agent/web/data/final-loop-closed/claim/claim.json, produced by
// `python -m research_agent run claim`. There is deliberately no `signature` field:
// closure sign owns that, so a validator demanding one would reject real artifacts.
const cliArtifact = {
  claim_id: "CLM-b11da18a28",
  statement: "On the local iris protocol, mean accuracy is 0.956 over seeds [17, 18, 19].",
  evidence_refs: ["EA-56b0c7c1c382"],
  scope: "S5/demo/iris",
  status: "supported",
  human_reason: "final verification: capsule metrics checked",
  created_at: "2026-10-28T16:27:28+00:00",
  warnings: ["legacy claim has no structured assertions; numeric support was not re-verified"]
};

function claim(patch: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    id: "CLM-1",
    kind: "claim",
    status: "unsigned",
    text: "双分子钝化层在湿热条件下延长 T80",
    scope: "S5/demo/iris",
    refs: ["EA-1"],
    ...patch
  };
}

test("a demo preview is never worded as a human signature", () => {
  const label = claimSignatureLabel(claim({ status: "signed", origin: "demo" }));
  assert.equal(label.state, "signed-demo");
  assert.equal(label.demo, true);
  assert.match(label.badge, /DEMO/);
  assert.match(label.detail, /没有产生签名/);
  assert.match(label.detail, /未写入证据层/);
});

test("an imported CLI artifact is read-only and still not a browser signature", () => {
  const label = claimSignatureLabel(claim({ status: "signed", origin: "cli-import" }));
  assert.equal(label.state, "signed-import");
  assert.equal(label.demo, false);
  assert.match(label.detail, /只读取/);
  assert.doesNotMatch(label.short, /演示/);
});

test("unsigned and legacy CLI-backed claims keep their own wording", () => {
  assert.equal(claimSignatureLabel(claim()).state, "unsigned");
  assert.equal(claimSignatureLabel().state, "missing");
  assert.equal(claimSignatureLabel(claim({ status: "signed" })).state, "signed-cli");
  assert.equal(claimSignatureLabel(claim({ status: "signed" })).demo, false);
});

test("a genuine run claim artifact passes validation", () => {
  const result = parseSignedClaim(cliArtifact, "S5/demo/iris");
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.record.claimId, cliArtifact.claim_id);
  assert.equal(result.record.statement, cliArtifact.statement);
  assert.equal(result.record.humanReason, cliArtifact.human_reason);
  assert.deepEqual(result.record.evidenceRefs, cliArtifact.evidence_refs);
  assert.equal(result.scopeMismatch, undefined);
});

test("incomplete, draft and non-object artifacts are rejected", () => {
  assert.equal(parseSignedClaim(null).ok, false);
  assert.equal(parseSignedClaim([]).ok, false);
  assert.equal(parseSignedClaim({ ...cliArtifact, human_reason: "" }).ok, false);
  assert.equal(parseSignedClaim({ ...cliArtifact, claim_id: "  " }).ok, false);
  const draft = parseSignedClaim({ ...cliArtifact, status: "draft" });
  assert.equal(draft.ok, false);
});

test("a scope mismatch is reported as a warning, not silently accepted", () => {
  const result = parseSignedClaim(cliArtifact, "S5/perovskite");
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.match(result.scopeMismatch ?? "", /S5\/demo\/iris/);
  assert.match(result.scopeMismatch ?? "", /请确认是同一次 run/);
});
