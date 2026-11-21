/**
 * design/169: RESEARCH FLOW must follow the task's research method, not one
 * universal pipeline. These tests read the SAME export the page consumes
 * (workspace export -> public/method-registry.json), so a stale snapshot or a
 * registry without per-method stage tasks fails here.
 *
 * The three claims under test:
 *  1. different methods produce different stage ORDER (that is what "编排" means);
 *  2. governance stages (closure / experience) are NOT method-specific;
 *  3. a transcript that ran stages outside the plan says so instead of vanishing.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import type { Message } from "../src/domain/types.ts";
import { buildMethodFlow, contractKeyFor, normalizeStageId, slotCommand, slotForStage } from "../src/domain/stagePlan.ts";
import { methodById } from "../src/domain/methodModel.ts";

const registry = JSON.parse(
  fs.readFileSync(new URL("../public/method-registry.json", import.meta.url), "utf8")
);

const known = new Set(registry.stages.map((stage: { id: string }) => normalizeStageId(stage.id)));

function msg(id: string, stage: string, role: "agent" | "user" = "agent"): Message {
  return { id, role, at: "22:00:00", text: `关于 ${stage} 的一条记录`, stage };
}

function flowFor(methodId: string, messages: Message[] = []) {
  const method = methodById(methodId, registry);
  assert.ok(method, `method ${methodId} missing from export`);
  const flow = buildMethodFlow(method, registry, messages);
  assert.ok(flow, `method ${methodId} has no composition plan`);
  return flow;
}

test("confirmatory and exploratory methods walk the stages in different orders", () => {
  const confirmatory = flowFor("controlled-experiment");
  const exploratory = flowFor("repository-mining");

  assert.equal(confirmatory.compositionId, "confirmatory");
  assert.equal(exploratory.compositionId, "exploratory");
  assert.deepEqual(
    confirmatory.steps.map((step) => step.slot),
    ["S2-S3", "S4", "S5", "S5b", "S8-S12"]
  );
  // Exploratory puts the design before the literature/evidence stage: you
  // cannot consume a hypothesis that does not exist yet.
  assert.deepEqual(
    exploratory.steps.map((step) => step.slot),
    ["S4", "S1", "S5", "S5b"]
  );
  assert.notDeepEqual(
    confirmatory.steps.map((step) => step.slot),
    exploratory.steps.map((step) => step.slot)
  );
});

test("every plan step carries the method's own task card and a wiring rationale", () => {
  for (const method of registry.methods) {
    const flow = flowFor(method.id);
    assert.ok(flow.steps.length > 0, `${method.id} has an empty plan`);
    for (const step of flow.steps) {
      assert.ok(step.task.trim(), `${method.id}/${step.slot} has no stage task`);
      if (!step.uncovered) {
        assert.ok(step.rationale, `${method.id}/${step.slot} has no wiring rationale`);
        assert.ok(step.element, `${method.id}/${step.slot} has no wiring element`);
      }
    }
  }
});

test("the same transcript is read differently by two methods", () => {
  const messages = [
    msg("1", "S1"),
    msg("2", "S2–S3"),
    msg("3", "S4"),
    msg("4", "S5a"),
    msg("5", "S5b"),
    msg("6", "S6"),
    msg("7", "S8–S12"),
    msg("8", "S13–S16"),
    msg("9", "META")
  ];
  const mining = flowFor("repository-mining", messages);
  const experiment = flowFor("controlled-experiment", messages);

  // Same nine tags, different plans: S2–S3/S6/S8–S12 are inside the
  // experiment's plan but outside mining's.
  assert.deepEqual(
    mining.extras.map((extra) => extra.id),
    ["S2–S3", "S6", "S8–S12"]
  );
  assert.deepEqual(
    experiment.extras.map((extra) => extra.id),
    ["S1", "S6"]
  );
  assert.deepEqual(mining.missing, []);
  assert.deepEqual(experiment.missing, []);
});

test("closure and experience are governance, not method differences", () => {
  const messages = [msg("1", "S5a"), msg("2", "S13–S16"), msg("3", "META")];
  const mining = flowFor("repository-mining", messages);
  assert.deepEqual(
    mining.governance.map((step) => step.slot),
    ["S13-S16", "META"]
  );
  for (const step of mining.governance) {
    assert.ok(!mining.steps.some((planned) => planned.slot === step.slot));
  }
});

test("order divergence is reported at the first different position", () => {
  const messages = [msg("1", "S1"), msg("2", "S4"), msg("3", "S5a"), msg("4", "S5b")];
  const mining = flowFor("repository-mining", messages);
  assert.ok(mining.orderMismatch, "expected an order mismatch");
  assert.deepEqual(mining.orderMismatch.planned, ["S4", "S1", "S5", "S5b"]);
  assert.deepEqual(mining.orderMismatch.actual, ["S1", "S4", "S5", "S5b"]);
  assert.equal(mining.orderMismatch.at, 0);

  // Same messages, confirmatory plan: S1 is not in the plan, the remaining
  // slots already appear in plan order, so no mismatch is claimed.
  const experiment = flowFor("controlled-experiment", messages);
  assert.equal(experiment.orderMismatch, null);
});

test("a session that never ran still shows a plan, with every step marked absent", () => {
  const flow = flowFor("case-study", []);
  assert.deepEqual(flow.steps.map((step) => step.slot), ["S0", "S4", "S1", "S5", "S8-S12"]);
  assert.deepEqual(flow.missing, ["S0", "S4", "S1", "S5", "S8-S12"]);
  assert.deepEqual(flow.extras, []);
  assert.equal(flow.orderMismatch, null);
});

test("stage ids normalise across registry and transcript spellings", () => {
  assert.equal(normalizeStageId("S2–S3"), "S2-S3");
  assert.equal(normalizeStageId("S13—S16"), "S13-S16");
  assert.equal(slotForStage("S5a", known), "S5");
  assert.equal(slotForStage("META", known), null);
  assert.equal(slotForStage("S99", known), null);
});

test("commands and contracts resolve for plan slots without inventing data", () => {
  assert.equal(slotCommand("S4"), "design.freeze");
  assert.equal(slotCommand("S5"), "run.work");
  assert.equal(slotCommand("S1b"), null);
  assert.equal(contractKeyFor("S2-S3"), "S2–S3");
  assert.equal(contractKeyFor("S5"), "S5a");
  assert.equal(contractKeyFor("S1b"), null);
});

test("the exported registry still declares a plan for all ten methods", () => {
  assert.equal(registry.methods.length, 10);
  for (const method of registry.methods) {
    assert.ok(method.composition_id, method.id);
    assert.ok(registry.compositions.some((item: { id: string }) => item.id === method.composition_id));
  }
});
