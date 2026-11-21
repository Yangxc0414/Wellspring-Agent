import assert from "node:assert/strict";
import test from "node:test";

import {
  EVIDENCE_PROFILES,
  evidenceProfileFor
} from "../src/domain/methodModel.ts";

test("every registry method has an evidence profile", () => {
  // Nine methods from modules/method-registry/registry.json
  const ids = [
    "systematic-literature-review",
    "repository-mining",
    "controlled-experiment",
    "quasi-experiment",
    "benchmark-evaluation",
    "case-study",
    "survey",
    "design-science",
    "action-research",
    "ml-iterative-experiment"
  ];
  for (const id of ids) {
    const profile = evidenceProfileFor(id);
    assert.ok(profile, `${id} has no evidence profile`);
    assert.ok(profile.kind.length > 4);
    assert.ok(profile.basis.length > 4, `${id} lacks a literature basis`);
  }
  assert.equal(Object.keys(EVIDENCE_PROFILES).length, ids.length);
});

test("experiment and survey differ in the essence-defining way", () => {
  // The advisor's example: 受控+随机 vs 自报 — the evidence KINDS must differ,
  // because that difference is what makes their valid claims differ.
  const experiment = evidenceProfileFor("controlled-experiment");
  const survey = evidenceProfileFor("survey");
  assert.match(experiment.kind, /受控/);
  assert.match(survey.kind, /自报/);
  assert.notEqual(experiment.kind, survey.kind);
});

test("unknown method ids yield no invented profile", () => {
  assert.equal(evidenceProfileFor("nonexistent-method"), null);
});
