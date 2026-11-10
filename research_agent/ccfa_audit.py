"""CCF-A experiment-design audit derived from top-venue experiment skills.

The checklist is a deterministic projection of the NeurIPS / ICML / ICLR experiment skills in
Awesome-Journal-Skills: claims mapped to evidence, tuned and compute-matched baselines,
single-mechanism ablations, variance, leakage/split documentation, compute disclosure,
robustness and negative results. It is not a venue decision and not peer review; it tells a
human which required disclosures are missing before G2.

The run design in ``experiment.json`` is a local protocol validation and is not a study design.
This audit expects the separate ``study-design.json`` shape and refuses a run design when the
caller asks for a CCF-A check.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

STUDY_DESIGN_SCHEMA = "study-design-0.1"
AUDIT_SCHEMA = "ccfa-design-audit-0.1"
BOUNDARY = (
    "deterministic disclosure checklist derived from top-venue experiment skills; "
    "it is not a venue decision, not peer review, and it cannot certify that the evidence "
    "actually supports a claim"
)

CLAIM_TYPES = {
    "beats_prior": "a tuned, compute-matched, same-split baseline comparison",
    "mechanism": "a single-mechanism ablation or intervention",
    "scales": "at least two scales/datasets with a fixed protocol",
    "robustness": "one or more out-of-distribution/stress conditions",
    "real_world": "task-relevant metric and realistic constraints",
    "negative": "a faithful reproduction that explains when the prior claim fails",
}

REQUIRED_DATASET_FIELDS = ("name", "role", "splits", "leakage_checks", "license")
REQUIRED_BASELINE_FIELDS = ("name", "implementation", "tuning", "compute")
REQUIRED_COMPUTE_FIELDS = ("hardware", "training_time", "inference_cost", "fairness")
REQUIRED_STAT_FIELDS = ("effect_size", "confidence_interval", "multiplicity", "missing_data")


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _present(value: Any, minimum: int = 3) -> bool:
    text = _text(value)
    return len(text) >= minimum and text.lower() not in ("todo", "tbd", "待补", "待人工补全")


def _declared(value: Any, minimum: int = 3) -> bool:
    """Numbers are valid declarations: alpha=0.05 and n_per_arm=6 are not short strings."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    return _present(value, minimum)


def _has_number(value: Any) -> bool:
    """A power analysis needs an SD value, not the sentence 'not estimated'."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return True
    text = _text(value).lower()
    if not text or text in ("todo", "tbd", "待补", "待人工补全"):
        return False
    if any(marker in text for marker in ("not estimated", "not available", "未估计", "未给出")):
        return False
    return bool(re.search(r"\d", text))


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("study design is not readable JSON: %s" % exc)
    if not isinstance(value, dict):
        raise ValueError("study design must be a JSON object")
    return value


def _list_of_dicts(value: Any) -> List[Dict[str, Any]]:
    return [item for item in (value or []) if isinstance(item, dict)]


def audit_study_design(design: Dict[str, Any], venue: str = "neurips") -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []
    blockers: List[str] = []
    warnings: List[str] = []

    def add(check_id: str, ok: bool, detail: str, severity: str = "blocker") -> bool:
        checks.append(
            {
                "id": check_id,
                "status": "pass" if ok else "fail",
                "detail": detail,
                "severity": severity,
            }
        )
        if not ok:
            if severity == "blocker":
                blockers.append("%s: %s" % (check_id, detail))
            else:
                warnings.append("%s: %s" % (check_id, detail))
        return ok

    if str(design.get("schema_version") or "") != STUDY_DESIGN_SCHEMA:
        add(
            "design.schema",
            False,
            "schema must be %s; a run design (experiment.json) is not a study design"
            % STUDY_DESIGN_SCHEMA,
        )
        return _result(checks, blockers, warnings, venue)

    add("design.question", _present(design.get("question"), 8), "research question")
    add("design.hypothesis", _present(design.get("hypothesis"), 15), "falsifiable hypothesis")

    claims = _list_of_dicts(design.get("claims"))
    claim_ok = len(claims) >= 1
    add("claims.present", claim_ok, "%d claim(s)" % len(claims))
    claim_types: List[str] = []
    for index, claim in enumerate(claims):
        label = "claims.%d" % (index + 1)
        kind = str(claim.get("type") or "")
        claim_types.append(kind)
        add(label + ".type", kind in CLAIM_TYPES, "type=%r" % kind)
        add(label + ".statement", _present(claim.get("claim"), 10), "claim statement")
        add(
            label + ".evidence",
            _present(claim.get("evidence"), 20),
            "evidence mapping for the %s claim" % (kind or "untyped"),
        )

    datasets = _list_of_dicts(design.get("datasets"))
    add("data.present", bool(datasets), "%d dataset(s)" % len(datasets))
    for index, dataset in enumerate(datasets):
        label = "data.%d" % (index + 1)
        missing = [key for key in REQUIRED_DATASET_FIELDS if not _present(dataset.get(key))]
        add(
            label,
            not missing,
            "missing: " + ", ".join(missing) if missing else "splits/leakage/license documented",
        )
        add(
            label + ".coverage",
            _present(dataset.get("coverage"), 10),
            "domain/demographic/scale coverage",
            "warning",
        )

    baselines = _list_of_dicts(design.get("baselines"))
    add("baselines.present", bool(baselines), "%d baseline(s)" % len(baselines))
    for index, baseline in enumerate(baselines):
        label = "baselines.%d" % (index + 1)
        missing = [key for key in REQUIRED_BASELINE_FIELDS if not _present(baseline.get(key))]
        add(
            label,
            not missing,
            "missing: " + ", ".join(missing)
            if missing else
            "implementation/tuning/compute disclosed",
        )
        add(
            label + ".matched",
            bool(baseline.get("compute_matched")),
            "compute-matched comparison",
            "warning",
        )

    ablations = _list_of_dicts(design.get("ablations"))
    add("ablations.present", bool(ablations), "%d ablation(s)" % len(ablations))
    for index, ablation in enumerate(ablations):
        label = "ablations.%d" % (index + 1)
        add(label + ".mechanism", _present(ablation.get("mechanism"), 10), "isolated mechanism")
        add(
            label + ".single_change",
            bool(ablation.get("single_change")),
            "only one factor changes",
            "warning",
        )

    robustness = _list_of_dicts(design.get("robustness"))
    add("robustness.present", bool(robustness), "%d robustness plan(s)" % len(robustness))
    axes = {str(item.get("axis") or "") for item in robustness}
    add(
        "robustness.axes",
        len(axes) >= 1,
        "axes: " + ", ".join(sorted(axis for axis in axes if axis)) if axes else "no axis",
        "warning",
    )

    compute = design.get("compute") if isinstance(design.get("compute"), dict) else {}
    missing_compute = [key for key in REQUIRED_COMPUTE_FIELDS if not _present(compute.get(key))]
    add(
        "compute.disclosure",
        not missing_compute,
        "missing: " + ", ".join(missing_compute) if missing_compute else "compute disclosed",
    )

    stats = design.get("statistics") if isinstance(design.get("statistics"), dict) else {}
    missing_stats = [key for key in REQUIRED_STAT_FIELDS if not _present(stats.get(key))]
    add(
        "statistics.plan",
        not missing_stats,
        "missing: " + ", ".join(missing_stats) if missing_stats else "statistical plan present",
    )
    seeds = stats.get("seeds")
    add(
        "statistics.seeds",
        isinstance(seeds, int) and not isinstance(seeds, bool) and seeds >= 3,
        "seeds=%r; at least 3 required for variance" % (seeds,),
    )
    power = stats.get("power_analysis") if isinstance(stats.get("power_analysis"), dict) else {}
    power_fields = ("effect_size", "sd", "alpha", "power", "n_per_arm")
    missing_power = [key for key in power_fields if not _declared(power.get(key))]
    if not _has_number(power.get("sd")):
        missing_power.append("sd (numeric)")
    if set(claim_types) & {"beats_prior", "mechanism", "scales", "robustness"}:
        add(
            "statistics.power_analysis",
            not missing_power,
            "missing: " + ", ".join(missing_power)
            if missing_power else
            "effect/SD/alpha/power/n per arm declared",
        )

    statuses = [str(item.get("data_status") or "") for item in datasets]
    if datasets and not all(statuses):
        add(
            "data.status",
            False,
            "each dataset should declare data_status=fixture|planned|collected",
            "warning",
        )
    prior_work = _list_of_dicts(design.get("prior_work"))
    add(
        "prior_work.present",
        len(prior_work) >= 2,
        "%d prior-work entr(ies); at least 2 with a stated relation are expected for a venue claim"
        % len(prior_work),
        "warning",
    )

    add(
        "negative_results",
        _present(design.get("negative_results"), 15),
        "negative-result plan / boundary conditions",
        "warning",
    )
    add(
        "limitations",
        _present(design.get("limitations"), 15),
        "limitations and threats to validity",
        "warning",
    )

    # Claim-to-evidence ladder: the evidence section must match the claim type.
    if claims and baselines and datasets:
        tuned_baselines = all(
            _present(item.get("tuning")) and _present(item.get("implementation"))
            for item in baselines
        )
        clean_splits = all(
            _present(item.get("splits")) and _present(item.get("leakage_checks"))
            for item in datasets
        )
        if "beats_prior" in claim_types:
            add(
                "ladder.beats_prior",
                tuned_baselines and clean_splits,
                "beats-prior needs tuned baselines and leakage-checked splits",
            )
        if "mechanism" in claim_types:
            add(
                "ladder.mechanism",
                bool(ablations) and all(_present(item.get("mechanism")) for item in ablations),
                "mechanism claim needs a mechanism-isolating ablation",
            )
        if "scales" in claim_types:
            add(
                "ladder.scales",
                len(datasets) >= 2,
                "scales claim needs at least two datasets/scales, got %d" % len(datasets),
            )
        if "robustness" in claim_types:
            add(
                "ladder.robustness",
                bool(robustness),
                "robustness claim needs at least one stress condition",
            )
        if "real_world" in claim_types:
            add(
                "ladder.real_world",
                _present(design.get("deployment") or "", 10),
                "real-world claim needs deployment constraints",
            )
        if "negative" in claim_types:
            add(
                "ladder.negative",
                _present(design.get("negative_results"), 15),
                "negative result needs a faithful reproduction plan",
            )
    replication = design.get("replication") if isinstance(design.get("replication"), dict) else {}
    if replication:
        replication_status = str(replication.get("status") or "").lower()
        add(
            "replication.scope",
            replication_status in ("consistent", "generalises", "generalizes", "generalized"),
            "replication status=%s; decided in %s of %s environments"
            % (
                replication_status or "unstated",
                len(replication.get("decided_in") or []),
                int(replication.get("datasets") or 0),
            ),
            severity="warning",
        )
        total = int(replication.get("datasets") or 0)
        partial = [
            "%s %d/%d" % (key, len(value), total)
            for key, value in replication.items()
            if key.endswith("_decided_in")
            and isinstance(value, list)
            and total
            and len(value) < total
        ]
        if partial:
            add(
                "replication.partial_claim",
                False,
                "claim-level replication is partial: " + ", ".join(partial),
                severity="warning",
            )
    elif len(datasets) > 1:
        add(
            "replication.scope",
            False,
            "multiple datasets are declared but replication status is not disclosed",
            severity="warning",
        )
    metric_validity = design.get("metric_validity")
    if isinstance(metric_validity, dict):
        undecided = _metric_validity_undecided(design)
        add(
            "metric.validity",
            not undecided,
            "the disclosed metric sensitivity is undecided in "
            + ", ".join(undecided)
            + "; report the registered metric as metric-specific, not as a general efficiency effect"
            if undecided
            else "metric-validity sensitivity is decided in every declared environment",
            severity="warning",
        )
    return _result(checks, blockers, warnings, venue, design)


def _metric_validity_undecided(design: Dict[str, Any]) -> List[str]:
    metric = design.get("metric_validity")
    if not isinstance(metric, dict):
        return []
    return [str(item) for item in metric.get("undecided_in") or [] if str(item)]


def _readiness(design: Dict[str, Any], blockers: List[str]) -> Dict[str, Any]:
    """Separate 'the design discloses enough' from 'the evidence exists' and 'venue-ready'."""
    datasets = _list_of_dicts(design.get("datasets"))
    stats = design.get("statistics") if isinstance(design.get("statistics"), dict) else {}
    power = stats.get("power_analysis") if isinstance(stats.get("power_analysis"), dict) else {}
    power_ok = all(
        _declared(power.get(key)) for key in ("effect_size", "sd", "alpha", "power", "n_per_arm")
    ) and _has_number(power.get("sd"))
    replication = design.get("replication") if isinstance(design.get("replication"), dict) else {}
    replication_status = str(replication.get("status") or "").lower()
    replication_ok = replication_status in ("consistent", "generalises", "generalizes", "generalized")
    multiple_environments = len(datasets) > 1
    replication_total = int(replication.get("datasets") or 0)
    partial_claims = [
        (str(key), len(value), replication_total)
        for key, value in replication.items()
        if key.endswith("_decided_in")
        and isinstance(value, list)
        and replication_total
        and len(value) < replication_total
    ]
    collected = any(
        str(item.get("data_status") or "").lower() == "collected" for item in datasets
    )
    prior_work = _list_of_dicts(design.get("prior_work"))
    baselines = _list_of_dicts(design.get("baselines"))
    baselines_ok = bool(baselines) and all(
        _present(item.get("implementation")) for item in baselines
    )
    reasons: List[str] = []
    if blockers:
        level = "disclosure_incomplete"
        reasons.append("%d disclosure blocker(s)" % len(blockers))
    elif not collected:
        level = "disclosure_complete"
        reasons.append("no dataset is marked data_status=collected; fixture/planned data cannot carry a venue claim")
    elif not power_ok:
        level = "disclosure_complete"
        reasons.append("statistics.power_analysis is incomplete")
    elif len(prior_work) < 2 or not baselines_ok:
        level = "evidence_ready"
        if len(prior_work) < 2:
            reasons.append("fewer than 2 prior-work entries with a stated relation")
        if not baselines_ok:
            reasons.append("baseline implementation is not documented for every baseline")
    elif replication and not replication_ok:
        level = "evidence_ready"
        reasons.append(
            "replication status is %s (%s/%s environments decided); a single-environment "
            "effect is not a venue-level generalisation"
            % (
                replication_status or "unstated",
                len(replication.get("decided_in") or []),
                int(replication.get("datasets") or 0),
            )
        )
    elif multiple_environments and not replication:
        level = "evidence_ready"
        reasons.append(
            "multiple environments are declared but no replication status is disclosed; "
            "run study replicate and record consistent/one_dataset_decided"
        )
    elif partial_claims:
        level = "evidence_ready"
        reasons.append(
            "claim-level replication is partial: "
            + ", ".join("%s %d/%d" % item for item in partial_claims)
        )
    elif _metric_validity_undecided(design):
        level = "evidence_ready"
        reasons.append(
            "metric validity: the disclosed sensitivity is undecided in "
            + ", ".join(_metric_validity_undecided(design))
            + "; the registered metric must not be read as a general efficiency effect"
        )
    else:
        level = "venue_ready"
        reasons.append("disclosure, collected data, power analysis and prior work are all present")
    if level == "venue_ready":
        reasons.append(
            "venue_ready is still a disclosure status, not a novelty/review verdict; "
            "it cannot certify that reviewers will accept the paper"
        )
    return {"level": level, "reasons": reasons, "collected_data": collected, "power_analysis": power_ok}


def _result(
    checks: List[Dict[str, str]],
    blockers: List[str],
    warnings: List[str],
    venue: str,
    design: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    passed = sum(1 for item in checks if item["status"] == "pass")
    score = round(float(passed) / len(checks), 3) if checks else 0.0
    return {
        "schema_version": AUDIT_SCHEMA,
        "venue": venue,
        "status": "incomplete" if blockers else "attention" if warnings else "ready_for_g2",
        "score": score,
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "ccfa": _readiness(design or {}, blockers),
        "boundary": BOUNDARY,
    }


def audit_file(path: Path, venue: str = "neurips") -> Dict[str, Any]:
    return audit_study_design(_load(Path(path)), venue=venue)


def study_design_template() -> Dict[str, Any]:
    """A skeleton with TODO markers; valid JSON, invalid as a study design until filled."""
    return {
        "schema_version": STUDY_DESIGN_SCHEMA,
        "question": "TODO: the scientific question",
        "hypothesis": "TODO: a falsifiable hypothesis",
        "claims": [
            {
                "claim": "TODO: headline claim",
                "type": "beats_prior",
                "evidence": "TODO: which experiment would support it",
            }
        ],
        "datasets": [
            {
                "name": "TODO",
                "role": "development|test|shift",
                "splits": "TODO",
                "leakage_checks": "TODO",
                "license": "TODO",
                "coverage": "TODO",
                "data_status": "fixture|planned|collected",
            }
        ],
        "baselines": [
            {
                "name": "TODO",
                "implementation": "official|reimplementation",
                "tuning": "TODO",
                "compute": "TODO",
                "compute_matched": False,
            }
        ],
        "ablations": [
            {"name": "TODO", "mechanism": "TODO", "single_change": True}
        ],
        "robustness": [{"axis": "seeds|datasets|shift|scale|hyperparameters", "plan": "TODO"}],
        "compute": {
            "hardware": "TODO",
            "training_time": "TODO",
            "inference_cost": "TODO",
            "fairness": "TODO",
        },
        "statistics": {
            "seeds": 3,
            "effect_size": "TODO",
            "confidence_interval": "TODO",
            "multiplicity": "TODO",
            "missing_data": "TODO",
            "power_analysis": {
                "effect_size": "TODO",
                "sd": "TODO",
                "alpha": 0.05,
                "power": 0.8,
                "n_per_arm": 0,
            },
        },
        "prior_work": [
            {"title": "TODO", "venue": "TODO", "year": 0, "relation": "TODO"}
        ],
        "negative_results": "TODO",
        "limitations": "TODO",
        "deployment": "TODO for real_world claims",
    }
