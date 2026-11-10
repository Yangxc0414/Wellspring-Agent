"""What this runtime can actually test, as one authoritative registry.

The idea stage kept proposing experiment plans that the execution stage could not run:
hypotheses about search behaviour paired with a harness that only fits a model once on a
tabular dataset, and literature corpora written into ``dataset`` fields. A plan the runtime
cannot execute is not a plan, so both generation and review need one shared answer to
"can this be tested here?".

Profiles are declared with what they *cannot* test, because an over-claim about scope is the
failure mode this registry exists to prevent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

REGISTRY_SCHEMA = "executable-profiles-0.1"

BOUNDARY = (
    "a capability registry, not a claim of scientific breadth: a hypothesis whose object is "
    "not listed here cannot be validated by this runtime and must not be written up as an "
    "experiment plan"
)


def _protocol_run_profile() -> Dict[str, Any]:
    # These are the S5 protocol datasets the CLI accepts (`run execute --dataset`).
    datasets = ["iris", "breast_cancer", "chemlab"]
    return {
        "id": "protocol_run",
        "label": "内置协议验证运行（S5）",
        "objective": "在同一数据与协议上重复运行，产出 RunCapsule/EA 与均值/标准差",
        "datasets": datasets,
        "metrics": ["accuracy", "mean", "std"],
        "design": "fixed protocol, repeated seeds; no search loop",
        "supports": [
            "seed variability on a fixed protocol",
            "mean/std comparison between two fixed configurations",
        ],
        "cannot_test": [
            "any search, archive or acceptance-gate effect",
            "self-modification of an agent or its code",
            "compute-normalised improvement over a lineage",
        ],
    }


def _local_experiment_profile() -> Dict[str, Any]:
    from .experiment_codegen import SUPPORTED_METHODS

    return {
        "id": "local_tabular_experiment",
        "label": "项目内 CSV 的本地监督实验（S4→S5）",
        "objective": "用户数据上的 baseline/方法对比，带 CI 与结果表",
        "datasets": ["user-provided CSV inside the project"],
        "metrics": ["r2", "accuracy", "mean_diff", "ci95"],
        "design": "train/test split, listed estimators, optional k-fold CV and ridge alpha sweep",
        "supports": [
            "supervised comparison of listed estimators on user tabular data",
            "paired difference intervals over seeds or folds",
        ],
        "cannot_test": [
            "generative or agentic behaviour",
            "long-horizon search with a retained population",
            "anything requiring the user's own training code",
        ],
        "methods": list(SUPPORTED_METHODS),
    }


def _search_study_profile() -> Dict[str, Any]:
    from .search_lab import study_profile_summary

    profile = study_profile_summary()
    return {
        "id": "search_factorial",
        "label": "改进搜索控制研究（可声明因子的控制设计）",
        "objective": profile["kind"],
        "datasets": list(profile["datasets"]),
        "metrics": ["improvement_per_evaluation", "best_score", "lineage_depth"],
        "design": "declared factorial over the registered controls (%s), paired across seeds; "
        "default is the 2x2 memory x gate"
        % ", ".join(sorted((profile.get("factors") or {}).keys())),
        "factors": {
            key: list(value) for key, value in sorted((profile.get("factors") or {}).items())
        },
        "operator_sets": {
            key: list(value)
            for key, value in sorted((profile.get("operator_sets") or {}).items())
        },
        "supports": list(profile["supports"]),
        "cannot_test": list(profile["does_not_support"]),
    }


def executable_profiles() -> List[Dict[str, Any]]:
    return [_protocol_run_profile(), _local_experiment_profile(), _search_study_profile()]


def profile_ids() -> List[str]:
    return [profile["id"] for profile in executable_profiles()]


def validate_plan(
    plan: Dict[str, Any],
    profiles: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Check one experiment plan against the registry.

    Returns ``{"ok": bool, "reasons": [...], "profile": str}``. A plan that names no profile
    is not executable-by-construction, so it is rejected rather than passed with a warning:
    silently accepting untestable plans is what produced fictional experiment sections.
    """
    registry = profiles if profiles is not None else executable_profiles()
    by_id = {profile["id"]: profile for profile in registry}
    reasons: List[str] = []
    profile_id = str((plan or {}).get("profile") or "").strip()
    if not profile_id:
        reasons.append("experiment plan must name an executable profile: " + ", ".join(by_id))
        return {"ok": False, "reasons": reasons, "profile": ""}
    if profile_id not in by_id:
        reasons.append("unknown profile '%s'; available: %s" % (profile_id, ", ".join(by_id)))
        return {"ok": False, "reasons": reasons, "profile": profile_id}
    profile = by_id[profile_id]
    dataset = str((plan or {}).get("dataset") or "").strip()
    if dataset:
        accepted = [str(item).lower() for item in profile.get("datasets") or []]
        if not any(token in " ".join(accepted) for token in dataset.lower().split()):
            reasons.append(
                "dataset '%s' is not listed for profile '%s' (%s)"
                % (dataset, profile_id, ", ".join(accepted))
            )
    metric = str((plan or {}).get("metric") or "").strip()
    if metric and profile.get("metrics"):
        tokens = [token for token in metric.lower().replace(",", " ").split() if token]
        known = " ".join(str(item).lower() for item in profile["metrics"])
        if not any(token in known for token in tokens):
            reasons.append(
                "metric '%s' is not produced by profile '%s' (%s)"
                % (metric, profile_id, ", ".join(str(item) for item in profile["metrics"]))
            )
    return {"ok": not reasons, "reasons": reasons, "profile": profile_id}


def plan_prompt_block() -> str:
    """The registry rendered for a generation prompt, including each profile's limits."""
    lines: List[str] = []
    for profile in executable_profiles():
        lines.append(
            "- profile=%s | 数据=%s | 指标=%s | 设计=%s | 不能检验=%s"
            % (
                profile["id"],
                ", ".join(str(item) for item in profile.get("datasets") or []),
                ", ".join(str(item) for item in profile.get("metrics") or []),
                profile.get("design", ""),
                "; ".join(profile.get("cannot_test") or []),
            )
        )
    return "\n".join(lines)
