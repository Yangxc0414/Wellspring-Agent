import assert from "node:assert/strict";
import test from "node:test";

import {
  gateDecisionQuote,
  humanTurns,
  turnsByStage,
  turnsForStage
} from "../src/domain/humanTurns.ts";
import type { Message } from "../src/domain/types.ts";

function msg(patch: Partial<Message>): Message {
  return { id: "m", role: "agent", at: "10:00", text: "...", ...patch };
}

// Shape mirrors the seeded teaching transcript: user turns sit between staged
// agent messages, so the span rule decides which stage "owns" each turn.
const TRANSCRIPT: Message[] = [
  msg({ role: "system", text: "STATIC REPLAY" }),
  msg({ role: "user", text: "从一份文献开始，完整演示一遍。" }),
  msg({ stage: "S1" }),
  msg({ role: "user", text: "先查界面钝化与湿热稳定性的证据。" }),
  msg({ stage: "S1" }),
  msg({ stage: "S2–S3" }),
  msg({ role: "user", text: "G1：收敛到 H1（钝化层降低缺陷密度 → 延长 T80），H2 作为竞争假设保留。" }),
  msg({ stage: "S2–S3" }),
  msg({ stage: "S4" }),
  msg({ role: "user", text: "G2：确认协议，按 3 seeds 跑。" }),
  msg({ stage: "S4" }),
  msg({ stage: "S5b" }),
  msg({ role: "user", text: "这条现在能签吗？" }),
  msg({ stage: "META" })
];

test("user turns are absorbed into the stage span they sit inside", () => {
  const turns = humanTurns(TRANSCRIPT);
  assert.equal(turns.length, 5);
  // Opening turn sits before any stage tag.
  assert.equal(turns[0].stage, null);
  // A user turn between two S1 messages belongs to S1.
  assert.equal(turns[1].stage, "S1");
  assert.equal(turns[2].stage, "S2–S3");
  assert.equal(turns[3].stage, "S4");
  // A question inside S5b stays a question, but is still attributed to S5b.
  assert.equal(turns[4].stage, "S5b");
  assert.equal(turns[4].text, "这条现在能签吗？");
});

test("grouping keeps every turn reachable per stage", () => {
  const grouped = turnsByStage(humanTurns(TRANSCRIPT));
  assert.equal(grouped[""].length, 1);
  assert.equal(grouped["S1"].length, 1);
  assert.equal(grouped["S2–S3"].length, 1);
  assert.equal(grouped["S4"].length, 1);
  assert.equal(grouped["S5b"].length, 1);
  assert.equal(turnsForStage(humanTurns(TRANSCRIPT), "S4").length, 1);
  assert.equal(turnsForStage(humanTurns(TRANSCRIPT), "META").length, 0);
});

test("gate decision quotes match explicit gate-prefixed lines only", () => {
  const turns = humanTurns(TRANSCRIPT);
  const g1 = gateDecisionQuote(turns, "S2–S3", "G1");
  assert.ok(g1);
  assert.match(g1.text, /^G1：收敛到 H1/);
  const g2 = gateDecisionQuote(turns, "S4", "G2");
  assert.ok(g2);
  // "这条现在能签吗？" is a question, never a decision to pre-fill.
  assert.equal(gateDecisionQuote(turns, "S5b", "S5b"), null);
  assert.equal(gateDecisionQuote(turns, "S1", "G1"), null);
});

test("transcripts without user turns yield nothing", () => {
  assert.deepEqual(humanTurns([msg({ stage: "S1" })]), []);
});
