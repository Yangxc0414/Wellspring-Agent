"""Run-internal A/B on the guideline memory: does the injected block change idea quality?

TTME's lesson is not "add memory" but "give half the children a control card". This module makes the
same discipline available here, non-parametrically: the same generation request is run once with the
guideline block and once without, and both arms are scored by deterministic checks the runtime already
enforces — evidence grounding, falsifiability, and whether the declared experiment plan is actually
executable. The comparison refuses to declare a winner on a small number of ideas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .executable import validate_plan
from .storage import read_json, write_json_atomic

MEMORY_AB_SCHEMA = "memory-ab-0.2"
MIN_PAIRS = 4

MEMORY_AB_BOUNDARY = (
    "an A/B over ideas from one prompt differs by exactly one inserted block: it can say which arm "
    "scored better on the checks the runtime enforces, and it cannot establish that the memory caused "
    "a discovery; below %d paired ideas no direction is reported" % MIN_PAIRS
)

SINGLE_SESSION_BOUNDARY = (
    "single-session mode: the same host session answered both arms, so this comparison can "
    "demonstrate that the measurement pipeline runs and produce a paired read-out, but it cannot "
    "rule out same-source bias — a memory-gain claim requires the multi-session mode with "
    "distinct host sessions per arm"
)

METRICS = (
    "grounded_rate",
    "falsifiable_rate",
    "executable_plan_rate",
    "distinct_sources_mean",
    "power_aware_stopping_rate",
    "risk_noted_rate",
)

# A stopping rule that names seeds, pairing or budget has dynamic range; "run until it works" does not.
_POWER_TERMS = ("seed", "种子", "paired", "配对", "功效", "power", "budget", "预算", "重复")


def _source_ids(literature: Dict[str, Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for span in literature.get("spans") or []:
        if isinstance(span, dict):
            span_id = str(span.get("span_id") or "")
            if span_id:
                mapping[span_id] = str(span.get("source_id") or "")
    for ref in literature.get("references") or []:
        if isinstance(ref, dict):
            ref_id = str(ref.get("ref_id") or "")
            if ref_id:
                mapping.setdefault(ref_id, str(ref.get("source_id") or ""))
    return mapping


def _specificity(stopping_rule: str) -> bool:
    text = (stopping_rule or "").lower()
    return any(term.lower() in text for term in _POWER_TERMS)


def score_arm(ideas: List[Dict[str, Any]], literature: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic quality rates for one arm; no model, no thresholds tuned per run.

    The first three checks are gates the runtime already enforces, so on surviving ideas they sit at
    the ceiling and cannot separate arms; the last three carry the signal (source breadth, stopping
    rule specificity, named risks).
    """
    ideas = [item for item in (ideas or []) if isinstance(item, dict)]
    if not ideas:
        return {"n": 0, "rates": {key: None for key in METRICS}, "per_idea": []}
    owners = _source_ids(literature)
    per_idea: List[Dict[str, Any]] = []
    for index, idea in enumerate(ideas):
        refs = [str(ref) for ref in (idea.get("evidence_refs") or [])]
        distinct = {owners[ref] for ref in refs if ref in owners and owners[ref]}
        grounded = len(distinct) >= 2
        falsifiable = len(str(idea.get("falsification") or "").strip()) >= 12
        plan = idea.get("experiment_plan") or {}
        executable = bool(validate_plan(plan).get("ok")) if isinstance(plan, dict) else False
        specific = _specificity(str((plan or {}).get("stopping_rule") or ""))
        risks = [str(item) for item in (idea.get("risks") or []) if str(item).strip()]
        per_idea.append(
            {
                "index": index,
                "title": str(idea.get("title") or "")[:120],
                "grounded": grounded,
                "falsifiable": falsifiable,
                "executable_plan": executable,
                "distinct_sources": len(distinct),
                "power_aware_stopping": specific,
                "risk_noted": bool(risks),
                "score": int(grounded) + int(falsifiable) + int(executable),
                "score_wide": (
                    int(grounded) + int(falsifiable) + int(executable)
                    + int(specific) + int(bool(risks))
                ),
            }
        )
    total = float(len(per_idea))
    return {
        "n": len(per_idea),
        "rates": {
            "grounded_rate": round(sum(bool(item["grounded"]) for item in per_idea) / total, 4),
            "falsifiable_rate": round(sum(bool(item["falsifiable"]) for item in per_idea) / total, 4),
            "executable_plan_rate": round(
                sum(bool(item["executable_plan"]) for item in per_idea) / total, 4
            ),
            "distinct_sources_mean": round(
                sum(int(item["distinct_sources"]) for item in per_idea) / total, 4
            ),
            "power_aware_stopping_rate": round(
                sum(bool(item["power_aware_stopping"]) for item in per_idea) / total, 4
            ),
            "risk_noted_rate": round(
                sum(bool(item["risk_noted"]) for item in per_idea) / total, 4
            ),
        },
        "mean_score": round(sum(int(item["score"]) for item in per_idea) / total, 4),
        "mean_score_wide": round(sum(int(item["score_wide"]) for item in per_idea) / total, 4),
        "per_idea": per_idea,
    }


def compare(
    with_arm: Dict[str, Any],
    without_arm: Dict[str, Any],
    *,
    session_mode: str = "single",
) -> Dict[str, Any]:
    """Paired read-out of the two arms, with the same refusal-to-interpret rule as the studies."""
    if session_mode not in ("single", "multi"):
        raise ValueError("unknown session mode: %s (use single or multi)" % session_mode)
    pairs = min(int(with_arm.get("n") or 0), int(without_arm.get("n") or 0))
    verdict: Dict[str, Any] = {
        "pairs": pairs,
        "underpowered": pairs < MIN_PAIRS,
        "session_mode": session_mode,
        "session_check": {"status": "single_session"},
        "rates": {
            "with_memory": with_arm.get("rates"),
            "without_memory": without_arm.get("rates"),
            "delta": {
                key: None
                if (with_arm.get("rates") or {}).get(key) is None
                or (without_arm.get("rates") or {}).get(key) is None
                else round((with_arm["rates"][key] - without_arm["rates"][key]), 4)
                for key in METRICS
            },
        },
        "per_idea_deltas": [],
        "sign_counts": {"better": 0, "worse": 0, "tie": 0},
    }
    if session_mode == "multi":
        with_label = str((with_arm.get("session") or {}).get("host_label") or "")
        without_label = str((without_arm.get("session") or {}).get("host_label") or "")
        if not with_label or not without_label:
            verdict["session_check"] = {
                "status": "blocked",
                "reason": (
                    "multi-session mode requires session metadata on both arms; record each arm "
                    "with --session-host-label so same-source bias can be excluded"
                ),
            }
        elif with_label == without_label:
            verdict["session_check"] = {
                "status": "blocked",
                "reason": "both arms were answered by host session '%s'; multi-session mode requires distinct sessions" % with_label,
            }
        else:
            verdict["session_check"] = {
                "status": "ok",
                "with_host_label": with_label,
                "without_host_label": without_label,
            }
        if verdict["session_check"]["status"] == "blocked":
            # fail-visible: a blocked session check refuses direction interpretation entirely
            verdict["direction"] = ""
            verdict["reading"] = "blocked: " + verdict["session_check"]["reason"]
            return verdict
    for index in range(pairs):
        left = (with_arm.get("per_idea") or [])[index]
        right = (without_arm.get("per_idea") or [])[index]
        delta = int(left["score_wide"]) - int(right["score_wide"])
        verdict["per_idea_deltas"].append(
            {
                "index": index,
                "with": left["score_wide"],
                "without": right["score_wide"],
                "delta": delta,
                "gates_only": int(left["score"]) - int(right["score"]),
            }
        )
        key = "better" if delta > 0 else "worse" if delta < 0 else "tie"
        verdict["sign_counts"][key] += 1
    if verdict["underpowered"]:
        verdict["direction"] = ""
        verdict["reading"] = (
            "%d paired ideas is too few to interpret a sign: run more ideas per arm before "
            "claiming the memory helps or hurts" % pairs
        )
    else:
        better = verdict["sign_counts"]["better"]
        worse = verdict["sign_counts"]["worse"]
        verdict["direction"] = (
            "with_memory_better" if better > worse
            else "with_memory_worse" if worse > better
            else "no_difference"
        )
        verdict["reading"] = (
            "%d of %d paired ideas scored better with the guideline block, %d worse; "
            "this is a difference on the runtime's own checks, not a discovery claim"
            % (better, pairs, worse)
        )
    if session_mode == "single":
        verdict["reading"] = verdict["reading"] + " | " + SINGLE_SESSION_BOUNDARY
    return verdict


def path_for(project: Path) -> Path:
    return Path(project) / "memory" / "ab.json"


def record(project: Path, *, run_id: str, arm: str, ideas: List[Dict[str, Any]],
           literature: Dict[str, Any], guidance: Optional[str] = None,
           session: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    store = read_json(path_for(project)) or {"schema_version": MEMORY_AB_SCHEMA, "arms": {}}
    scored = score_arm(ideas, literature)
    scored["guidance_chars"] = len(guidance or "")
    scored["run_id"] = str(run_id)
    if session:
        scored["session"] = {
            "session_id": str(session.get("session_id") or ""),
            "host_label": str(session.get("host_label") or ""),
        }
    store["arms"][str(arm)] = scored
    store["schema_version"] = MEMORY_AB_SCHEMA
    store["boundary"] = MEMORY_AB_BOUNDARY
    write_json_atomic(path_for(project), store)
    return scored


def analysis(project: Path, session_mode: str = "single") -> Dict[str, Any]:
    store = read_json(path_for(project)) or {}
    arms = store.get("arms") or {}
    if "with" not in arms or "without" not in arms:
        return {
            "schema_version": MEMORY_AB_SCHEMA,
            "status": "incomplete",
            "arms_present": sorted(arms),
            "next": "record both arms (`memory ab record --arm with|without`) before comparing",
            "boundary": MEMORY_AB_BOUNDARY,
        }
    return {
        "schema_version": MEMORY_AB_SCHEMA,
        "status": "compared",
        "arms_present": ["with", "without"],
        "comparison": compare(arms["with"], arms["without"], session_mode=session_mode),
        "boundary": MEMORY_AB_BOUNDARY,
    }
