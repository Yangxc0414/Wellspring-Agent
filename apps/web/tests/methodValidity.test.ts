/**
 * design/166: the method model's new declarative layer, checked against the same
 * JSON the page consumes (workspace export -> public/method-registry.json), so a
 * stale export cannot pass the UI tests.
 */
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { iterationLabel, validityName } from "../src/domain/methodModel.ts";

const registry = JSON.parse(
  fs.readFileSync(new URL("../public/method-registry.json", import.meta.url), "utf8")
);

test("validity names resolve through the closed vocabulary", () => {
  assert.equal(validityName(registry, "internal"), "内部效度");
  assert.equal(validityName(registry, "transferability"), "可转移性");
  assert.equal(validityName(registry, "vibes"), "vibes");
  assert.equal(validityName(null, undefined), "—");
});

test("iteration labels cover all four legitimate kinds", () => {
  assert.equal(iterationLabel("fixed"), "固定阶段");
  assert.equal(iterationLabel("saturation"), "饱和停止");
  assert.equal(iterationLabel("cycle"), "循环回路");
  assert.equal(iterationLabel("convergence"), "收敛停止");
  assert.equal(iterationLabel(undefined), "—");
});

test("every exported method declares a validity focus in vocabulary", () => {
  assert.equal(registry.schema, "ese-method-registry-0.6");
  const vocab = new Set(registry.validity_vocabulary.map((entry) => entry.key));
  for (const method of registry.methods) {
    assert.ok(vocab.has(method.validity_focus.primary), method.id);
    for (const key of method.validity_focus.secondary) assert.ok(vocab.has(key), method.id);
    assert.ok(method.iteration_rule.detail.trim(), method.id);
  }
});

test("every exported wiring step explains why it sits there", () => {
  for (const composition of registry.compositions) {
    for (const step of composition.wiring) {
      assert.ok(
        String(step.rationale ?? "").trim(),
        `${composition.id}/${step.element} has no rationale`
      );
    }
  }
});
