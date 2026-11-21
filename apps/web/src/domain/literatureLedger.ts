import type { EvidenceItem, LiteratureFacet, Message, ResearchTask } from "./types";

/**
 * S1 literature ledger — a READ-ONLY projection of a task's literature layer,
 * mirroring what the backend writes into literature.json / literature-ledger.json
 * (query plan, hits/spans, counts{found, included_full_text, abstract_only,...},
 * coverage gaps). Everything here is DERIVED from the task's existing state:
 * coverage numbers, gap evidence items, and the plan card already present in the
 * transcript. No number is invented; if a facet was never registered, the panel
 * says 未登记 rather than guessing (modules/literature contract).
 */

/** The six audit facets from the literature-brief skill (catalog.ts) and the
 * backend's coverage audit. Labels match the wording used by the run artifacts. */
export const SIX_FACETS: Array<{ id: LiteratureFacet["id"]; label: string }> = [
  { id: "core", label: "核心问题" },
  { id: "survey", label: "综述" },
  { id: "method", label: "方法" },
  { id: "evaluation", label: "评测" },
  { id: "limitation", label: "局限" },
  { id: "recent", label: "近期进展" }
];

export type FacetState = "covered" | "missing" | "unregistered";

export interface LiteraturePlan {
  queries: string[];
  scope: string;
  budget: string;
  note: string;
}

export interface LiteratureLedgerView {
  composition: {
    total: number;
    fullText: number;
    abstractOnly: number;
    spans: number;
    gapCount: number;
  };
  facets: Array<{ id: LiteratureFacet["id"]; label: string; state: FacetState }>;
  /** Whether the session registered facet coverage at all. */
  facetBasis: "registered" | "unregistered";
  facetSource?: string;
  gaps: EvidenceItem[];
  plan: LiteraturePlan | null;
}

export interface PlanCardShape {
  type: "plan";
  queries: string[];
  scope: string;
  budget: string;
  note: string;
}

/** The plan card, if the transcript carries one (teaching S1; some samples). */
export function planFromMessages(messages: Message[]): LiteraturePlan | null {
  const card = messages.map((item) => item.card).find((item) => item?.type === "plan");
  if (!card || card.type !== "plan") return null;
  return { queries: [...card.queries], scope: card.scope, budget: card.budget, note: card.note };
}

/**
 * Does this task have a literature layer at all? Repository-mining tasks
 * (spans=0 + a run capsule) run on RUN-CAPSULE evidence — their plan cards are
 * RQ mining plans, not literature queries — and an all-zero ledger would
 * mislabel repos as full-text sources.
 */
export function hasLiteratureLayer(task: ResearchTask): boolean {
  if (task.coverage.spans > 0) return true;
  // No spans: only a literature query plan on a task without a run capsule
  // still counts (a planned-but-not-yet-run survey).
  return !task.run && planFromMessages(task.messages) !== null;
}

export function buildLiteratureLedger(task: ResearchTask): LiteratureLedgerView {
  const { sources, spans, gaps, abstractOnly } = task.coverage;
  const declared = task.literature?.facets;
  const facets = SIX_FACETS.map((facet) => {
    const hit = declared?.find((item) => item.id === facet.id);
    return {
      id: facet.id,
      label: facet.label,
      state: (hit ? (hit.covered ? "covered" : "missing") : "unregistered") as FacetState
    };
  });
  return {
    composition: {
      total: sources,
      // Both seeded transcripts state this exact split ("3 条全文，1 条摘要-only"
      // for 4 sources; "2 篇来源、1 篇有全文" for 2), so the arithmetic is a
      // projection of registered counts, not a new claim.
      fullText: Math.max(0, sources - abstractOnly),
      abstractOnly,
      spans,
      gapCount: gaps
    },
    facets,
    facetBasis: declared ? "registered" : "unregistered",
    facetSource: task.literature?.source,
    gaps: task.evidence.filter((item) => item.kind === "gap"),
    plan: planFromMessages(task.messages)
  };
}
