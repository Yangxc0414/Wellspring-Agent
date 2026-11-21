import assert from "node:assert/strict";
import test from "node:test";

import {
  GATE_CONTRACTS,
  GATE_ORDER,
  STAGE_MODULE_CONTRACTS,
  gateIdForCard
} from "../src/domain/gateContracts.ts";
import { TEACHING_STAGE_IDS } from "../src/domain/demoPlayer.ts";

test("every human gate has a contract, an owner, and a CLI command", () => {
  for (const id of GATE_ORDER) {
    const gate = GATE_CONTRACTS[id];
    assert.ok(gate.contract.length >= 3, `${id} needs its backend invariants`);
    assert.match(gate.owner, /modules\//, `${id} must name its backend owner`);
    const cmd = gate.command({}, { humanReason: "核对完成", ideaId: "IDEA-02" });
    // human_reason is mandatory on every sign/freeze/converge command in cli.py.
    assert.match(cmd, /--human-reason "核对完成"/, `${id} command must carry the dialog reason`);
  }
});

test("each gate command mirrors the real CLI entrypoint", () => {
  assert.match(GATE_CONTRACTS.G1.command({}, { ideaId: "IDEA-02", humanReason: "x" }), /flow g1/);
  assert.match(GATE_CONTRACTS.G1.command({}, { ideaId: "IDEA-02", humanReason: "x" }), /--idea-id IDEA-02/);
  assert.match(GATE_CONTRACTS.G2.command({}, { humanReason: "x" }), /protocol freeze/);
  assert.match(GATE_CONTRACTS.S5b.command({}, { humanReason: "x" }), /run claim/);
  assert.match(GATE_CONTRACTS.G5.command({}, { humanReason: "x" }), /closure sign/);
  // An empty dialog reason falls back to the documented placeholder instead of
  // producing `--human-reason ""` (which the CLI would reject anyway).
  assert.match(GATE_CONTRACTS.G5.command({}, {}), /--human-reason "[^"]+"/);
});

test("gate cards route to their own gate, not always to the claim panel", () => {
  assert.equal(gateIdForCard("G1"), "G1");
  assert.equal(gateIdForCard("G2"), "G2");
  assert.equal(gateIdForCard("S5b"), "S5b");
  assert.equal(gateIdForCard("G5"), "G5");
  // Q0 cards open the same claim panel (existing behaviour in ClaimGateDialog).
  assert.equal(gateIdForCard("Q0"), "S5b");
  assert.equal(gateIdForCard("G3"), null);
});

test("the stage×module contract map covers exactly the nine teaching stages", () => {
  for (const stageId of [...TEACHING_STAGE_IDS]) {
    const mc = STAGE_MODULE_CONTRACTS[stageId];
    assert.ok(mc, `stage ${stageId} has no backend contract entry`);
    assert.match(mc.module, /modules\//);
    assert.ok(mc.invariants.length >= 2, `stage ${stageId} needs its invariants`);
  }
  // And nothing extra: a contract for a stage the panel never renders would be
  // unreviewable dead data.
  const extra = Object.keys(STAGE_MODULE_CONTRACTS).filter(
    (id) => !(TEACHING_STAGE_IDS as readonly string[]).includes(id)
  );
  assert.deepEqual(extra, []);
});
