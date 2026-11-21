import assert from "node:assert/strict";
import test from "node:test";

import {
  DEMO_NARRATION,
  DEMO_STORYLINE_ORDER,
  DEMO_STORYLINES,
  TEACHING_STAGE_IDS,
  createDemoPlayerState,
  demoDwell,
  demoGateHint,
  demoNarration,
  demoStagePlan,
  demoStageSpans,
  isDemoGateStage,
  stageLabel
} from "../src/domain/demoPlayer.ts";
import type { Message } from "../src/domain/types.ts";

function msg(patch: Partial<Message>): Message {
  return { id: "m", role: "agent", at: "10:00", text: "...", ...patch };
}

// Stage tags mirror the two seeded transcripts (full-chain-demo and
// e2e-closed-loop); the seeds themselves use extensionless imports that node
// --test cannot resolve, so the shape is asserted on synthetic transcripts.
const TEACHING_TRANSCRIPT: Message[] = [
  msg({ role: "system", text: "STATIC REPLAY · 教学演示" }),
  msg({ role: "user", text: "从一份文献开始…" }),
  msg({ stage: "S1" }),
  msg({ role: "user", text: "先查界面钝化…" }),
  msg({ stage: "S1", card: { type: "sources" } as Message["card"] }),
  msg({ stage: "S2–S3" }),
  msg({ role: "user", text: "G1：收敛到 H1…" }),
  msg({ stage: "S2–S3", card: { type: "gate" } as Message["card"] }),
  msg({ stage: "S4" }),
  msg({ stage: "S4", card: { type: "gate" } as Message["card"] }),
  msg({ stage: "S5a", card: { type: "run" } as Message["card"] }),
  msg({ stage: "S5b", card: { type: "gate" } as Message["card"] }),
  msg({ stage: "S6" }),
  msg({ stage: "S8–S12", card: { type: "writing" } as Message["card"] }),
  msg({ stage: "S13–S16", card: { type: "gate" } as Message["card"] }),
  msg({ role: "system", text: "待人工…" }),
  msg({ stage: "META", card: { type: "evolution" } as Message["card"] }),
  msg({ text: "边界与反思" }),
  msg({ role: "system", text: "完整闭环演示结束。" })
];

const REAL_TRANSCRIPT: Message[] = [
  msg({ role: "system", text: "STATIC REPLAY · 回放一次真实执行" }),
  msg({ role: "user", text: "用 fixture 语料把完整闭环跑一遍…" }),
  msg({ stage: "S1", card: { type: "sources" } as Message["card"] }),
  msg({ stage: "S2–S3", card: { type: "idea" } as Message["card"] }),
  msg({ role: "user", text: "G1：收敛到 IDEA-02…" }),
  msg({ stage: "S2–S3", card: { type: "gate" } as Message["card"] }),
  msg({ stage: "S4", card: { type: "protocol" } as Message["card"] }),
  msg({ stage: "S5a", card: { type: "run" } as Message["card"] }),
  msg({ stage: "S5b" }),
  msg({ stage: "S8–S12" }),
  msg({ stage: "S13–S16" }),
  msg({ stage: "S13–S16", card: { type: "gate" } as Message["card"] }),
  msg({ role: "system", text: "闭环结束。" })
];

test("the teaching storyline maps to the full nine-stage template", () => {
  assert.equal(DEMO_STORYLINES.teaching.taskId, "full-chain-demo");
  assert.equal(DEMO_STORYLINES.teaching.allowDemoSign, true);
  const plan = demoStagePlan(TEACHING_TRANSCRIPT);
  assert.equal(plan.length, 9);
  // FlowDemo is driven by index into TEACHING_STAGE_IDS, so the transcript's
  // stage order must match the panel order exactly.
  assert.deepEqual(plan, [...TEACHING_STAGE_IDS]);
});

test("the real storyline maps to the e2e closed loop and forbids a demo human sign", () => {
  assert.equal(DEMO_STORYLINES.real.taskId, "e2e-closed-loop");
  // The on-disk signature in that run is a delegated autopilot one (design/136);
  // a simulated human sign would blur exactly that distinction.
  assert.equal(DEMO_STORYLINES.real.allowDemoSign, false);
  const plan = demoStagePlan(REAL_TRANSCRIPT);
  assert.equal(plan.length, 7);
  assert.ok(!plan.includes("S6"), "real replay has no figure message");
  assert.ok(!plan.includes("META"), "real replay has no self-improvement message");
});

test("stage spans absorb untagged messages into the preceding stage", () => {
  const spans = demoStageSpans(TEACHING_TRANSCRIPT);
  assert.equal(spans.length, 9);
  // The first two messages (STATIC REPLAY + user question) carry no stage tag.
  assert.equal(spans[0].first, 2);
  // Messages from the first stage tag onward must be covered by exactly one
  // span; untagged tails belong to the last stage so stepping never hides them.
  // (The two leading untagged messages sit before any stage and are revealed
  // together with the first stage via revealCount = span.last + 1.)
  let covered = 0;
  for (const span of spans) covered += span.last - span.first + 1;
  assert.equal(covered, TEACHING_TRANSCRIPT.length - spans[0].first);
  assert.equal(spans[0].first, 2);
});

test("the claim human gate is S5b on both storylines", () => {
  assert.ok(isDemoGateStage("teaching", "S5b"));
  assert.ok(isDemoGateStage("real", "S5b"));
  assert.ok(isDemoGateStage("ese", "S5b"));
  assert.ok(!isDemoGateStage("teaching", "S5a"));
  assert.ok(!isDemoGateStage("teaching", null));
  assert.match(demoGateHint("real"), /委托签/);
  assert.match(demoGateHint("teaching"), /人工门/);
  assert.match(demoGateHint("ese"), /分层口径/);
});

test("the ese storyline maps to the real repo-mining replay and forbids a demo sign", () => {
  assert.equal(DEMO_STORYLINES.ese.taskId, "ese-ms-20261118-03");
  // The ESE run's claim is an unsigned draft (no signature on disk at all), so
  // a simulated human sign would fabricate a gate crossing that never happened.
  assert.equal(DEMO_STORYLINES.ese.allowDemoSign, false);
  // The ESE transcript narrates all nine stages after the closed-loop extension.
  for (const stageId of [...TEACHING_STAGE_IDS]) {
    assert.ok(DEMO_NARRATION.ese[stageId], `ese is missing narration for ${stageId}`);
  }
  assert.equal(DEMO_STORYLINE_ORDER.length, 3);
});

test("carded messages hold longer than plain text", () => {
  const carded = demoDwell(msg({ card: { type: "gate" } as Message["card"] }));
  const plain = demoDwell(msg({}));
  assert.ok(carded > plain);
});

test("narration exists for every stage a storyline actually plays", () => {
  const teachingPlan = demoStagePlan(TEACHING_TRANSCRIPT);
  const realPlan = demoStagePlan(REAL_TRANSCRIPT);
  for (const [storyline, plan] of [
    ["teaching", teachingPlan],
    ["real", realPlan]
  ] as const) {
    for (const stageId of plan) {
      assert.ok(
        DEMO_NARRATION[storyline][stageId],
        `${storyline} is missing narration for ${stageId}`
      );
      // The narration table is the source; the lookup must not fall back to the
      // generic "S1 文献检索" string for any real stage.
      assert.notEqual(demoNarration(storyline, stageId), `${stageId} ${stageLabel(stageId)}`);
    }
  }
});

test("a fresh player starts playing, un-signed, and bound to its storyline task", () => {
  const player = createDemoPlayerState("teaching");
  assert.equal(player.revealCount, 0);
  assert.equal(player.stageId, null);
  assert.equal(player.playing, true);
  assert.equal(player.signed, false);
  assert.equal(player.finished, false);
  assert.equal(player.taskId, DEMO_STORYLINES.teaching.taskId);
});
