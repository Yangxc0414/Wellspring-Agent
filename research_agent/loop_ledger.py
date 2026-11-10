"""Stage ledger for the automated research loop.

This is a read-only projection of one run. It shows which stages are complete,
which are skipped in review/position mode, which human gates are still open,
and how many review iterations were actually performed.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .project import run_dir
from .storage import read_json, write_json_atomic

LOOP_SCHEMA = "research-loop-0.1"


def _load(path: Path) -> Any:
    try:
        return read_json(path)
    except Exception:
        return None


def _clean(value: Any, limit: int = 0) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit else text


def _file_status(path: Path, done: str = "done") -> Dict[str, Any]:
    return {
        "status": done if path.is_file() else "not_started",
        "artifact": str(path) if path.is_file() else "",
    }


def _gate(
    gate: str,
    status: str,
    reason: str,
    artifact: str = "",
    human_action: str = "",
) -> Dict[str, Any]:
    return {
        "gate": gate,
        "status": status,
        "reason": reason,
        "artifact": artifact,
        "human_action": human_action,
    }


def _overturned_comparisons(project: Path, package: Path) -> List[str]:
    """Comparisons this package decided that a higher-power package on the same dataset undoes.

    Pointing a human at ``study claim`` for a verdict the project's own data already overturned
    would be the runtime volunteering a bad signature.
    """
    from .study_replication import build_replication_report, comparability_key, load_package

    current = load_package(package)
    if not current:
        return []
    key = comparability_key(current)
    report = build_replication_report(project / "studies", siblings=True)
    return sorted(
        {
            str(item["comparison"])
            for item in report.get("overturned") or []
            if item.get("design_key") == key
            and item.get("dataset") == current["dataset"]
            # the entry must have been decided *by this package*; the higher-power package that
            # did the overturning keeps its own verdict
            and item.get("decided_at", {}).get("directory") == current["directory"]
        }
    )


def _replication_action(
    project: Path, package: Path, evidence: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """One dataset decides one dataset. Say so, and name the dataset that would test it.

    The action disappears by itself: once the same design exists on a second dataset,
    ``study replicate`` puts that design in a replicated group, so there is nothing left to
    suggest here.
    """
    from .search_lab import DATASETS
    from .study_replication import build_replication_report, design_labels

    spec = _load(package / "study-spec.json") or {}
    raw_design = spec.get("design") if isinstance(spec.get("design"), dict) else {}
    design = design_labels(raw_design)
    if not design:
        return []
    own_dataset = str(evidence.get("dataset") or "")
    report = build_replication_report(project / "studies", siblings=True)
    for group in report.get("replicated") or []:
        if group.get("design") == design:
            return []
    datasets: set = set()
    for item in report.get("unreplicated") or []:
        if item.get("design") == design:
            datasets = {str(name) for name in item.get("datasets") or []}
    if datasets != {own_dataset}:
        # A design this ledger did not just execute (or that is already grouped) gets no advice;
        # guessing which package the caller means would be inventing a relation.
        return []
    untried = sorted(set(DATASETS) - datasets)
    if not untried:
        return []
    factors = " ".join(
        "--factors %s=%s" % (factor, ",".join(str(level) for level in levels))
        for factor, levels in sorted(design.items())
        if len(levels) > 1
    )
    origin = _load(package / "study-origin.json") or {}
    idea_id = str(origin.get("idea_id") or "")
    origin_run = str(origin.get("run_id") or "")
    if idea_id and origin_run:
        # Prefer the idea-bound command: replicating on another environment through
        # ``study from-idea`` keeps the hypothesis attached to the new package.
        command = (
            "python -m research_agent study from-idea --project %s --run-id %s --idea-id %s "
            "--seeds %s --budget %s --datasets %s && python -m research_agent study replicate "
            "--project %s"
            % (
                project,
                origin_run,
                idea_id,
                ",".join(str(seed) for seed in (evidence.get("seeds") or [])),
                evidence.get("budget") or 60,
                ",".join(untried),
                project,
            )
        )
    else:
        command = "python -m research_agent study search --project %s --dataset %s " \
            "--seeds %s --budget %s %s && python -m research_agent study replicate --project %s" % (
            project,
            untried[0],
            ",".join(str(seed) for seed in (evidence.get("seeds") or [])),
            evidence.get("budget") or 60,
            factors,
            project,
        )
    return [
        {
            "kind": "study_replication",
            "stage": "S5",
            "study_dir": str(package),
            "datasets_present": sorted(datasets),
            "datasets_untried": untried,
            "idea_bound": bool(idea_id and origin_run),
            "message": (
                "this design was executed on %s only: an interval that excludes zero there says "
                "nothing about whether the effect generalises; run the same design on %s and read "
                "`study replicate`, which counts the datasets that decide rather than the datasets "
                "that were tried"
                % (own_dataset, ", ".join(untried))
            ),
            "command": command,
        }
    ]


def _idea_package(project: Path, idea_id: str, declared_dataset: str) -> Optional[Path]:
    """The package that stands for this idea, whether it ran on one environment or several.

    ``study from-idea --datasets all`` writes ``STUDY-<idea>-<dataset>`` per environment. Matching
    only ``STUDY-<idea>`` would report an executed idea as never executed, and the caller would be
    told to re-run four studies that are already on disk.
    """
    root = project / "studies"
    exact = root / ("STUDY-%s" % idea_id)
    if (exact / "study.json").is_file():
        return exact
    if not root.is_dir():
        return None
    prefix = "STUDY-%s-" % idea_id
    siblings = sorted(
        directory
        for directory in root.iterdir()
        if directory.is_dir()
        and directory.name.startswith(prefix)
        and (directory / "study.json").is_file()
    )
    if not siblings:
        return None
    preferred = [
        directory
        for directory in siblings
        if directory.name == prefix + str(declared_dataset or "")
    ]
    return preferred[0] if preferred else siblings[0]


def _baseline_candidate(package: Path, dataset: str, seeds: List[int]) -> str:
    """A tuned-baseline report the user already generated next to this study, if any.

    The guidance may only name a path it has checked: dataset and seed overlap are verified here
    so a bound opponent cannot be an unrelated environment's numbers.
    """
    for directory in (package, package.parent):
        try:
            candidates = sorted(directory.glob("tuned-baseline*.json"))
        except OSError:
            return ""
        for path in candidates:
            data = _load(path)
            if not isinstance(data, dict):
                continue
            if str(data.get("dataset") or "") != dataset:
                continue
            reported = [int(seed) for seed in (data.get("seeds") or [])]
            if reported and seeds and not set(reported) & set(seeds):
                continue
            return str(path)
    return ""


def pending_study_actions(
    project: Path, run_id: str, innovation: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Turn an executable idea into the next concrete step, without executing it here.

    A search study is deterministic local compute, but it is still an experiment: the ledger
    points at the CLI command instead of running it, the same way it points at
    ``experiment approve``. Ideas that already have a package stop nagging and move the caller
    on to the claim gate.
    """
    from .search_lab import DATASETS

    ideas = list(innovation.get("selected_ideas") or []) or list(innovation.get("final_ideas") or [])
    actions: List[Dict[str, Any]] = []
    for idea in ideas[:3]:
        idea_id = str(idea.get("idea_id") or "").strip()
        plan = idea.get("experiment_plan") or {}
        if not idea_id or str(plan.get("profile") or "") != "search_factorial":
            continue
        package = _idea_package(project, idea_id, str(plan.get("dataset") or ""))
        if package is not None:
            origin = _load(package / "study-origin.json") or {}
            evidence = _load(package / "study-evidence.json") or {}
            signable = [
                name
                for name, item in (evidence.get("comparison") or {}).items()
                if item.get("ci95_low") is not None
                and (item["ci95_low"] > 0 or item["ci95_high"] < 0)
            ]
            overturned = _overturned_comparisons(project, package)
            dropped = [name for name in signable if name in overturned]
            signable = [name for name in signable if name not in overturned]
            spec = _load(package / "study-spec.json") or {}
            from .search_lab import code_fingerprint

            code_stale = bool(spec.get("code_fingerprint")) and str(
                spec.get("code_fingerprint")
            ) != code_fingerprint()
            prereg = _load(package / "study-preregistration.json") or {}
            declared_baseline = (
                prereg.get("baseline") if isinstance(prereg.get("baseline"), dict) else None
            )
            dataset_seeds = [int(seed) for seed in (evidence.get("seeds") or [])]
            baseline_path = package / "tuned-baseline.json"
            candidate = ""
            if not baseline_path.is_file():
                candidate = _baseline_candidate(
                    package, str(evidence.get("dataset") or ""), dataset_seeds
                )
            if not (package / "claim-draft.json").is_file() and not (package / "claim.json").is_file():
                actions.append(
                    {
                        "kind": "human_gate" if signable else "study_no_finding",
                        "gate": "S5b" if signable else "S5",
                        "idea_id": idea_id,
                        "study_dir": str(package),
                        "decidable_comparisons": signable,
                        "overturned_comparisons": dropped,
                        "claimable": bool(signable),
                        "message": (
                            "study executed; %d comparison(s) have an interval excluding zero; "
                            "draft and sign the claim in the CLI"
                            % len(signable)
                            if signable
                            else "study executed but no comparison excludes zero: this is a "
                                 "non-result. Add seeds/budget or narrow the claim; do not "
                                 "re-run until a directional finding appears. No claim command "
                                 "is offered, because signing a non-result is the failure this "
                                 "gate exists to stop."
                        )
                        + (
                            " %s was decided by this package but a higher-power study on the same "
                            "dataset does not decide it, so it is not offered as a signable basis"
                            % ", ".join(dropped)
                            if dropped
                            else ""
                        )
                        + (
                            (
                                " | no tuned baseline is bound and none was found beside this "
                                "study: this claim would compare only with the study's own "
                                "reference cell, so run `study baseline --study <study.json> "
                                "--output <file>` first"
                                if not (baseline_path.is_file() or candidate)
                                else (
                                    " | opponent bound in the package as tuned-baseline.json"
                                    if baseline_path.is_file()
                                    else " | opponent available at %s: bind it with --baseline-file"
                                    % candidate
                                )
                            )
                            if signable
                            else ""
                        )
                        + (
                            " | the declared plan carries no baseline slot, so closure will warn "
                            "that the opponent was chosen after the run"
                            if signable and declared_baseline is None
                            else ""
                        )
                        + (
                            " | NOTE closure will block at code.unchanged: the search code changed "
                            "since this package ran, so re-verify with "
                            "`study closure --verify-repro` before treating it as closable"
                            if code_stale
                            else ""
                        ),
                        "tuned_baseline": {
                            "bound": baseline_path.is_file(),
                            "candidate": candidate,
                            "declared": declared_baseline,
                            "bound_in_command": bool(baseline_path.is_file() or candidate),
                        },
                        "code_stale": bool(code_stale),
                        "command": (
                            "python -m research_agent study claim --study-dir %s "
                            "--statement \"...\" --human-reason \"...\" --scope %s/%s%s"
                            % (
                                package,
                                run_id,
                                idea_id,
                                (
                                    " --baseline-file %s"
                                    % (baseline_path if baseline_path.is_file() else candidate)
                                    if (baseline_path.is_file() or candidate)
                                    else ""
                                ),
                            )
                            if signable
                            else "python -m research_agent study replicate --project %s" % project
                        ),
                    }
                )
            actions.extend(_replication_action(project, package, evidence))
            continue
        if str(plan.get("dataset") or "") not in DATASETS:
            continue
        actions.append(
            {
                "kind": "study_execution",
                "stage": "S5",
                "idea_id": idea_id,
                "dataset": str(plan.get("dataset") or ""),
                "metric": str(plan.get("metric") or ""),
                "falsification": str(idea.get("falsification") or ""),
                "message": (
                    "this idea is bound to an executable search profile but no study package "
                    "exists yet; running it produces evidence whose provenance names the idea"
                ),
                "replication_option": "--datasets all",
                "replication_note": (
                    "one package per registered environment, each keeping this idea's provenance, "
                    "so a generalising result stays traceable to the hypothesis that predicted it"
                ),
                "command": (
                    "python -m research_agent study from-idea --project %s --run-id %s "
                    "--idea-id %s --seeds 1,2,3,4,5,6,7,8 --budget 60"
                    % (project, run_id, idea_id)
                ),
            }
        )
    return actions


def build_loop_ledger(
    project: Path,
    run_id: str,
    *,
    output_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    target = run_dir(project, run_id)
    if not target.is_dir():
        raise ValueError("run does not exist: " + run_id)
    task = _load(target / "task.json") or {}
    plan = task.get("plan") if isinstance(task.get("plan"), dict) else {}
    q0 = _load(target / "q0.json") or {}
    design_audit = _load(target / "design-audit.json") or {}
    innovation = _load(target / "innovation-review.json") or {}
    review_candidates = sorted(
        target.glob("manuscript-review*/manuscript-review.json"),
        key=lambda path: path.stat().st_mtime,
    )
    manuscript_review = _load(review_candidates[-1]) if review_candidates else {}
    claim = _load(target / "claim" / "claim.json") or {}
    claim_draft = _load(target / "run" / "claim-draft.json") or {}
    capsule = _load(target / "run" / "run-capsule.json") or {}
    has_writing = (target / "writing-pack.json").is_file()
    has_synthesis = (target / "synthesis-matrix.json").is_file()
    has_innovation = (target / "innovation-review.json").is_file()
    has_experiment = (target / "experiment.json").is_file()
    has_run = bool(capsule)
    has_claim = str(claim.get("status") or "") in ("supported", "approved")
    review_mode = not has_run and (has_writing or has_innovation)
    mode = "review" if review_mode else "empirical"

    def stage(stage_id: str, name: str, artifacts: List[Path], note: str = "") -> Dict[str, Any]:
        found = [path for path in artifacts if path.is_file()]
        return {
            "stage_id": stage_id,
            "name": name,
            "status": "done" if found else "not_started",
            "artifacts": [str(path) for path in found],
            "note": note,
        }

    stages = [
        stage("S0", "问题框定与路由", [target / "task.json", target / "task-plan.json"]),
        stage("S1", "多源检索与全文阅读", [target / "literature-ledger.json", target / "literature.json"]),
        stage("S1b", "跨来源综合矩阵", [target / "synthesis-matrix.json"]),
        stage("S2-S3", "缺口与创新评审", [target / "innovation-review.json"]),
        stage("S4", "实验设计", [target / "experiment.json"]),
        stage("S5", "本地实验执行", [target / "run" / "run-capsule.json", target / "run" / "ea.json"]),
        stage("S5b", "Claim 草稿/签核", [target / "run" / "claim-draft.json", target / "claim" / "claim.json"]),
        stage("S6", "图表", [target / "figure.scene.json", target / "run" / "result-figure.svg"]),
        stage(
            "S8-S12",
            "写作包与手稿评审",
            [
                target / "writing-pack.json",
                review_candidates[-1] if review_candidates else target / "manuscript-review" / "manuscript-review.json",
            ],
        ),
        stage("S13-S16", "闭包与签核", [target / "closure" / "closure-report.json", target / "closure-signature" / "signature.json"]),
    ]
    stage_by_id = {item["stage_id"]: item for item in stages}
    for stage_id in ("S4", "S5", "S5b", "S13-S16"):
        if review_mode and stage_by_id[stage_id]["status"] == "not_started":
            stage_by_id[stage_id]["status"] = "skipped_review_mode"
            stage_by_id[stage_id]["note"] = "review/position mode; no new experiment or claim"
    if has_experiment and not has_run:
        stage_by_id["S4"]["note"] = "design exists; execution not started"
    if claim_draft and not has_claim:
        stage_by_id["S5b"]["status"] = "needs_human"
        stage_by_id["S5b"]["note"] = "claim draft exists; human signature required"

    gates = []
    q0_status = str(q0.get("status") or "not_recorded")
    gates.append(
        _gate(
            "Q0",
            "pass" if q0_status == "pass" else q0_status,
            str(q0.get("reason") or "Q0 artifact not recorded"),
            str(target / "q0.json") if (target / "q0.json").is_file() else "",
        )
    )
    g1_file = target / "g1-decision.json"
    gates.append(
        _gate(
            "G1",
            "pass"
            if g1_file.is_file()
            else ("skipped_review_mode" if review_mode else ("pending_human" if has_innovation else "not_started")),
            "idea selection" if has_innovation else "no innovation candidates yet",
            str(g1_file) if g1_file.is_file() else "",
            "human selects one candidate and writes a G1 decision",
        )
    )
    protocol = target / "protocol" / "protocol-card.json"
    gates.append(
        _gate(
            "G2",
            "pass"
            if protocol.is_file()
            else ("skipped_review_mode" if review_mode else ("pending_human" if has_experiment else "not_started")),
            "design audit=%s" % (_clean(design_audit.get("status")) or "missing"),
            str(protocol) if protocol.is_file() else "",
            "human checks baseline/metric/seeds and freezes the protocol",
        )
    )
    gates.append(
        _gate(
            "S5b",
            "pass"
            if has_claim
            else ("skipped_review_mode" if review_mode else ("needs_human" if claim_draft else "not_started")),
            "claim status=%s" % (_clean(claim.get("status")) or ("draft" if claim_draft else "missing")),
            str(target / "claim" / "claim.json") if has_claim else "",
            "human inspects RunCapsule/EA and signs the claim",
        )
    )
    signature = target / "closure-signature" / "signature.json"
    gates.append(
        _gate(
            "G5",
            "pass" if signature.is_file() else ("skipped_review_mode" if review_mode else "not_started"),
            "closure signature" if signature.is_file() else "closure not signed",
            str(signature) if signature.is_file() else "",
            "human signs the export after closure review",
        )
    )

    innovation_rounds = [
        item.get("overall") for item in innovation.get("iterations") or []
    ]
    review_scores = list(manuscript_review.get("score_progression") or [])
    iterations = {
        "innovation_rounds": len(innovation_rounds),
        "innovation_scores": innovation_rounds,
        "manuscript_rounds": len(review_scores),
        "manuscript_scores": review_scores,
        "accepted_revisions": manuscript_review.get("accepted_revisions", 0),
        "synthesis_themes": len((_load(target / "synthesis-matrix.json") or {}).get("themes") or []),
    }
    next_actions = []
    if review_mode:
        next_actions.append(
            {
                "kind": "mode_boundary",
                "message": "This run is a review/position study; S4/S5/S5b are intentionally skipped. Run an empirical mode with a local dataset to obtain a claim.",
            }
        )
    if claim_draft and not has_claim:
        next_actions.append(
            {
                "kind": "human_gate",
                "gate": "S5b",
                "message": "Claim draft is ready; inspect EA and sign in the CLI.",
                "artifact": str(target / "run" / "claim-draft.json"),
            }
        )
    if manuscript_review.get("status") == "needs_more_work":
        next_actions.append(
            {
                "kind": "review",
                "message": "Manuscript rubric score is below threshold; run another revision/review round or revise manually.",
                "score": manuscript_review.get("best_score"),
            }
        )
    if not has_synthesis:
        next_actions.append(
            {
                "kind": "synthesis",
                "message": "No multi-source synthesis matrix; run `literature synthesize` before writing.",
            }
        )
    study_actions = pending_study_actions(project, run_id, innovation)
    if study_actions:
        next_actions.extend(study_actions)
    result = {
        "schema_version": LOOP_SCHEMA,
        "run_id": run_id,
        "mode": mode,
        "task": {
            "route": plan.get("route") or task.get("task_type"),
            "status": task.get("status"),
            "goal": plan.get("goal") or task.get("goal"),
            "stopped_at": task.get("stopped_at"),
        },
        "stages": stages,
        "gates": gates,
        "iterations": iterations,
        "next_actions": next_actions,
        "automation_boundary": (
            "Retrieval, synthesis, innovation review, drafting, rubric review and revision are "
            "automated or model-assisted. G1/G2/S5b/G5 and all claims/signatures remain human-only."
        ),
    }
    destination = Path(output_dir) if output_dir else target
    destination.mkdir(parents=True, exist_ok=True)
    write_json_atomic(destination / "research-loop.json", result)
    lines = [
        "# Research Loop",
        "",
        "- run: `%s`" % run_id,
        "- mode: `%s`" % mode,
        "- route: `%s`" % (task.get("route") or "-"),
        "",
        "## Stages",
        "",
        "| Stage | Name | Status | Artifacts |",
        "| --- | --- | --- | --- |",
    ]
    for item in stages:
        lines.append(
            "| %s | %s | %s | %s |"
            % (
                item["stage_id"],
                item["name"],
                item["status"],
                ", ".join("`%s`" % Path(path).name for path in item["artifacts"]) or "-",
            )
        )
    lines += ["", "## Gates", ""]
    for item in gates:
        lines.append(
            "- %s: `%s` — %s" % (item["gate"], item["status"], item["reason"])
        )
    lines += [
        "",
        "## Iterations",
        "",
        "- innovation: %d rounds %s"
        % (iterations["innovation_rounds"], iterations["innovation_scores"]),
        "- synthesis themes: %d" % iterations["synthesis_themes"],
        "- manuscript: %d rounds %s; accepted revisions=%d"
        % (
            iterations["manuscript_rounds"],
            iterations["manuscript_scores"],
            iterations["accepted_revisions"],
        ),
        "",
        "## Next actions",
        "",
    ]
    for action in next_actions:
        lines.append("- [%s] %s" % (action.get("kind"), action.get("message")))
    lines += ["", result["automation_boundary"], ""]
    (destination / "research-loop.md").write_text("\n".join(lines), encoding="utf-8")
    return result
