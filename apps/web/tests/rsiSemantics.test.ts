import assert from "node:assert/strict";
import test from "node:test";

import {
  RSI_GATE_CHAIN,
  gateChainLabel,
  snapshotDateLabel,
  tone,
  verdictTone
} from "../src/domain/rsiSemantics.ts";

test("a gate clearing is not coloured as success", () => {
  // the measured defect: approved / active / recorded shared the success colour with confirmed
  assert.equal(tone("approved"), "idle");
  assert.equal(tone("active"), "idle");
  assert.equal(tone("recorded"), "idle");
  assert.equal(tone("confirmed"), "ok");
  assert.equal(tone("passed"), "ok");
  assert.equal(tone("done"), "ok");
});

test("failure and waiting keep their own colours", () => {
  assert.equal(tone("rejected"), "bad");
  assert.equal(tone("regressed"), "bad");
  assert.equal(tone("pending_human"), "warn");
  assert.equal(tone("missing"), "warn");
  assert.equal(tone("something-new"), "idle");
});

test("the instrument verdict is information, never a success badge", () => {
  assert.equal(verdictTone("gate_uninformative"), "warn");
  assert.equal(verdictTone("informative"), "idle");
  assert.equal(verdictTone("awaiting_decisions"), "idle");
  assert.equal(verdictTone(undefined), "idle");
});

test("the gate chain keeps near_ood and the full order", () => {
  // the measured defect: a hand-typed strip dropped near_ood, the primary environment
  assert.deepEqual([...RSI_GATE_CHAIN], [
    "dry-run", "public", "hidden", "near_ood", "regression",
    "human", "lease", "consume", "confirmation"
  ]);
  assert.ok(gateChainLabel().includes("near_ood"));
});

test("an undated snapshot says it is undated", () => {
  assert.equal(snapshotDateLabel(undefined), "快照日期未记录");
  assert.equal(snapshotDateLabel(""), "快照日期未记录");
  assert.ok(snapshotDateLabel("2026-10-24T00:00:00+00:00").includes("2026-10-24"));
});
