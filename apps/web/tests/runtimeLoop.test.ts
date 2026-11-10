import test from "node:test";
import assert from "node:assert/strict";

import { compactRuntimeLoop } from "../src/domain/runtimeLoop.ts";

test("projects linked experiment, writing audit and next actions", () => {
  const loop = compactRuntimeLoop({
    idea: {
      status: "candidates_need_human",
      candidates: [{ idea_id: "IDEA-01", title: "candidate", hypothesis: "h" }],
      shortlist: { selection: "human_g1", ranked: [{ idea_id: "IDEA-01", rank: 1, evidence_count: 2, source_count: 2, prior_art_scope: "s1_corpus", novelty_status: "unverified", testability: "measurable", has_kill_criteria: true, has_contrast: true }] }
    },
    experiment: { status: "needs_human", idea_id: "IDEA-01", seeds: 3 },
    paper: { status: "needs_evidence", sections: ["a"], slots: [{ slot_id: "result.primary", status: "pending_evidence" }] },
    loopCapsule: {
      writing: { status: "blocked", submission_ready: false, blockers: ["results.signed_claim: pending"], external_gates: { external_lint: { status: "blocked", issue_count: 1 }, external_consistency: { status: "attention", issue_count: 0 } } },
      experiments: [{ experiment_id: "EXP-1", idea_id: "IDEA-01", status: { stages: { claim: "signed", closure: "ready_for_signature" }, next_action: "experiment sign (human only)" } }],
      blockers: ["EXPERIMENT_CLOSURE_UNSIGNED"],
      next_actions: [{ owner: "human", gate: "G5", command: "python -m research_agent experiment sign" }]
    },
    appliedPolicy: { policy_id: "EP-1", patch: { max_sources: 5 } },
    activeLease: { lease_id: "LEASE-1", seeds: 2, scope: "S5/demo/iris" }
  });
  assert.equal(loop.idea?.candidates[0].idea_id, "IDEA-01");
  assert.equal(loop.idea?.ranked?.[0].source_count, 2);
  assert.equal(loop.idea?.ranked?.[0].prior_art_scope, "s1_corpus");
  assert.equal(loop.idea?.ranked?.[0].has_kill_criteria, true);
  assert.equal(loop.experiments?.[0].experiment_id, "EXP-1");
  assert.equal(loop.experiments?.[0].stages?.claim, "signed");
  assert.equal(loop.writing?.status, "blocked");
  assert.equal(loop.writing?.externalGates?.external_lint.status, "blocked");
  assert.equal(loop.writing?.externalGates?.external_consistency.status, "attention");
  assert.deepEqual(loop.blockers, ["EXPERIMENT_CLOSURE_UNSIGNED"]);
  assert.equal(loop.nextActions?.[0].gate, "G5");
  assert.equal(loop.appliedPolicy?.policy_id, "EP-1");
  assert.equal(loop.activeLease?.lease_id, "LEASE-1");
  assert.equal(loop.activeLease?.seeds, 2);
});

test("caps declarations without inventing experiments or writing", () => {
  const loop = compactRuntimeLoop({ loopCapsule: { blockers: ["S5_NOT_RUN"] } });
  assert.equal(loop.experiments, undefined);
  assert.equal(loop.writing, undefined);
  assert.deepEqual(loop.blockers, ["S5_NOT_RUN"]);
});
