/**
 * design/176: 三态决策不能压成二态。测试钉住 positive/negative/undecidable
 * 映射到三条不同分支，且 undecidable 绝不宣布为成功。
 */
import test from "node:test";
import assert from "node:assert/strict";
import { overallVerdict, researchVerdict } from "../src/domain/researchVerdict.ts";
import type { StudyComparison } from "../src/domain/types.ts";

function cmp(state: string, seeds?: number): StudyComparison {
  return {
    comparison: "X vs baseline",
    state,
    mean_diff: state === "negative" ? -0.02 : 0.01,
    ci95: state === "undecidable" ? [-0.01, 0.03] : [0.005, 0.02],
    reason: "test",
    ...(typeof seeds === "number" ? { seeds_for_80pct: seeds } : {})
  };
}

test("三态映射到三条不同的过程分支", () => {
  assert.equal(researchVerdict(cmp("positive")).action, "continue_analysis");
  assert.equal(researchVerdict(cmp("negative")).action, "revise_hypothesis");
  assert.equal(researchVerdict(cmp("undecidable")).action, "add_evidence");
});

test("undecidable 即使点估计为正也不算支持", () => {
  const decision = researchVerdict(cmp("undecidable", 42));
  assert.equal(decision.triad, "INCONCLUSIVE");
  assert.match(decision.reason, /42 种子/);
  assert.notStrictEqual(decision.action, "continue_analysis");
});

test("unavailable 交人签，不伪装成三态之一", () => {
  const decision = researchVerdict(cmp("unavailable"));
  assert.equal(decision.action, "needs_human");
  assert.equal(decision.triad, "OUT_OF_SCOPE");
});

test("整体判定：任一未判定就不宣布整体支持", () => {
  const mixed = overallVerdict([cmp("positive"), cmp("undecidable")]);
  assert.equal(mixed.triad, "INCONCLUSIVE");
  assert.equal(mixed.action, "add_evidence");
});

test("整体判定：任一反驳不被正向结果掩盖", () => {
  const mixed = overallVerdict([cmp("positive"), cmp("negative")]);
  assert.equal(mixed.triad, "REFUTED");
});

test("整体判定：空比较保持开放", () => {
  assert.equal(overallVerdict([]).action, "needs_human");
});

test("纯函数不改输入对象", () => {
  const input = cmp("undecidable", 7);
  const frozen = JSON.stringify(input);
  researchVerdict(input);
  overallVerdict([input]);
  assert.equal(JSON.stringify(input), frozen);
});
