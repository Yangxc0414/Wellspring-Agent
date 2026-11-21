import assert from "node:assert/strict";
import test from "node:test";

import {
  compareEmpiricalTasks,
  compareMethodProfiles,
  isComparableTask
} from "../src/domain/taskCompare.ts";
import type { ResearchTask } from "../src/domain/types.ts";

function task(id: string, patch: Partial<ResearchTask>): ResearchTask {
  return {
    id,
    name: id,
    goal: "",
    domain: "",
    mode: "experiment",
    access: "ask",
    status: "blocked",
    workspaceId: "w",
    createdAt: "",
    updatedAt: "",
    stage: 0,
    completedStages: [0, 1, 2],
    harness: { version: "v1", budget: 6, label: "" },
    model: {} as ResearchTask["model"],
    usage: {},
    usageDays: {},
    guidance: [],
    plugins: [],
    toolCalls: [],
    budget: { used: 0, total: 40 },
    gates: [
      { id: "S5", status: "pass", reason: "" },
      { id: "G5", status: "blocked", reason: "claim / closure / signature 待人签" }
    ],
    coverage: { sources: 2, spans: 2, gaps: 1, abstractOnly: 0 },
    evidence: [],
    protocol: null,
    protocolFrozen: true,
    run: null,
    evaluation: {} as ResearchTask["evaluation"],
    evolution: {} as ResearchTask["evolution"],
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: [],
    messages: [],
    ...patch
  } as ResearchTask;
}

const ESE_LIKE = task("ese-ms-20261118-03", {
  name: "ESE：缺陷修复更常触碰测试？",
  run: {
    id: "RUN-ESE",
    dataset: "msr-corpus:click,httpx,requests",
    seeds: 1,
    metric: "test_cochange_rate",
    mean: 0.3749,
    // No paired baseline: the run contract is not_verifiable on min_delta, so
    // the comparison row must say "mean-only", never print a fake delta.
    baseline: null,
    ea: "EA-65d32e114229",
    status: "completed"
  },
  gates: [
    { id: "S5", status: "pass", reason: "" },
    { id: "G5", status: "blocked", reason: "claim / closure / signature 待人签" }
  ],
  evidence: [
    {
      id: "CLM-ESE-01",
      kind: "claim",
      status: "unsigned",
      text: "合并样本上缺陷修复提交触碰测试比例高 0.0464（p=0.015）；click 内方向反转。",
      scope: "三仓库便利样本 · 启发式标签 · 不可外推",
      refs: ["EA-65d32e114229"]
    }
  ],
  messages: [
    { id: "a", role: "agent", at: "", text: "语料组装开始。", stage: "S1" },
    { id: "b", role: "agent", at: "", text: "**S5b · 分层结果**", stage: "S5b" }
  ]
});

const IRIS_LIKE = task("e2e-closed-loop", {
  name: "E2E 闭环：Iris 协议验证",
  run: {
    id: "RUN-IRIS",
    dataset: "sklearn:iris:150x4",
    seeds: 3,
    metric: "accuracy",
    mean: 0.956,
    baseline: null,
    ea: "EA-bf9f4eeca1d7",
    status: "completed"
  },
  evidence: [
    {
      id: "CLM-8a1d500c25",
      kind: "claim",
      status: "signed",
      origin: "delegated",
      text: "在本地 iris 协议上，三个种子的平均 accuracy 为 0.956。",
      scope: "local protocol validation · 不可外推到科学结论",
      refs: ["EA-bf9f4eeca1d7"]
    }
  ],
  messages: [{ id: "c", role: "agent", at: "", text: "S1 检索完成。", stage: "S1" }]
});

test("comparison rows follow the fixed order and skip unmapped tasks", () => {
  const rows = compareEmpiricalTasks(
    [IRIS_LIKE, task("perovskite", { name: "示例" }), ESE_LIKE],
    null
  );
  assert.deepEqual(
    rows.map((row) => row.taskId),
    ["ese-ms-20261118-03", "e2e-closed-loop"]
  );
});

test("baseline policy is stated, never a fabricated delta", () => {
  const rows = compareEmpiricalTasks([ESE_LIKE, IRIS_LIKE], null);
  const ese = rows[0];
  assert.match(ese.baseline ?? "", /无配对基线/);
  assert.doesNotMatch(ese.baseline ?? "", /配对基线 null/);
  // A run WITH a paired baseline prints the number instead.
  const paired = compareEmpiricalTasks([
    task("e2e-closed-loop", {
      run: {
        id: "RUN",
        dataset: "iris",
        seeds: 3,
        metric: "accuracy",
        mean: 0.956,
        baseline: 0.333,
        ea: "EA",
        status: "completed"
      }
    })
  ]);
  assert.match(paired[0].baseline ?? "", /配对基线 0\.333/);
});

test("claim rows carry statement + scope with honest badges", () => {
  const rows = compareEmpiricalTasks([ESE_LIKE, IRIS_LIKE], null);
  assert.match(rows[0].claim?.badge ?? "", /待/);
  assert.match(rows[0].claim?.scope ?? "", /不可外推/);
  // The delegated iris signature must not read as a human "signed" badge.
  assert.match(rows[1].claim?.badge ?? "", /委托|DEMO|非人签|待/);
});

test("stages walked come from the transcript's own tags; quote from the first slot", () => {
  const rows = compareEmpiricalTasks([ESE_LIKE], null);
  assert.deepEqual(rows[0].stagesWalked, ["S1", "S5b"]);
  assert.match(rows[0].firstStageQuote ?? "", /语料组装开始/);
  assert.equal(rows[0].openGates.join(","), "G5");
});

test("method profile comparison exposes the protocol-field contrast", () => {
  assert.equal(isComparableTask("perovskite"), false);
  // Without a registry the method comparison is empty but the task rows still work.
  assert.deepEqual(compareMethodProfiles(null), []);
});

test("unique tag differences are computed against the compared set", () => {
  // Two methods with deliberately overlapping + unique tags (as registered).
  const methodA = { id: "repository-mining", name_zh: "甲", tags: ["消融实验", "随机化"] };
  const methodB = { id: "controlled-experiment", name_zh: "乙", tags: ["消融实验", "三角验证"] };
  const registry = {
    schema: "ese-method-registry-0.4",
    boundary: "",
    stages: [{ id: "S1", name: "x" }],
    methods: [methodA, methodB]
  } as Parameters<typeof compareEmpiricalTasks>[1];
  const a = task("ese-ms-20261118-03", { name: "甲任务" });
  const b = task("e2e-closed-loop", { name: "乙任务" });
  const rows = compareEmpiricalTasks([a, b], registry);
  assert.deepEqual(rows[0].uniqueTags, ["随机化"]);
  assert.deepEqual(rows[1].uniqueTags, ["三角验证"]);
});
