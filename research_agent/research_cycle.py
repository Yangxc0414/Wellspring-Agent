"""A bounded feedback loop: a coverage verdict changes the next retrieval budget.

Until this module, every verdict in this runtime ended in a read-only projection
(``next_actions``, a status report, a Markdown ledger). This is the first place
where a verdict is *consumed as an input*: if S1 says coverage is partial, the
next S1 run is called with a larger ``max_sources``, and the loop stops when the
verdict says saturated or the budget is exhausted.

Deliberately narrow, because it must not weaken the governance core:

* it changes exactly one parameter (the retrieval budget);
* it never crosses a human gate, never writes a Claim/EA/gate/signature, never
  sets ``submission_ready``, never resumes the rest of the pipeline;
* it never invents literature - a larger budget only lets the existing retriever
  return more of what it already has;
* every observation and decision is appended to the run event chain, so the
  loop is auditable and its budget is visible.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .modules.literature import LiteratureRequest
from .run_events import append_event

CYCLE_SCHEMA = "research-cycle-0.1"
OBSERVED_KIND = "cycle_observed"
EXPANDED_KIND = "cycle_expanded"
CONVERGED_KIND = "cycle_converged"
EXHAUSTED_KIND = "cycle_exhausted"
DEFAULT_MAX_CYCLES = 3
DEFAULT_BUDGET_CAP = 30
HUMAN_BLOCK_NOTE = (
    "retrieval budget exhausted or insufficient full text; a human must supply "
    "more sources or explicitly accept partial coverage"
)


def observe(result: Any) -> Dict[str, Any]:
    """Read-only projection of the S1 coverage verdict. Never mutates the result."""
    brief = getattr(result, "brief", None)
    coverage = getattr(result, "coverage", None)
    hits = list(getattr(result, "hits", None) or [])
    spans = list(getattr(result, "spans", None) or [])
    warnings = list(getattr(result, "warnings", None) or [])
    receipt = next(
        (item for item in warnings if str(item).startswith("evidence_breadth=")), ""
    )
    return {
        "sources": len(hits),
        "full_text": sum(1 for hit in hits if bool(getattr(hit, "full_text", False))),
        "spans": len(spans),
        "coverage_score": round(float(getattr(brief, "coverage_score", 0.0) or 0.0), 3),
        "saturation": str(getattr(brief, "saturation", "") or ""),
        "gaps": len(list(getattr(coverage, "gaps", None) or [])),
        "brief_gaps": list(getattr(brief, "gaps", None) or []),
        "review_grade": "yes" if "review_grade:yes" in receipt else "no",
        "fixture_mode": bool(getattr(result, "fixture_mode", False)),
    }


def decide_next_cycle(
    observation: Dict[str, Any],
    *,
    budget: int,
    cycles_used: int,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    budget_cap: int = DEFAULT_BUDGET_CAP,
) -> Dict[str, Any]:
    """Pure: the verdict decides whether the next run gets a bigger budget.

    ``cycles_used`` counts rounds already executed. A saturated verdict always
    wins; a loop that cannot widen reports ``exhausted`` and names the human
    action required instead of pretending it converged.
    """
    saturation = str(observation.get("saturation") or "")
    grade = str(observation.get("review_grade") or "no")
    if saturation == "saturated":
        return {
            "action": "stop", "status": "converged", "next_budget": int(budget),
            "reason": "coverage saturated (review_grade=%s); no further retrieval" % grade,
            "blocked_by_human": [],
        }
    if int(cycles_used) + 1 >= int(max_cycles):
        return {
            "action": "stop", "status": "exhausted", "next_budget": int(budget),
            "reason": "max_cycles=%d reached before saturation" % int(max_cycles),
            "blocked_by_human": [HUMAN_BLOCK_NOTE],
        }
    if int(budget) >= int(budget_cap):
        return {
            "action": "stop", "status": "exhausted", "next_budget": int(budget),
            "reason": "budget_cap=%d reached before saturation" % int(budget_cap),
            "blocked_by_human": [HUMAN_BLOCK_NOTE],
        }
    next_budget = min(max(int(budget) * 2, int(budget) + 3), int(budget_cap))
    if next_budget <= int(budget):
        return {
            "action": "stop", "status": "exhausted", "next_budget": int(budget),
            "reason": "budget cannot widen further", "blocked_by_human": [HUMAN_BLOCK_NOTE],
        }
    return {
        "action": "widen",
        "status": "widening",
        "next_budget": int(next_budget),
        "reason": "coverage=%s score=%s gaps=%d; widen retrieval budget %d -> %d" % (
            saturation or "unknown", observation.get("coverage_score"),
            int(observation.get("gaps") or 0), int(budget), int(next_budget),
        ),
        "blocked_by_human": [],
    }


@dataclass
class CycleReport:
    final: Any = None
    rounds: List[Dict[str, Any]] = field(default_factory=list)
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "exhausted"
    initial_budget: int = 0
    final_budget: int = 0
    stop_reason: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def converged(self) -> bool:
        return self.status == "converged"

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe projection; the LiteratureResult itself is not duplicated here."""
        return {
            "schema_version": CYCLE_SCHEMA,
            "status": self.status,
            "converged": self.converged,
            "rounds": [dict(row) for row in self.rounds],
            "decisions": [dict(row) for row in self.decisions],
            "initial_budget": self.initial_budget,
            "final_budget": self.final_budget,
            "stop_reason": self.stop_reason,
            "boundary": (
                "retrieval budget only; no human gate crossed, no Claim/EA/gate/signature "
                "written, no new literature invented"
            ),
        }

    def warning(self) -> str:
        if not self.rounds:
            return "adaptive_cycle=no rounds executed"
        first, last = self.rounds[0], self.rounds[-1]
        return (
            "adaptive_cycle=rounds:%d status:%s budget:%d->%d | "
            "sources:%d->%d spans:%d->%d coverage:%s->%s saturation:%s->%s | "
            "loopback changes retrieval budget only; no human gate crossed, "
            "no Claim/EA/gate written"
            % (
                len(self.rounds), self.status,
                self.initial_budget, self.final_budget,
                first["sources"], last["sources"],
                first["spans"], last["spans"],
                first["coverage_score"], last["coverage_score"],
                first["saturation"], last["saturation"],
            )
        )


def run_literature_cycle(
    agent: Any,
    question: str,
    *,
    initial_budget: int = 3,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    budget_cap: int = DEFAULT_BUDGET_CAP,
    source_scope: Optional[List[str]] = None,
    run_id: str = "",
    events: Optional[List[Dict[str, Any]]] = None,
) -> CycleReport:
    """Execute S1 until the verdict says saturated or the budget is exhausted.

    ``events`` may be the pipeline's live event chain; observations and decisions
    are appended to it so they appear in ``events.ndjson`` with correct seq/hash.
    """
    chain = events if events is not None else []
    budget = max(1, int(initial_budget))
    cycles = max(1, int(max_cycles))
    report = CycleReport(
        initial_budget=budget, final_budget=budget, events=chain,
    )
    for cycle in range(cycles):
        result = agent.run(
            LiteratureRequest(
                question=question,
                max_sources=budget,
                source_scope=list(source_scope or ["fixture"]),
                run_id=("%s-c%d" % (run_id, cycle + 1)) if run_id else "",
                coverage_plan=True,
                followup_plan=True,
            )
        )
        observation = observe(result)
        row = dict(observation, cycle=cycle + 1, budget=budget)
        report.rounds.append(row)
        append_event(chain, OBSERVED_KIND, phase="literature", payload=row)

        decision = decide_next_cycle(
            observation, budget=budget, cycles_used=cycle,
            max_cycles=cycles, budget_cap=budget_cap,
        )
        report.decisions.append(decision)
        report.final = result
        report.final_budget = budget
        if decision["action"] == "stop":
            kind = CONVERGED_KIND if decision["status"] == "converged" else EXHAUSTED_KIND
            append_event(
                chain, kind, phase="literature",
                payload={
                    "cycle": cycle + 1, "status": decision["status"],
                    "reason": decision["reason"],
                    "blocked_by_human": list(decision["blocked_by_human"]),
                },
            )
            report.status = decision["status"]
            report.stop_reason = decision["reason"]
            break
        append_event(
            chain, EXPANDED_KIND, phase="literature",
            payload={
                "cycle": cycle + 1, "from_budget": budget,
                "to_budget": decision["next_budget"], "reason": decision["reason"],
            },
        )
        budget = int(decision["next_budget"])
    else:
        report.status = "exhausted"
        report.stop_reason = "max_cycles reached without a stop decision"
        append_event(
            chain, EXHAUSTED_KIND, phase="literature",
            payload={"reason": report.stop_reason, "blocked_by_human": [HUMAN_BLOCK_NOTE]},
        )
    return report


__all__ = [
    "CYCLE_SCHEMA", "OBSERVED_KIND", "EXPANDED_KIND", "CONVERGED_KIND", "EXHAUSTED_KIND",
    "DEFAULT_MAX_CYCLES", "DEFAULT_BUDGET_CAP", "HUMAN_BLOCK_NOTE",
    "CycleReport", "observe", "decide_next_cycle", "run_literature_cycle",
]
