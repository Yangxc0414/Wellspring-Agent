"""Fixture research queue: run the full S1→paper pipeline and collect observations.

This is the execution surface that a future TF-RSI proposer will observe. It is
still fixture-only: no model/API, no real experiments, no claims.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .pipeline import PipelineRequest, PipelineRunner
from .rsi import RSIController, StepLedger
from .rsi_fixture import RetrievalPolicy, active_literature_policy, run_observation_trial
from .rsi_proposer import RuleBasedProposer


@dataclass
class ResearchTask:
    task_id: str
    topic: str
    language: str = "zh"
    venue_type: str = "zh_core_journal"
    grant_scheme: str = ""
    primary_metric: str = ""
    controls: List[str] = field(default_factory=list)
    budget: str = ""


@dataclass
class ResearchObservation:
    observation_id: str
    task_id: str
    kind: str
    severity: str
    message: str
    refs: List[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_research_tasks(path: Path) -> List[ResearchTask]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("fixture") is not True:
        raise ValueError("research tasks must be marked fixture: true")
    tasks = []
    for raw in data.get("tasks", []):
        tasks.append(ResearchTask(
            task_id=str(raw["task_id"]),
            topic=str(raw["topic"]),
            language=str(raw.get("language", "zh")),
            venue_type=str(raw.get("venue_type", "zh_core_journal")),
            grant_scheme=str(raw.get("grant_scheme", "")),
            primary_metric=str(raw.get("primary_metric", "")),
            controls=list(raw.get("controls", [])),
            budget=str(raw.get("budget", "")),
        ))
    if not tasks:
        raise ValueError("research queue needs at least one task")
    return tasks


class ResearchRunner:
    fixture_mode = True

    def __init__(self, output_dir: Path, max_sources: int = 6):
        if not isinstance(max_sources, int) or isinstance(max_sources, bool) or max_sources < 1:
            raise ValueError("max_sources must be a positive integer")
        self.output_dir = Path(output_dir)
        self.max_sources = max_sources
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _observations(self, task: ResearchTask, result: Dict[str, Any]) -> List[ResearchObservation]:
        obs: List[ResearchObservation] = []
        literature = result["modules"].get("literature") or {}
        idea = result["modules"].get("idea") or {}
        experiment = result["modules"].get("experiment") or {}
        figure = result["modules"].get("figure") or {}
        paper = result["modules"].get("paper") or {}

        for gap in (literature.get("coverage") or {}).get("gaps", []):
            obs.append(ResearchObservation(
                "OBS-" + uuid.uuid4().hex[:8], task.task_id, "coverage_gap", "warn",
                str(gap.get("code", "coverage_gap")), [str(gap.get("message", ""))],
            ))
        hits = literature.get("hits") or []
        spans = literature.get("spans") or []
        if len(hits) >= 3:
            obs.append(ResearchObservation(
                "OBS-" + uuid.uuid4().hex[:8], task.task_id, "retrieval_cost", "info",
                "sources=%d spans=%d; lower-budget trial is eligible" % (len(hits), len(spans)),
                [str(literature.get("run_id", ""))],
            ))
        if idea.get("status") == "candidates_need_human":
            obs.append(ResearchObservation(
                "OBS-" + uuid.uuid4().hex[:8], task.task_id, "idea_needs_human", "warn",
                "idea candidates require G1", [str(idea.get("spec_version", ""))],
            ))
        if experiment.get("status") == "needs_human":
            obs.append(ResearchObservation(
                "OBS-" + uuid.uuid4().hex[:8], task.task_id, "design_needs_human", "warn",
                "experiment design needs pre-registration/human", [str(experiment.get("design_id", ""))],
            ))
        if not (figure.get("audit") or {}).get("ok", False):
            obs.append(ResearchObservation(
                "OBS-" + uuid.uuid4().hex[:8], task.task_id, "figure_audit_failed", "error",
                "SVG audit failed", [str(figure.get("figure_id", ""))],
            ))
        pending = [slot for slot in paper.get("slots", []) if slot.get("status") == "pending_evidence"]
        if pending:
            obs.append(ResearchObservation(
                "OBS-" + uuid.uuid4().hex[:8], task.task_id, "paper_pending_evidence", "warn",
                "%d result slots pending evidence" % len(pending), [str(paper.get("title", ""))],
            ))
        return obs

    def run(self, tasks: List[ResearchTask]) -> Dict[str, Any]:
        batch_id = "BATCH-" + uuid.uuid4().hex[:8]
        runs = []
        observations: List[ResearchObservation] = []
        for task in tasks:
            result = PipelineRunner().run(PipelineRequest(
                topic=task.topic,
                language=task.language,
                venue_type=task.venue_type,
                grant_scheme=task.grant_scheme,
                primary_metric=task.primary_metric,
                controls=list(task.controls),
                budget=task.budget,
                max_sources=self.max_sources,
            ))
            task_dir = self.output_dir / task.task_id
            task_dir.mkdir(parents=True, exist_ok=True)
            figure = result.modules["figure"]
            with open(str(task_dir / "figure.svg"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(figure["svg"])
            demo = result.to_dict()
            demo["modules"]["figure"].pop("svg", None)
            demo["figure_uri"] = "figure.svg"
            _write_json(task_dir / "demo.json", demo)
            task_obs = self._observations(task, result.to_dict())
            observations.extend(task_obs)
            runs.append({
                "task": task.__dict__,
                "run_id": result.run_id,
                "status": result.status,
                "figure_id": figure.get("figure_id"),
                "observation_ids": [o.observation_id for o in task_obs],
                "paths": {"demo": str(task_dir / "demo.json"), "figure": str(task_dir / "figure.svg")},
            })
        batch = {
            "fixture": True,
            "batch_id": batch_id,
            "created_at": _now(),
            "note": "Fixture research queue; no API, no real run/EA, no claims.",
            "max_sources": self.max_sources,
            "runs": runs,
            "observations": [o.__dict__ for o in observations],
            "summary": {
                "tasks": len(tasks),
                "runs": len(runs),
                "observations": len(observations),
                "errors": sum(1 for o in observations if o.severity == "error"),
                "max_sources": self.max_sources,
            },
        }
        _write_json(self.output_dir / "research-batch.json", batch)
        return batch


def run_research_cycle(
    tasks: List[ResearchTask],
    ledger_path: Path,
    output_dir: Path,
    human_approve: bool = False,
) -> Dict[str, Any]:
    """Run research first, then a TF-RSI fixture improvement cycle.

    Observations are recorded for the proposer; this fixture candidate is still a
    fixed retrieval-budget policy, not an observation-driven LLM proposal.
    """
    output_dir = Path(output_dir)
    research_dir = output_dir / "research"
    rsi_dir = output_dir / "rsi"
    batch = ResearchRunner(research_dir).run(tasks)
    observation_dicts = batch["observations"]
    cost_observations = [obs for obs in observation_dicts if obs["kind"] == "retrieval_cost"]
    coverage = [obs for obs in observation_dicts if obs["kind"] == "coverage_gap"]
    proposal = None
    trial = None
    duplicate_active = False
    active_before = active_literature_policy(Path(ledger_path), expected_scope="S1/fixture")
    if cost_observations:
        observation_text = "; ".join(
            "%s: %s" % (obs["kind"], obs["message"]) for obs in cost_observations
        )
        if coverage:
            observation_text += "; guard: %d coverage gaps remain and must not increase" % len(coverage)
        try:
            candidate = RuleBasedProposer().propose(observation_text)
            patch = json.loads(candidate.patch)
            policy = RetrievalPolicy("candidate-from-observation", int(patch["max_sources"]))
            duplicate_active = bool(active_before and active_before["max_sources"] == policy.max_sources)
            if duplicate_active:
                proposal = {
                    "candidate_id": candidate.candidate_id,
                    "target": candidate.target,
                    "patch": candidate.patch,
                    "rationale": candidate.rationale,
                    "predicted_effect": candidate.predicted_effect,
                    "recorded": False,
                    "skipped": "duplicate of active lease; no new episode",
                    "trigger": "retrieval_cost",
                    "active_lease": active_before["lease_id"],
                }
            else:
                trial = run_observation_trial(policy, observation_text, ledger_path, rsi_dir, human_approve=human_approve)
                proposal = {
                    "candidate_id": candidate.candidate_id,
                    "target": candidate.target,
                    "patch": candidate.patch,
                    "rationale": candidate.rationale,
                    "predicted_effect": candidate.predicted_effect,
                    "recorded": True,
                    "trigger": "retrieval_cost",
                    "parent_episode": trial.get("parent_episode", ""),
                }
        except (ValueError, KeyError, RuntimeError) as exc:
            proposal = {"error": type(exc).__name__ + ": " + str(exc)}
    active = active_literature_policy(Path(ledger_path), expected_scope="S1/fixture")
    post_lease = None
    if active:
        post_batch = ResearchRunner(
            output_dir / "research-under-lease", max_sources=active["max_sources"]
        ).run(tasks)
        post_lease = {
            "batch_id": post_batch["batch_id"],
            "max_sources": active["max_sources"],
            "lease_id": active["lease_id"],
            "tasks": post_batch["summary"]["tasks"],
            "observations": post_batch["summary"]["observations"],
            "errors": post_batch["summary"]["errors"],
            "path": str(output_dir / "research-under-lease" / "research-batch.json"),
        }
    result = {
        "fixture": True,
        "cycle": "research→observation→proposal→tf-rsi→lease→research",
        "note": "Mechanism test; observation-derived candidate is rule-based, not an LLM proposal.",
        "research": {
            "batch_id": batch["batch_id"],
            "tasks": batch["summary"]["tasks"],
            "observations": batch["summary"]["observations"],
            "errors": batch["summary"]["errors"],
            "max_sources": batch["summary"]["max_sources"],
        },
        "observation_kinds": sorted({obs["kind"] for obs in observation_dicts}),
        "proposal": proposal,
        "rsi": {
            "chosen": trial["candidate"]["policy_id"] if trial else None,
            "would_accept": trial["would_accept"] if trial else None,
            "decision": "active_unchanged" if duplicate_active else (trial["decision"] if trial else "no_candidate"),
            "duplicate_active": duplicate_active,
            "prediction_audit": trial["prediction_audit"] if trial else None,
            "active_policy": active,
            "post_lease_research": post_lease,
            "report": RSIController(StepLedger.load(Path(ledger_path))).report(),
        },
    }
    _write_json(output_dir / "research-cycle.json", result)
    return result
