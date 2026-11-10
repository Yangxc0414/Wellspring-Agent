"""Run the experiment an idea actually asked for, instead of describing it in prose.

The loop this closes is the one the whole system exists for: S2/S3 produces an idea whose
``experiment_plan`` is bound to an executable profile, and until now nothing executed it — the
plan was only ever rendered into the writing prompt. Here the plan is validated against the same
registry the critic read, turned into a declared design, and run as a study whose artifacts are
the ones the claim and closure paths already accept.

The idea's own words (statement, falsification, plan) are recorded in a sidecar bound to the study
hash, so a later reader can see which hypothesis the numbers were produced to test — and which
result would have refuted it.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .executable import validate_plan
from .project import run_dir
from .search_lab import (
    DATASETS,
    DEFAULT_SEEDS,
    code_fingerprint,
    normalize_design,
    spec_sha256_of,
    study_profile_summary,
    write_study_package,
)
from .storage import read_json, write_json_atomic

ORIGIN_SCHEMA = "study-origin-0.1"
EXECUTABLE_PROFILE = "search_factorial"
DEFAULT_MIN_DELTA = 0.005
ORIGIN_BOUNDARY = (
    "running an idea's plan executes the design it declared: it does not confirm the idea, does "
    "not sign a claim, and an executed study whose intervals cover zero is a non-result rather "
    "than a failure to be re-run away"
)


class StudyFromIdeaError(ValueError):
    """The idea cannot be executed here, stated with the reason the plan failed."""


def _load_idea(project: Path, run_id: str, idea_id: str) -> Dict[str, Any]:
    target = run_dir(project, run_id)
    review = read_json(target / "innovation-review.json")
    if not review:
        raise StudyFromIdeaError(
            "no innovation-review.json in %s; run `innovation review` first" % run_id
        )
    ideas = list(review.get("selected_ideas") or []) + list(review.get("final_ideas") or [])
    for idea in ideas:
        if str(idea.get("idea_id")) == idea_id:
            return idea
    raise StudyFromIdeaError(
        "idea %s is not in %s; known ids: %s"
        % (idea_id, run_id, ", ".join(sorted(str(item.get("idea_id")) for item in ideas)))
    )


def plan_to_controls(plan: Dict[str, Any]) -> Dict[str, Any]:
    """Translate an idea's plan into the runner's declared design.

    ``design`` levels are passed through as declared (the runner's own validation decides), while
    dataset and metric are checked against the registry here so an idea bound to a different
    profile never reaches the runner.
    """
    executable = validate_plan(plan)
    if not executable.get("ok"):
        raise StudyFromIdeaError(
            "plan is not executable here: " + "; ".join(executable.get("reasons") or [])
        )
    profile = str(executable.get("profile") or plan.get("profile") or "")
    if profile != EXECUTABLE_PROFILE:
        raise StudyFromIdeaError(
            "only %s ideas can be executed as a study; this plan binds profile=%s"
            % (EXECUTABLE_PROFILE, profile or "unset")
        )
    dataset = str(plan.get("dataset") or "").strip()
    if dataset not in DATASETS:
        raise StudyFromIdeaError(
            "dataset %s is not available to %s; use %s"
            % (dataset or "(empty)", EXECUTABLE_PROFILE, ", ".join(sorted(DATASETS)))
        )
    metric = str(plan.get("metric") or "").strip()
    min_delta = plan.get("min_delta")
    min_delta = float(min_delta) if isinstance(min_delta, (int, float)) else DEFAULT_MIN_DELTA
    declared = plan.get("design")
    design = None
    if isinstance(declared, dict) and declared:
        design = {
            str(factor): [str(level) for level in levels] if levels else []
            for factor, levels in declared.items()
        }
    if design is None:
        # The runner's default is memory x gate. A plan that names another registered factor
        # in prose would silently execute that default instead of the design it describes.
        factors = (study_profile_summary().get("factors") or {})
        text = ("%s %s" % (plan.get("baseline") or "", plan.get("stopping_rule") or "")).lower()
        mentioned = sorted(name for name in factors if name.lower() in text)
        if mentioned:
            raise StudyFromIdeaError(
                "plan mentions registered factors (%s) but carries no experiment_plan.design; "
                "refusing to fall back to the default memory x gate design" % ", ".join(mentioned)
            )
    return {
        "dataset": dataset,
        "metric": metric or "improvement_per_evaluation",
        "design": design,
        "min_delta": min_delta,
        "stopping_rule": str(plan.get("stopping_rule") or ""),
        "profile": profile,
    }


def plan_from_design(
    design: Dict[str, Any], dataset: str, seeds_override: int = 0
) -> Dict[str, Any]:
    """Map a pipeline experiment design onto the search arm, or let validation refuse it.

    The study measures search efficiency; the design's own ``primary_metric`` is the inner
    objective being improved, so it travels as context rather than being used as the study
    metric. Reporting the inner metric as the study outcome is the same 口径混淆 that made an
    earlier draft fill ``dataset`` with literature corpus names.
    """
    declared = str((design or {}).get("primary_metric") or "").strip()
    declared_seeds = int((design or {}).get("seeds") or 0)
    if int(seeds_override or 0) >= 4:
        # An explicit operator override is a stated design decision, not a silent change.
        declared_seeds = int(seeds_override)
    if declared_seeds and declared_seeds < 4:
        raise StudyFromIdeaError(
            "the design declares %d seeds, but the study arm needs at least 4 paired seeds "
            "before an interval is interpreted; pass --study-seeds to override the design"
            % declared_seeds
        )
    return {
        "profile": "search_factorial",
        "dataset": str(dataset or "").strip(),
        "baseline": str((design or {}).get("baseline") or "no archive, no acceptance gate"),
        "metric": "improvement_per_evaluation",
        "stopping_rule": "%d paired seeds under a fixed validation budget"
        % (declared_seeds or DEFAULT_SEEDS),
        "declared_primary_metric": declared,
    }


def named_factor_terms(text: str) -> set:
    """Which control names the idea's own words refer to.

    The vocabulary is `study_claims.FACTOR_KEYWORDS`, so the check that refuses a run before
    compute and the guard that refuses a claim after it cannot drift apart.
    """
    from .study_claims import FACTOR_KEYWORDS

    lowered = str(text or "").lower()
    found = set()
    for factor, terms in FACTOR_KEYWORDS.items():
        for term in terms:
            if str(term).lower() in lowered:
                found.add(factor)
                break
    return found


def plan_testability(plan_text: str, design: Dict[str, Any]) -> Tuple[str, str]:
    """Refuse to burn compute on a plan whose hypothesis names only held-fixed controls.

    Measured on the real batch: an idea about narrowing the operator space shipped a plan that set
    ``operators`` to one level, so the run produced cells about memory and gate, and the claim guard
    caught the mismatch only after the compute was already spent. A study that cannot address any
    factor its own words name is not a partially informative study, it is the wrong study. When at
    least one named factor is varied, the fixed ones are context controls and only recorded.
    """
    levels = {str(key): value for key, value in (design or {}).items() if isinstance(value, list)}
    varied = {key for key, value in levels.items() if len(value) > 1}
    fixed = {key for key, value in levels.items() if len(value) == 1}
    named = named_factor_terms(plan_text)
    if not named or not fixed or not varied:
        return "", ""
    if not (named & varied):
        return (
            "the idea's own words name %s, but this plan holds every one of them at a single level, "
            "so no comparison in the study can address them. Vary the named factor(s) in "
            "experiment_plan.design (registered: %s) or state the idea about what is actually "
            "varied (%s); refusing to run compute that cannot test its own hypothesis."
            % (", ".join(sorted(named)), ", ".join(sorted(levels)), ", ".join(sorted(varied)))
        ), ""
    context = sorted(named & fixed)
    if not context:
        return "", ""
    return "", (
        "the idea also names %s, which this design holds at a single level: those are context "
        "controls here, not tested contrasts, so nothing about them is measured even though the "
        "study is about a factor the sentence mentions" % ", ".join(context)
    )


def execute_study_plan(
    directory: Path,
    plan: Dict[str, Any],
    *,
    provenance: Dict[str, Any],
    seeds: Optional[List[int]] = None,
    budget: int = 60,
    force: bool = False,
    preregistration: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate a plan, run it as a study, and write the provenance sidecar.

    Shared by ``study from-idea`` and the pipeline's study arm so both produce the same
    package shape; a second implementation of the no-overwrite and escalation rules is how
    two entry points start disagreeing about the same evidence.

    ``preregistration`` is the same declared plan ``study search --preregistration`` takes. It is
    validated before anything is computed, so the plan is on record while the result is still
    unknown; without it an idea-attributed study could never carry a pre-registration, which is
    how the two evidence items came to co-occur in zero packages.
    """
    controls = plan_to_controls(plan)
    design = normalize_design(controls["design"], controls["min_delta"])
    refusal, context_warning = plan_testability(
        " ".join([str(provenance.get(key) or "") for key in ("idea_title", "hypothesis", "falsification")])
        + " " + str(plan.get("stopping_rule") or ""),
        design,
    )
    if refusal:
        raise StudyFromIdeaError(refusal)
    seeds = [int(seed) for seed in (seeds or list(range(1, DEFAULT_SEEDS + 1)))]
    if len(seeds) < 4:
        raise StudyFromIdeaError(
            "a study needs at least 4 paired seeds before any interval is interpreted; "
            "got %d" % len(seeds)
        )
    directory = Path(directory)
    previous = read_json(directory / "study-origin.json") or {}
    previous_controls = (previous.get("resolved_controls") or {}) if previous else {}
    if (directory / "study.json").is_file() and not force:
        raise StudyFromIdeaError(
            "%s already holds a study; pass --force to replace it (the previous conclusion "
            "would otherwise be overwritten without a trace)" % directory
        )
    prereg = None
    if preregistration:
        from .study_preregistration import assert_matches_run, load_preregistration

        prereg = load_preregistration(Path(preregistration))
        assert_matches_run(
            prereg,
            design=design,
            seeds=seeds,
            budget=int(budget),
            dataset=controls["dataset"],
        )
    result = write_study_package(
        directory,
        dataset=controls["dataset"],
        seeds=seeds,
        budget=int(budget),
        min_delta=controls["min_delta"],
        design=design,
    )
    if prereg is not None:
        from .study_preregistration import bind_sidecar

        bind_sidecar(directory, prereg, read_json(directory / "study.json") or {})
    spec = read_json(directory / "study-spec.json") or {}
    revised_from: Optional[Dict[str, Any]] = None
    if previous and previous_controls:
        changed = {
            key: value
            for key, value in (
                ("seeds", len(previous_controls.get("seeds") or []) != len(seeds)),
                ("budget", previous_controls.get("budget") != int(budget)),
                ("design", previous_controls.get("design") != design),
                ("dataset", previous_controls.get("dataset") != controls["dataset"]),
            )
            if value
        }
        if changed:
            # Raising seeds or budget is a design decision that changes what the study can
            # conclude, so it is recorded rather than left as an untraceable re-run.
            revised_from = {
                "changed": sorted(changed),
                "previous_seeds": len(previous_controls.get("seeds") or []),
                "previous_budget": previous_controls.get("budget"),
                "previous_study_sha256": previous.get("study_sha256", ""),
                "previous_study_spec_sha256": previous.get("study_spec_sha256", ""),
                "note": (
                    "this package replaces an earlier run of the same idea with different power; "
                    "the previous result is no longer on disk and must not be cited alongside "
                    "these numbers"
                ),
            }
    origin = {
        "schema_version": ORIGIN_SCHEMA,
        "project_dir": str(provenance.get("project_dir") or ""),
        "run_id": str(provenance.get("run_id") or ""),
        "idea_id": str(provenance.get("idea_id") or ""),
        "idea_title": str(provenance.get("idea_title") or ""),
        "hypothesis": str(provenance.get("hypothesis") or ""),
        "falsification": str(provenance.get("falsification") or ""),
        "source": str(provenance.get("source") or "innovation_review"),
        "experiment_plan": plan,
        "resolved_controls": {
            "dataset": controls["dataset"],
            "metric": controls["metric"],
            "min_delta": controls["min_delta"],
            "design": design,
            "seeds": seeds,
            "budget": int(budget),
        },
        "study_spec_sha256": spec_sha256_of(spec),
        "study_sha256": str(spec.get("study_sha256") or ""),
        "revised_from": revised_from,
        "code_fingerprint": code_fingerprint(),
        "boundary": ORIGIN_BOUNDARY,
    }
    write_json_atomic(directory / "study-origin.json", origin)
    return {
        "status": "executed",
        "warnings": [context_warning] if context_warning else [],
        "study_dir": str(directory),
        "origin_file": str(directory / "study-origin.json"),
        "preregistered": bool(prereg),
        "idea_id": origin["idea_id"],
        "dataset": controls["dataset"],
        "metric": controls["metric"],
        "design": design,
        "seeds": seeds,
        "budget": int(budget),
        "hashes": result["hashes"],
        "decomposition": result["decomposition"],
        "comparison": result["comparison"],
        "directional_supported": result["directional_supported"],
        "interval_covers_zero": result["interval_covers_zero"],
        "underpowered": result["underpowered"],
        "revised_from": revised_from,
        "next": (
            "study claim --study-dir %s --statement ... --human-reason ... --scope %s/%s, then "
            "study closure --study-dir %s"
            % (directory, origin["run_id"] or "RUN", origin["idea_id"] or "PLAN", directory)
        ),
        "boundary": ORIGIN_BOUNDARY,
    }


def _requested_datasets(datasets: Optional[Any], plan: Dict[str, Any]) -> List[str]:
    """Which environments to execute. Empty means "the one the idea declared".

    Validated in full before anything runs, so a typo cannot leave a half-written replication set.
    """
    if not datasets:
        return []
    if isinstance(datasets, str) and datasets.strip().lower() == "all":
        names = sorted(DATASETS)
    elif isinstance(datasets, str):
        names = [item.strip() for item in datasets.replace(";", ",").split(",") if item.strip()]
    else:
        names = [str(item).strip() for item in datasets if str(item).strip()]
    unknown = sorted(set(names) - set(DATASETS))
    if unknown:
        raise StudyFromIdeaError(
            "environment %s is not executable here; the registry offers %s"
            % (", ".join(unknown), ", ".join(sorted(DATASETS)))
        )
    if len(set(names)) != len(names):
        raise StudyFromIdeaError(
            "the same environment appeared twice (%s): one package per environment is what "
            "replication counts" % ", ".join(sorted({n for n in names if names.count(n) > 1}))
        )
    return names


def run_study_from_idea(
    project: Path,
    run_id: str,
    idea_id: str,
    *,
    seeds: Optional[List[int]] = None,
    budget: int = 60,
    output_root: Optional[Path] = None,
    force: bool = False,
    datasets: Optional[Any] = None,
    preregistration: Optional[str] = None,
) -> Dict[str, Any]:
    project = Path(project).resolve()
    idea = _load_idea(project, run_id, idea_id)
    plan = idea.get("experiment_plan") or {}
    names = _requested_datasets(datasets, plan)
    if preregistration and names and len(names) > 1:
        raise StudyFromIdeaError(
            "one declared plan binds one dataset: %s would be checked against %d datasets and "
            "could only match one of them. Run one dataset per plan so each pre-registration "
            "says in advance what it is testing." % (preregistration, len(names))
        )
    root = output_root or project / "studies"
    directories = [
        root / ("STUDY-%s" % idea_id if not names else "STUDY-%s-%s" % (idea_id, name))
        for name in (names or [str(plan.get("dataset") or "")])
    ]
    if not force:
        occupied = [str(d) for d in directories if (d / "study.json").is_file()]
        if occupied:
            raise StudyFromIdeaError(
                "%s already hold%s a study; pass --force to replace %s (the previous conclusion "
                "would otherwise be overwritten without a trace)"
                % (
                    ", ".join(occupied),
                    "s" if len(occupied) == 1 else "",
                    "it" if len(occupied) == 1 else "them",
                )
            )
    provenance = {
        "project_dir": str(project),
        "run_id": run_id,
        "idea_id": idea_id,
        "idea_title": idea.get("title"),
        "hypothesis": idea.get("mechanism"),
        "falsification": idea.get("falsification"),
        "source": "innovation_review",
    }
    results: List[Dict[str, Any]] = []
    for name, directory in zip(names or [None], directories):
        results.append(
            execute_study_plan(
                directory,
                dict(plan) if name is None else dict(plan, dataset=name),
                provenance=provenance,
                seeds=seeds,
                budget=budget,
                force=force,
                preregistration=preregistration,
            )
        )
    if len(results) == 1:
        return results[0]
    return {
        "status": "executed",
        "idea_id": idea_id,
        "datasets": names,
        "studies": [
            {"dataset": item["dataset"], "study_dir": item["study_dir"], "design": item["design"]}
            for item in results
        ],
        "next": (
            "python -m research_agent study replicate --project %s" % project
        ),
        "boundary": (
            "these packages share one declared design and differ only in environment, so "
            "`study replicate` may count them as replication; each keeps the idea's own "
            "provenance, so a generalising result is still traceable to the hypothesis that "
            "predicted it"
        ),
    }
