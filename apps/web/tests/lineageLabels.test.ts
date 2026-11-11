import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";

import {
  LINEAGE_KINDS,
  LINEAGE_STAGES,
  lineageActionLabel,
  lineageKind,
  lineageMetaLabel,
  lineageStage
} from "../src/domain/lineageLabels.ts";

const snapshotPath = fileURLToPath(new URL("../public/lineage-demo.json", import.meta.url));
const snapshot = JSON.parse(readFileSync(snapshotPath, "utf8")) as {
  nodes: Array<{ kind: string; stage: string }>;
};

test("every kind and stage in the shipped snapshot has a Chinese name and explanation", () => {
  for (const kind of new Set(snapshot.nodes.map((node) => node.kind))) {
    const label = lineageKind(kind);
    assert.ok(label.zh.length > 0, `kind ${kind} has no Chinese name`);
    assert.ok(label.desc.length > 8, `kind ${kind} has no explanation`);
    assert.ok(label.en.length > 0, `kind ${kind} has no CLI tag`);
  }
  for (const stage of new Set(snapshot.nodes.map((node) => node.stage))) {
    const label = lineageStage(stage);
    assert.ok(label.zh.length > 0, `stage ${stage} has no Chinese name`);
    assert.ok(label.hint.length > 4, `stage ${stage} has no hint`);
  }
});

test("unknown keys degrade to readable fallbacks instead of blank labels", () => {
  assert.equal(lineageKind("some_future_artifact").zh, "some_future_artifact");
  assert.match(lineageKind("some_future_artifact").desc, /快照/);
  assert.equal(lineageStage("future").zh, "FUTURE");
  assert.equal(lineageMetaLabel("unknown_key"), "unknown_key");
  assert.equal(lineageActionLabel("unknown_action"), "unknown_action");
});

test("the vocabulary tables cover the CLI vocabulary used by the page", () => {
  assert.equal(LINEAGE_KINDS.evidence.zh, "证据断言");
  assert.equal(LINEAGE_KINDS.claim.zh, "研究主张");
  assert.equal(LINEAGE_KINDS.paper_slot.zh, "稿件槽位");
  assert.equal(LINEAGE_STAGES.sources.zh, "数据与来源");
  assert.equal(lineageMetaLabel("status"), "状态");
  assert.equal(lineageMetaLabel("checks"), "检查项数");
  assert.equal(lineageActionLabel("rerun"), "需重跑");
  assert.equal(lineageActionLabel("rewrite"), "需重写");
  assert.equal(lineageActionLabel("recheck"), "需复核");
});
