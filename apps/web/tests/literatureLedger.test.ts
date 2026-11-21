import assert from "node:assert/strict";
import test from "node:test";

import {
  buildLiteratureLedger,
  hasLiteratureLayer,
  planFromMessages,
  SIX_FACETS
} from "../src/domain/literatureLedger.ts";
import type { LiteratureFacet, Message, ResearchTask } from "../src/domain/types.ts";

function task(patch: Partial<ResearchTask> & { coverage?: ResearchTask["coverage"] }): ResearchTask {
  return {
    id: "t",
    name: "t",
    goal: "",
    domain: "",
    mode: "research",
    access: "ask",
    status: "active",
    workspaceId: "w",
    createdAt: "",
    updatedAt: "",
    stage: 0,
    completedStages: [],
    harness: { version: "v1", budget: 6, label: "" },
    model: {} as ResearchTask["model"],
    usage: {},
    usageDays: {},
    guidance: [],
    plugins: [],
    toolCalls: [],
    budget: { used: 0, total: 40 },
    gates: [],
    coverage: { sources: 4, spans: 12, gaps: 2, abstractOnly: 1 },
    evidence: [],
    protocol: null,
    protocolFrozen: false,
    run: null,
    evaluation: {} as ResearchTask["evaluation"],
    evolution: {} as ResearchTask["evolution"],
    auto: { running: false, paused: false, index: 0, cycle: 0, gate: "", gateApproved: false },
    autoStages: [],
    messages: [],
    ...patch
  } as ResearchTask;
}

// Both seeded literature transcripts state this exact split: teaching S1 says
// "3 条全文，1 条摘要-only" for 4 sources; the real e2e run says "2 篇来源、
// 1 篇有全文" for 2 sources with abstractOnly=1.
test("来源构成 derives the full-text split the transcripts state", () => {
  const teaching = buildLiteratureLedger(task({}));
  assert.equal(teaching.composition.total, 4);
  assert.equal(teaching.composition.fullText, 3);
  assert.equal(teaching.composition.abstractOnly, 1);

  const e2e = buildLiteratureLedger(task({ coverage: { sources: 2, spans: 2, gaps: 4, abstractOnly: 1 } }));
  assert.equal(e2e.composition.fullText, 1);
  assert.equal(e2e.composition.abstractOnly, 1);
  // Clamp: a malformed coverage row can never produce a negative full-text count.
  const clamped = buildLiteratureLedger(
    task({ coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 2 } })
  );
  assert.equal(clamped.composition.fullText, 0);
});

test("six-facet audit: declared facets merge onto the rubric, undeclared say 未登记", () => {
  const declared: LiteratureFacet[] = [
    { id: "core", label: "核心问题", covered: true },
    { id: "survey", label: "综述", covered: true },
    { id: "method", label: "方法", covered: false }
  ];
  const ledger = buildLiteratureLedger(task({ literature: { facets: declared, source: "S1 覆盖声明" } }));
  assert.equal(ledger.facetBasis, "registered");
  const byId = Object.fromEntries(ledger.facets.map((f) => [f.id, f.state]));
  assert.equal(byId.core, "covered");
  assert.equal(byId.survey, "covered");
  assert.equal(byId.method, "missing");
  // Facets the session never mentioned stay unregistered — not guessed.
  assert.equal(byId.evaluation, "unregistered");
  assert.equal(byId.limitation, "unregistered");
  assert.equal(byId.recent, "unregistered");

  const unregistered = buildLiteratureLedger(task({}));
  assert.equal(unregistered.facetBasis, "unregistered");
  assert.ok(unregistered.facets.every((f) => f.state === "unregistered"));
  // The rubric itself is always the backend's six facets, in order.
  assert.deepEqual(
    unregistered.facets.map((f) => f.id),
    SIX_FACETS.map((f) => f.id)
  );
});

test("gap registry reads evidence rows; plan card is lifted from the transcript", () => {
  const gapRows = [
    { id: "GAP-001", kind: "gap" as const, status: "open" as const, text: "湿热配对对照缺失", scope: "S1", refs: ["SPAN-021"] },
    { id: "CAND-H1", kind: "hypothesis" as const, status: "candidate" as const, text: "H1", scope: "S2", refs: [] }
  ];
  const ledger = buildLiteratureLedger(task({ evidence: gapRows as ResearchTask["evidence"] }));
  assert.equal(ledger.gaps.length, 1);
  assert.equal(ledger.gaps[0].id, "GAP-001");

  const messages: Message[] = [
    { id: "m1", role: "agent", at: "", text: "" },
    {
      id: "m2",
      role: "agent",
      at: "",
      text: "",
      card: {
        type: "plan",
        queries: ["q1", "q2", "q3"],
        scope: "2020–2026 · 中英双语",
        budget: "4 sources · 12 spans",
        note: "没有全文不生成 span"
      }
    }
  ];
  const plan = planFromMessages(messages);
  assert.ok(plan);
  assert.equal(plan.queries.length, 3);
  const withPlan = buildLiteratureLedger(task({ messages }));
  assert.equal(withPlan.plan?.queries.length, 3);
  assert.equal(buildLiteratureLedger(task({})).plan, null);
});

test("tasks without a literature layer are excluded (repo-mining runs on RUN-CAPSULE)", () => {
  assert.equal(hasLiteratureLayer(task({})), true);
  const repoMining = task({ coverage: { sources: 3, spans: 0, gaps: 1, abstractOnly: 0 } });
  assert.equal(hasLiteratureLayer(repoMining), false);
  // The ESE shape: a plan card exists, but it is an RQ mining plan on a task
  // with a run capsule — repos are not full-text sources.
  const ese = task({
    coverage: { sources: 3, spans: 0, gaps: 1, abstractOnly: 0 },
    run: { id: "RUN-ESE", dataset: "repos", seeds: 0, metric: "", mean: 0, baseline: 0, ea: "", status: "" },
    messages: [
      {
        id: "m",
        role: "agent",
        at: "",
        text: "",
        card: { type: "plan", queries: ["RQ1"], scope: "repos", budget: "b", note: "n" }
      }
    ]
  });
  assert.equal(hasLiteratureLayer(ese), false);
  // A zero-coverage task that still carries a literature plan and no run
  // capsule counts (planned-but-not-yet-run survey).
  const planned = task({
    coverage: { sources: 0, spans: 0, gaps: 0, abstractOnly: 0 },
    messages: [
      {
        id: "m",
        role: "agent",
        at: "",
        text: "",
        card: { type: "plan", queries: ["q"], scope: "s", budget: "b", note: "n" }
      }
    ]
  });
  assert.equal(hasLiteratureLayer(planned), true);
});
