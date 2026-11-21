import assert from "node:assert/strict";
import test from "node:test";

import {
  ELEMENTS,
  ELEMENT_ORDER,
  elementById,
  elementEdges,
  isHumanElement,
  upstreamIds
} from "../src/domain/elementGraph.ts";

test("the element order is a topological order of its own dependencies", () => {
  // The advisor's question "为何当前流程顺序如此" is answered structurally:
  // every consumed upstream element must appear EARLIER, so the order is
  // derived from input/output dependencies, not from experience.
  const order = ELEMENT_ORDER;
  for (const node of ELEMENTS) {
    for (const from of upstreamIds(node)) {
      if (from === "人") continue; // human inputs are not slot elements
      const upstreamIndex = order.indexOf(from);
      assert.ok(
        upstreamIndex >= 0 && upstreamIndex < order.indexOf(node.id),
        `${node.id} consumes ${from} which must appear earlier`
      );
    }
  }
});

test("the chain closes: evidence production precedes signing precedes writing precedes closure", () => {
  const idx = (id: string) => ELEMENT_ORDER.indexOf(id);
  assert.ok(idx("S5") < idx("S5b"), "EA must exist before a claim can bind it");
  assert.ok(idx("S5b") < idx("S6"), "figures bind to the signed evidence");
  assert.ok(idx("S5b") < idx("S8–S12"), "writing slots only accept a signed claim");
  assert.ok(idx("S8–S12") < idx("S13–S16"), "closure checks the written artifacts");
  assert.ok(idx("S4") < idx("S5"), "a frozen protocol must precede execution");
});

test("human elements are exactly the gates", () => {
  const human = ELEMENTS.filter(isHumanElement).map((node) => node.id);
  assert.deepEqual(human, ["S2–S3", "S4", "S5b", "S8–S12", "S13–S16", "META"]);
  // Non-human elements must not declare human inputs except through gates.
  for (const node of ELEMENTS) {
    if (isHumanElement(node)) continue;
    for (const edge of node.consumes) {
      assert.notEqual(edge.from, "人");
    }
  }
});

test("every edge carries its provenance (SPEC/module source)", () => {
  for (const edge of elementEdges()) {
    assert.ok(edge.source.length > 4, `edge ${edge.from}->${edge.to} lacks provenance`);
    assert.ok(edge.what.length > 2, `edge ${edge.from}->${edge.to} lacks what flows`);
  }
  // The frozen-protocol edge is the run SPEC's hardest invariant.
  const s5 = elementById("S5");
  const protocolEdge = s5?.consumes.find((edge) => edge.from === "S4");
  assert.match(protocolEdge?.what ?? "", /protocol_sha256/);
});

test("every element declares a goal anchored in the research essence", () => {
  // design/160: goals are the WHY of each element, anchored in the four
  // movements of the essence definition (提出问题 / 证据 / 主张 / 积累).
  const movementOf: Record<string, string[]> = {
    提出问题: ["S0", "S2–S3"],
    证据: ["S1", "S1b", "S5"],
    主张: ["S5b", "S6", "S8–S12"],
    积累: ["S13–S16", "META"]
  };
  for (const [movement, ids] of Object.entries(movementOf)) {
    for (const id of ids) {
      const node = elementById(id);
      assert.ok(node, `${id} exists`);
      assert.ok(node.goal.length > 8, `${id} has a substantive goal`);
      assert.ok(node.goal.includes(movement), `${id} goal anchors to ${movement}`);
    }
  }
});
