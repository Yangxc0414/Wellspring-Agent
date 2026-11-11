import type { RuntimeLoop } from "./types";

type Loose = Record<string, unknown>;

const object = (value: unknown): Loose =>
  value && typeof value === "object" && !Array.isArray(value) ? value as Loose : {};

const array = <T = unknown>(value: unknown): T[] => Array.isArray(value) ? value as T[] : [];

const text = (value: unknown, max = 600): string =>
  typeof value === "string" ? value.trim().slice(0, max) : "";

const number = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

export interface RuntimeLoopArtifacts {
  idea?: unknown;
  experiment?: unknown;
  paper?: unknown;
  figure?: unknown;
  claimRegistry?: unknown;
  closure?: unknown;
  loopCapsule?: unknown;
  observationId?: string;
  activePolicyId?: string;
  appliedPolicy?: unknown;
  activeLease?: unknown;
}

export function compactRuntimeLoop(input: RuntimeLoopArtifacts): RuntimeLoop {
  const idea = object(input.idea);
  const shortlist = object(idea.shortlist);
  const candidates = array<Loose>(idea.candidates).slice(0, 3).map((item, index) => ({
    idea_id: text(item.idea_id, 80) || `IDEA-${index + 1}`,
    title: text(item.title, 240),
    hypothesis: text(item.hypothesis, 700),
    falsification: text(item.falsification, 400) || undefined,
    prior_art_scope: text(item.prior_art_scope, 80) || undefined,
    novelty_status: text(item.novelty_status, 60) || undefined
  }));
  const ranked = array<Loose>(shortlist.ranked).slice(0, 4).map((item) => ({
    idea_id: text(item.idea_id, 80) || undefined,
    rank: number(item.rank),
    title: text(item.title, 240) || undefined,
    evidence_count: number(item.evidence_count),
    source_count: number(item.source_count),
    prior_art_scope: text(item.prior_art_scope, 80) || undefined,
    novelty_status: text(item.novelty_status, 60) || undefined,
    testability: text(item.testability, 120) || undefined,
    has_kill_criteria: item.has_kill_criteria === true,
    has_contrast: item.has_contrast === true
  }));

  const experiment = object(input.experiment);
  const paper = object(input.paper);
  const slots = array<Loose>(paper.slots).slice(0, 8).map((item) => ({
    slot_id: text(item.slot_id, 80),
    section: text(item.section, 80) || undefined,
    status: text(item.status, 60) || "unknown",
    required_evidence: text(item.required_evidence, 180) || undefined
  }));

  const figure = object(input.figure);
  const registry = object(input.claimRegistry);
  const coverage = object(registry.coverage);
  const closure = object(input.closure);
  const capsule = object(input.loopCapsule);
  const writing = object(capsule.writing);
  // feedback 投影（round 2 起 capsule 自带；旧产物无此键 → undefined，UI 不渲染）
  const feedbackRaw = object(capsule.feedback);
  const feedbackApplied = number(feedbackRaw.constraints_applied);
  const feedbackLoops = array<string>(feedbackRaw.loops).slice(0, 6).map((item) => text(item, 60));
  const feedback = "feedback" in capsule
    ? {
        constraints_applied: feedbackApplied,
        loops: feedbackLoops,
        effects: array<string>(feedbackRaw.effects).slice(0, 6).map((item) => text(item, 120))
      }
    : undefined;
  const externalGates = object(writing.external_gates);
  const appliedPolicy = object(input.appliedPolicy);
  const activeLease = object(input.activeLease);
  const experiments = array<Loose>(capsule.experiments).map((item) => ({
    experiment_id: text(item.experiment_id, 120),
    idea_id: text(item.idea_id, 80) || undefined,
    next_action: text((object(item.status).next_action), 160) || undefined,
    stages: Object.fromEntries(
      Object.entries(object(object(item.status).stages)).map(([key, value]) => [key, text(value, 60)])
    )
  })).filter((item) => item.experiment_id);

  return {
    idea: Object.keys(idea).length
      ? {
          status: text(idea.status, 80) || undefined,
          selection: text(shortlist.selection, 80) || undefined,
          candidates,
          ranked: ranked.length ? ranked : undefined
        }
      : undefined,
    design: Object.keys(experiment).length
      ? {
          status: text(experiment.status, 80) || undefined,
          idea_id: text(experiment.idea_id, 80) || undefined,
          hypothesis: text(experiment.hypothesis, 700) || undefined,
          baseline: text(experiment.baseline, 240) || undefined,
          primary_metric: text(experiment.primary_metric, 240) || undefined,
          controls: array<string>(experiment.controls).slice(0, 6).map((item) => text(item, 120)),
          seeds: number(experiment.seeds),
          warnings: array<string>(experiment.warnings).slice(0, 6).map((item) => text(item, 240))
        }
      : undefined,
    paper: Object.keys(paper).length
      ? {
          status: text(paper.status, 80) || undefined,
          section_count: array(paper.sections).length,
          slots
        }
      : undefined,
    figure: Object.keys(figure).length
      ? {
          figure_id: text(figure.figure_id, 120) || undefined,
          kind: text(figure.kind, 80) || undefined,
          schematic: figure.schematic === true,
          evidence_refs: array<string>(figure.evidence_refs).slice(0, 6).map((item) => text(item, 120))
        }
      : undefined,
    claimRegistry: Object.keys(registry).length
      ? {
          entries: array(registry.entries).length,
          coverage_rate: number(coverage.coverage_rate),
          verified_anchor_rows: number(coverage.verified_anchor_rows)
        }
      : undefined,
    closure: Object.keys(closure).length
      ? {
          status: text(closure.status, 80) || undefined,
          unresolved: array<string>(closure.unresolved).slice(0, 8).map((item) => text(item, 160)),
          checks: array(closure.checks).length
        }
      : undefined,
    feedback: feedback ? { ...feedback, constraints_applied: feedback.constraints_applied || 0 } : undefined,
    observationId: text(input.observationId, 80) || undefined,
    activePolicyId: text(input.activePolicyId, 80) || undefined,
    appliedPolicy: Object.keys(appliedPolicy).length
      ? {
          policy_id: text(appliedPolicy.policy_id, 80) || undefined,
          patch: object(appliedPolicy.patch)
        }
      : undefined,
    activeLease: Object.keys(activeLease).length
      ? {
          lease_id: text(activeLease.lease_id, 120) || undefined,
          seeds: number(activeLease.seeds),
          scope: text(activeLease.scope, 160) || undefined
        }
      : undefined,
    writing: Object.keys(writing).length
      ? {
          status: text(writing.status, 80) || undefined,
          submission_ready: writing.submission_ready === true,
          blockers: array<string>(writing.blockers).slice(0, 8).map((item) => text(item, 180)),
          externalGates: Object.keys(externalGates).length
            ? Object.fromEntries(
                Object.entries(externalGates).map(([name, value]) => {
                  const gate = object(value);
                  return [name, {
                    status: text(gate.status, 40) || undefined,
                    issue_count: number(gate.issue_count)
                  }];
                })
              )
            : undefined
        }
      : undefined,
    experiments: experiments.length ? experiments : undefined,
    blockers: array<string>(capsule.blockers).slice(0, 10).map((item) => text(item, 120)),
    nextActions: array<Loose>(capsule.next_actions).slice(0, 6).map((item) => ({
      gate: text(item.gate, 40) || undefined,
      owner: text(item.owner, 40) || undefined,
      command: text(item.command, 400)
    })).filter((item) => item.command)
  };
}
