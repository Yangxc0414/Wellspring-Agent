import assert from "node:assert/strict";
import test from "node:test";

import {
  COMPOSITIONS,
  COMPOSITION_ORDER,
  PORT_ELEMENTS,
  validateComposition
} from "../src/domain/composition.ts";

test("both reference compositions are legal wirings (port matching)", () => {
  for (const id of COMPOSITION_ORDER) {
    const violations = validateComposition(COMPOSITIONS[id]);
    assert.deepEqual(violations, [], `${id} must be a legal wiring`);
  }
});

test("the confirmatory and exploratory wirings differ exactly at the 方案 port", () => {
  const confirmatory = COMPOSITIONS.confirmatory.wiring;
  const exploratory = COMPOSITIONS.exploratory.wiring;
  const cPlan = confirmatory.find((step) => step.element === "方案");
  const ePlan = exploratory.find((step) => step.element === "方案");
  // The advisor's example as data: 验证式的方案消费假设（判别式设计），
  // 探索式的方案消费研究问题（数据收集设计）——换顺序就是换输入端口。
  assert.equal(cPlan?.consumes, "候选假设（可判别）");
  assert.equal(ePlan?.consumes, "研究问题");
  // And the hypothesis moves: before the design in confirmatory, after the
  // evidence in exploratory.
  const idx = (wiring, element) => wiring.findIndex((step) => step.element === element);
  assert.ok(idx(confirmatory, "假设") < idx(confirmatory, "方案"));
  assert.ok(idx(exploratory, "假设") > idx(exploratory, "证据"));
});

test("an illegal wiring is detectable: 假设 cannot follow 证据 in confirmatory shape", () => {
  // Take the exploratory order but wire 方案 from the hypothesis port: the
  // hypothesis has not been produced yet at that point -> violation.
  const illegal = {
    id: "illegal" as const,
    label: "非法接线",
    sub: "",
    wiring: [
      { element: "问题", consumes: null },
      { element: "方案", consumes: "候选假设（可判别）" },
      { element: "证据", consumes: "判别式协议" }
    ]
  };
  const violations = validateComposition(illegal);
  assert.ok(violations.some((v) => v.message.includes("上游尚未产出")));
});

test("elements declare their ports; gates stay human", () => {
  const byId = new Map(PORT_ELEMENTS.map((item) => [item.id, item]));
  for (const id of ["判定", "闭包", "写作", "经验", "假设", "方案"]) {
    assert.equal(byId.get(id)?.human, true, `${id} is a human element`);
  }
  for (const id of ["证据", "图表", "问题"]) {
    assert.equal(byId.get(id)?.human, false, `${id} is agent-executable`);
  }
});
